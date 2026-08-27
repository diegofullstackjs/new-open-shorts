import os
import unittest
import tempfile
from datetime import datetime, timezone
import channel_watcher
import smart_scheduler

class TestAutomationSuite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_channel_watcher_db(self):
        db_file = os.path.join(self.temp_dir.name, "test_watcher.db")
        db = channel_watcher.ChannelWatcherDB(db_path=db_file)
        
        db.add_channel("UC1234567890123456789012", name="Canal Teste", auto_process=True)
        channels = db.list_channels()
        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0]["channel_id"], "UC1234567890123456789012")
        
        vid = channel_watcher.FeedVideo(
            video_id="vid_001",
            title="Video Viral Teste",
            link="https://youtube.com/watch?v=vid_001",
            published="2026-08-27T12:00:00Z",
            channel_id="UC1234567890123456789012"
        )
        self.assertFalse(db.is_video_processed("vid_001"))
        db.record_video(vid, job_id="job_abc", status="processing")
        self.assertTrue(db.is_video_processed("vid_001"))

    def test_smart_scheduler_slot_calculation(self):
        db_file = os.path.join(self.temp_dir.name, "test_scheduler.db")
        scheduler = smart_scheduler.SmartScheduler(db_path=db_file)
        
        slot = scheduler.calculate_next_optimal_slot(["tiktok", "instagram"])
        self.assertIsInstance(slot, datetime)
        self.assertEqual(slot.tzinfo, timezone.utc)

    def test_smart_scheduler_queue(self):
        db_file = os.path.join(self.temp_dir.name, "test_scheduler.db")
        scheduler = smart_scheduler.SmartScheduler(db_path=db_file)
        
        clips = [{
            "clip_filename": "short_1.mp4",
            "title": "Short Incrível",
            "description": "Veja isso!"
        }]
        scheduled_ids = scheduler.schedule_clips_from_job("job_999", clips, ["tiktok", "youtube"])
        self.assertEqual(len(scheduled_ids), 1)
        
        posts = scheduler.db.list_pending_posts()
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["job_id"], "job_999")

if __name__ == "__main__":
    unittest.main()
