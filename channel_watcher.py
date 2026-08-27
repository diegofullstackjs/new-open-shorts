"""
Auto-Channel Watcher module for OpenShorts.
Monitors YouTube channels via XML/RSS feeds and triggers automatic processing
whenever a new video is published.
"""

import os
import re
import time
import sqlite3
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [ChannelWatcher] %(message)s")
logger = logging.getLogger("ChannelWatcher")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "watcher.db")


@dataclass
class FeedVideo:
    video_id: str
    title: str
    link: str
    published: str
    channel_id: str


class ChannelWatcherDB:
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
                CREATE TABLE IF NOT EXISTS watched_channels (
                    channel_id TEXT PRIMARY KEY,
                    name TEXT,
                    auto_process INTEGER DEFAULT 1,
                    layouts TEXT DEFAULT 'auto',
                    subtitle_style TEXT DEFAULT 'hormozi',
                    custom_prompt TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_videos (
                    video_id TEXT PRIMARY KEY,
                    channel_id TEXT,
                    title TEXT,
                    link TEXT,
                    published_at TEXT,
                    job_id TEXT,
                    status TEXT,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (channel_id) REFERENCES watched_channels(channel_id)
                )
            """)
            conn.commit()

    def add_channel(self, channel_id: str, name: str = "", auto_process: bool = True,
                    layouts: str = "auto", subtitle_style: str = "hormozi", custom_prompt: Optional[str] = None):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO watched_channels (channel_id, name, auto_process, layouts, subtitle_style, custom_prompt)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (channel_id, name, 1 if auto_process else 0, layouts, subtitle_style, custom_prompt))
            conn.commit()

    def remove_channel(self, channel_id: str):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM watched_channels WHERE channel_id = ?", (channel_id,))
            conn.commit()

    def list_channels(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM watched_channels ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def is_video_processed(self, video_id: str) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT 1 FROM processed_videos WHERE video_id = ?", (video_id,))
            return cursor.fetchone() is not None

    def record_video(self, video: FeedVideo, job_id: Optional[str] = None, status: str = "pending", error: Optional[str] = None):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO processed_videos (video_id, channel_id, title, link, published_at, job_id, status, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (video.video_id, video.channel_id, video.title, video.link, video.published, job_id, status, error))
            conn.commit()

    def list_processed_videos(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM processed_videos ORDER BY created_at DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]


class ChannelWatcher:
    def __init__(self, api_base_url: str = "http://127.0.0.1:8000", db_path: str = DB_PATH):
        self.api_base_url = api_base_url.rstrip("/")
        self.db = ChannelWatcherDB(db_path)

    @staticmethod
    def resolve_channel_id(input_url_or_id: str) -> Optional[str]:
        """Resolves Channel ID from URL (channel/UC..., @handle or direct ID)."""
        input_url_or_id = input_url_or_id.strip()
        if input_url_or_id.startswith("UC") and len(input_url_or_id) == 24:
            return input_url_or_id
        
        match = re.search(r"channel/(UC[\w-]{22})", input_url_or_id)
        if match:
            return match.group(1)

        # Scrape channel ID from web page for @handle or /c/ urls
        try:
            target_url = input_url_or_id if input_url_or_id.startswith("http") else f"https://www.youtube.com/{input_url_or_id}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            resp = httpx.get(target_url, headers=headers, timeout=10.0, follow_redirects=True)
            if resp.status_code == 200:
                cid_match = re.search(r'itemprop="channelId"\s+content="(UC[\w-]{22})"', resp.text)
                if cid_match:
                    return cid_match.group(1)
                cid_match2 = re.search(r'"channelId":"(UC[\w-]{22})"', resp.text)
                if cid_match2:
                    return cid_match2.group(1)
        except Exception as e:
            logger.error(f"Failed to resolve channel ID for {input_url_or_id}: {e}")
        return None

    def fetch_channel_feed(self, channel_id: str) -> List[FeedVideo]:
        """Fetches and parses YouTube XML RSS feed without needing a YouTube Data API Key."""
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        videos: List[FeedVideo] = []
        try:
            resp = httpx.get(feed_url, timeout=15.0)
            if resp.status_code != 200:
                logger.warning(f"Feed returned HTTP {resp.status_code} for channel {channel_id}")
                return videos

            root = ET.fromstring(resp.content)
            # Standard Atom namespace
            ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
            
            for entry in root.findall("atom:entry", ns):
                vid_elem = entry.find("yt:videoId", ns)
                title_elem = entry.find("atom:title", ns)
                link_elem = entry.find("atom:link", ns)
                pub_elem = entry.find("atom:published", ns)

                video_id = vid_elem.text if vid_elem is not None else ""
                title = title_elem.text if title_elem is not None else ""
                link = link_elem.attrib.get("href", f"https://www.youtube.com/watch?v={video_id}") if link_elem is not None else f"https://www.youtube.com/watch?v={video_id}"
                published = pub_elem.text if pub_elem is not None else ""

                if video_id:
                    videos.append(FeedVideo(
                        video_id=video_id,
                        title=title,
                        link=link,
                        published=published,
                        channel_id=channel_id
                    ))
        except Exception as e:
            logger.error(f"Error parsing feed for channel {channel_id}: {e}")

        return videos

    def submit_video_job(self, video: FeedVideo, channel_config: Dict[str, Any]) -> Optional[str]:
        """Submits video to OpenShorts /api/process endpoint."""
        logger.info(f"Submitting video to pipeline: {video.title} ({video.link})")
        payload = {
            "url": video.link,
            "layouts": channel_config.get("layouts", "auto"),
            "subtitle_style": channel_config.get("subtitle_style", "hormozi"),
        }
        if channel_config.get("custom_prompt"):
            payload["custom_prompt"] = channel_config["custom_prompt"]

        try:
            resp = httpx.post(f"{self.api_base_url}/api/process", data=payload, timeout=30.0)
            if resp.status_code in (200, 201, 202):
                data = resp.json()
                job_id = data.get("job_id")
                logger.info(f"Successfully triggered job {job_id} for video {video.video_id}")
                return job_id
            else:
                logger.error(f"Failed to trigger job for {video.video_id}: HTTP {resp.status_code} - {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Exception submitting job for {video.video_id}: {e}")
            return None

    def poll_all_channels(self) -> List[Dict[str, Any]]:
        """Checks all watched channels and triggers jobs for new videos."""
        channels = self.db.list_channels()
        dispatched_jobs = []

        for ch in channels:
            cid = ch["channel_id"]
            if not ch.get("auto_process"):
                continue

            videos = self.fetch_channel_feed(cid)
            for vid in videos:
                if not self.db.is_video_processed(vid.video_id):
                    job_id = self.submit_video_job(vid, ch)
                    if job_id:
                        self.db.record_video(vid, job_id=job_id, status="processing")
                        dispatched_jobs.append({"video_id": vid.video_id, "title": vid.title, "job_id": job_id})
                    else:
                        self.db.record_video(vid, job_id=None, status="failed", error="API dispatch failed")

        return dispatched_jobs


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="OpenShorts Auto-Channel Watcher")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="OpenShorts API URL")
    parser.add_argument("--interval", type=int, default=300, help="Polling interval in seconds (default: 300)")
    parser.add_argument("--add-channel", help="Channel URL or ID to add")
    parser.add_argument("--name", default="", help="Optional channel nickname")
    parser.add_argument("--list", action="store_true", help="List watched channels")
    parser.add_argument("--once", action="store_true", help="Run a single poll pass and exit")
    args = parser.parse_args()

    watcher = ChannelWatcher(api_base_url=args.api_url)

    if args.add_channel:
        cid = watcher.resolve_channel_id(args.add_channel)
        if cid:
            watcher.db.add_channel(cid, name=args.name or cid)
            print(f"Added channel {cid} to watcher!")
        else:
            print(f"Could not resolve channel ID for {args.add_channel}")
        sys.exit(0)

    if args.list:
        channels = watcher.db.list_channels()
        print(f"Watched channels ({len(channels)}):")
        for c in channels:
            print(f"- {c['channel_id']} ({c['name']}) [Auto-process: {bool(c['auto_process'])}]")
        sys.exit(0)

    if args.once:
        jobs = watcher.poll_all_channels()
        print(f"Poll completed. Dispatched {len(jobs)} jobs.")
        sys.exit(0)

    print(f"Starting Auto-Channel Watcher (Interval: {args.interval}s, API: {args.api_url})...")
    while True:
        try:
            jobs = watcher.poll_all_channels()
            if jobs:
                print(f"[{time.strftime('%X')}] Triggered {len(jobs)} new shortify jobs.")
        except Exception as err:
            logger.error(f"Polling loop error: {err}")
        time.sleep(args.interval)
