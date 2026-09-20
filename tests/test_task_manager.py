import unittest
import time
from src.crawler.task_manager import CrawlerTaskManager

class TestTaskManager(unittest.TestCase):
    def test_initial_state(self):
        manager = CrawlerTaskManager()
        status = manager.get_status()
        self.assertFalse(status["is_running"])
        self.assertEqual(status["scraped_count"], 0)
        self.assertEqual(status["status_message"], "Sẵn sàng")

    def test_stop_crawl_when_not_running(self):
        manager = CrawlerTaskManager()
        result = manager.stop_crawl()
        self.assertFalse(result)

    def test_progress_callback(self):
        manager = CrawlerTaskManager()
        manager._progress_callback(
            current=10,
            total=50,
            msg="Đang cào...",
            latest={
                "username": "test_user",
                "is_toxic": True,
                "is_reply": False
            }
        )
        status = manager.get_status()
        self.assertEqual(status["scraped_count"], 10)
        self.assertEqual(status["toxic_count"], 1)
        self.assertEqual(status["root_count"], 1)
        self.assertEqual(status["child_count"], 0)
        self.assertEqual(status["status_message"], "Đang cào...")

    def test_reset_status(self):
        manager = CrawlerTaskManager()
        manager.scraped_count = 25
        manager.reset_status()
        status = manager.get_status()
        self.assertEqual(status["status_message"], "Sẵn sàng")

if __name__ == "__main__":
    unittest.main()
