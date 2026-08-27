"""
Smart Scheduling Module for OpenShorts.
Calculates optimal posting time slots per social media platform (TikTok, Instagram Reels,
YouTube Shorts, LinkedIn, Facebook) and manages an automated queue.
"""

import os
import sqlite3
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [SmartScheduler] %(message)s")
logger = logging.getLogger("SmartScheduler")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "scheduler.db")

# Platform peak engagement hours (in local/target timezone, default: UTC-3 / BRT or customizable)
PLATFORM_PEAK_HOURS = {
    "tiktok": [11, 15, 19, 21],
    "instagram": [12, 18, 20],
    "youtube": [14, 17, 20],
    "linkedin": [8, 12, 17],
    "facebook": [9, 13, 16],
}


class SmartSchedulerDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT,
                    clip_name TEXT,
                    clip_path TEXT,
                    platforms TEXT, -- JSON array of strings
                    title TEXT,
                    description TEXT,
                    tags TEXT,
                    scheduled_time TIMESTAMP,
                    status TEXT DEFAULT 'pending', -- pending, published, failed, cancelled
                    response_log TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def add_scheduled_post(self, job_id: str, clip_name: str, clip_path: str, platforms: List[str],
                           title: str, description: str, scheduled_time: datetime, tags: str = "") -> int:
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO scheduled_posts (job_id, clip_name, clip_path, platforms, title, description, tags, scheduled_time, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """, (job_id, clip_name, clip_path, json.dumps(platforms), title, description, tags, scheduled_time.isoformat()))
            conn.commit()
            return cursor.lastrowid

    def list_pending_posts(self, due_only: bool = False) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            if due_only:
                now_iso = datetime.now(timezone.utc).isoformat()
                cursor = conn.execute("SELECT * FROM scheduled_posts WHERE status = 'pending' AND scheduled_time <= ? ORDER BY scheduled_time ASC", (now_iso,))
            else:
                cursor = conn.execute("SELECT * FROM scheduled_posts WHERE status = 'pending' ORDER BY scheduled_time ASC")
            return [dict(row) for row in cursor.fetchall()]

    def list_all_posts(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM scheduled_posts ORDER BY scheduled_time DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def update_status(self, post_id: int, status: str, response_log: Optional[str] = None):
        with self._get_conn() as conn:
            conn.execute("UPDATE scheduled_posts SET status = ?, response_log = ? WHERE id = ?", (status, response_log, post_id))
            conn.commit()

    def get_latest_scheduled_time(self, platform: Optional[str] = None) -> Optional[datetime]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT MAX(scheduled_time) as max_time FROM scheduled_posts WHERE status = 'pending'")
            row = cursor.fetchone()
            if row and row["max_time"]:
                return datetime.fromisoformat(row["max_time"])
        return None


class SmartScheduler:
    def __init__(self, api_base_url: str = "http://127.0.0.1:8000", db_path: str = DB_PATH, target_tz_offset_hours: int = -3):
        self.api_base_url = api_base_url.rstrip("/")
        self.db = SmartSchedulerDB(db_path)
        self.tz = timezone(timedelta(hours=target_tz_offset_hours))

    def calculate_next_optimal_slot(self, platforms: List[str], min_hours_gap: int = 4) -> datetime:
        """Calculates the best upcoming engagement time slot with smart spacing."""
        now_local = datetime.now(self.tz)
        latest_scheduled = self.db.get_latest_scheduled_time()
        
        # Start searching from whichever is further: now or after the latest post + gap
        base_time = now_local
        if latest_scheduled:
            latest_local = latest_scheduled.astimezone(self.tz)
            if latest_local > base_time:
                base_time = latest_local + timedelta(hours=min_hours_gap)

        # Collect peak hours across the target platforms
        candidate_hours = set()
        for p in platforms:
            for h in PLATFORM_PEAK_HOURS.get(p.lower(), [12, 18, 20]):
                candidate_hours.add(h)
        sorted_hours = sorted(list(candidate_hours)) if candidate_hours else [12, 18, 20]

        # Find the next available hour slot today or in following days
        current_day = base_time.date()
        for day_offset in range(0, 14):  # Look up to 14 days ahead
            target_date = current_day + timedelta(days=day_offset)
            for hour in sorted_hours:
                candidate_dt = datetime(target_date.year, target_date.month, target_date.day, hour, 0, 0, tzinfo=self.tz)
                if candidate_dt > base_time:
                    return candidate_dt.astimezone(timezone.utc)

        return (base_time + timedelta(hours=min_hours_gap)).astimezone(timezone.utc)

    def schedule_clips_from_job(self, job_id: str, clips: List[Dict[str, Any]], platforms: List[str]) -> List[int]:
        """Schedules a batch of generated clips from a completed OpenShorts job."""
        scheduled_ids = []
        for clip in clips:
            clip_name = clip.get("clip_filename") or clip.get("filename") or clip.get("title", "clip.mp4")
            clip_path = clip.get("file_path") or os.path.join("output", job_id, clip_name)
            title = clip.get("video_title_for_youtube_short") or clip.get("title", "Novo Short Viral")
            description = clip.get("video_description_for_tiktok") or clip.get("description", "")
            
            slot = self.calculate_next_optimal_slot(platforms)
            post_id = self.db.add_scheduled_post(
                job_id=job_id,
                clip_name=clip_name,
                clip_path=clip_path,
                platforms=platforms,
                title=title,
                description=description,
                scheduled_time=slot
            )
            scheduled_ids.append(post_id)
            logger.info(f"Queued clip '{clip_name}' for {slot.isoformat()} on {platforms}")
        return scheduled_ids

    def publish_post(self, post: Dict[str, Any]) -> bool:
        """Dispatches post to the OpenShorts social poster endpoint."""
        logger.info(f"Publishing post #{post['id']}: {post['title']} ({post['platforms']})")
        platforms = json.loads(post["platforms"]) if isinstance(post["platforms"], str) else post["platforms"]
        
        payload = {
            "video_path": post["clip_path"],
            "title": post["title"],
            "description": post["description"],
            "platforms": platforms,
            "tags": post.get("tags", "")
        }
        
        try:
            resp = httpx.post(f"{self.api_base_url}/api/social/post", json=payload, timeout=60.0)
            if resp.status_code in (200, 201, 202):
                self.db.update_status(post["id"], "published", resp.text)
                logger.info(f"Post #{post['id']} successfully published/queued to social media!")
                return True
            else:
                self.db.update_status(post["id"], "failed", f"HTTP {resp.status_code}: {resp.text}")
                logger.error(f"Post #{post['id']} failed with status {resp.status_code}")
                return False
        except Exception as e:
            self.db.update_status(post["id"], "failed", str(e))
            logger.error(f"Exception publishing post #{post['id']}: {e}")
            return False

    def process_due_posts(self) -> int:
        """Checks and publishes all posts that reached their scheduled time."""
        due_posts = self.db.list_pending_posts(due_only=True)
        count = 0
        for post in due_posts:
            if self.publish_post(post):
                count += 1
        return count


if __name__ == "__main__":
    import time
    scheduler = SmartScheduler()
    print("Starting Smart Scheduler daemon...")
    while True:
        try:
            published = scheduler.process_due_posts()
            if published > 0:
                print(f"[{datetime.now().strftime('%X')}] Published {published} scheduled posts.")
        except Exception as err:
            logger.error(f"Scheduler daemon error: {err}")
        time.sleep(60)
