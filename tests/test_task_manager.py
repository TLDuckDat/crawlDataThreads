import unittest
import time
from unittest.mock import MagicMock, patch
from src.crawler.task_manager import CrawlerTaskManager, parse_multi_urls

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
        manager.total_links = 3
        manager.reset_status()
        status = manager.get_status()
        self.assertEqual(status["status_message"], "Sẵn sàng")
        self.assertEqual(status["total_links"], 0)

    def test_parse_multi_urls_various_delimiters(self):
        # Newlines
        text1 = "https://www.threads.net/@user1/post/111\nhttps://www.threads.net/@user2/post/222"
        urls1 = parse_multi_urls(text1)
        self.assertEqual(urls1, [
            "https://www.threads.net/@user1/post/111",
            "https://www.threads.net/@user2/post/222"
        ])

        # Commas and spaces
        text2 = "https://www.threads.com/@u/post/1, https://www.threads.com/@u/post/2, threads.net/@u/post/3"
        urls2 = parse_multi_urls(text2)
        self.assertEqual(urls2, [
            "https://www.threads.com/@u/post/1",
            "https://www.threads.com/@u/post/2",
            "https://threads.net/@u/post/3"
        ])

    def test_parse_multi_urls_duplicates_and_empty(self):
        self.assertEqual(parse_multi_urls(""), [])
        self.assertEqual(parse_multi_urls("   \n\n  "), [])

        text = "https://threads.net/@u/post/1\nhttps://threads.net/@u/post/1\nhttps://threads.net/@u/post/2"
        urls = parse_multi_urls(text)
        self.assertEqual(urls, [
            "https://threads.net/@u/post/1",
            "https://threads.net/@u/post/2"
        ])

    def test_start_multi_post_crawl_empty(self):
        manager = CrawlerTaskManager()
        res = manager.start_multi_post_crawl(post_urls=[])
        self.assertFalse(res)
        self.assertFalse(manager.is_active())

    @patch("src.crawler.task_manager.ThreadsCrawler")
    def test_multi_post_worker_execution(self, mock_crawler_cls):
        mock_instance = MagicMock()
        mock_crawler_cls.return_value = mock_instance

        # Mock results for 2 links
        def side_effect(post_url, max_comments, scroll_delay, progress_callback, stop_check, **kwargs):
            if "link1" in post_url:
                progress_callback(1, 10, "Done link 1", {"username": "a", "is_toxic": False, "is_reply": False})
                return {"comments_count": 1, "root_comments_count": 1, "child_comments_count": 0, "toxic_comments_count": 0}
            else:
                progress_callback(2, 10, "Done link 2", {"username": "b", "is_toxic": True, "is_reply": True})
                return {"comments_count": 2, "root_comments_count": 0, "child_comments_count": 2, "toxic_comments_count": 1}

        mock_instance.crawl_post_and_comments.side_effect = side_effect

        manager = CrawlerTaskManager()
        urls = ["https://threads.net/link1", "https://threads.net/link2"]
        started = manager.start_multi_post_crawl(urls, max_comments=10)
        self.assertTrue(started)

        # Wait for worker thread to complete
        if manager._worker_thread:
            manager._worker_thread.join(timeout=5)

        status = manager.get_status()
        self.assertFalse(status["is_running"])
        self.assertEqual(status["total_links"], 2)
        self.assertEqual(status["scraped_count"], 3)
        self.assertEqual(status["toxic_count"], 1)
        self.assertEqual(status["root_count"], 1)
        self.assertEqual(status["child_count"], 2)
        self.assertIn("Hoàn tất cào 2 bài viết", status["status_message"])
        self.assertEqual(len(status["link_results"]), 2)

    @patch("src.crawler.task_manager.ThreadsCrawler")
    def test_multi_post_worker_stop_early(self, mock_crawler_cls):
        mock_instance = MagicMock()
        mock_crawler_cls.return_value = mock_instance

        manager = CrawlerTaskManager()

        def side_effect(post_url, max_comments, scroll_delay, progress_callback, stop_check, **kwargs):
            # Stop immediately during link 1
            manager.stop_crawl()
            return {"comments_count": 1, "root_comments_count": 1, "child_comments_count": 0, "toxic_comments_count": 0}

        mock_instance.crawl_post_and_comments.side_effect = side_effect

        urls = ["https://threads.net/link1", "https://threads.net/link2", "https://threads.net/link3"]
        started = manager.start_multi_post_crawl(urls)
        self.assertTrue(started)

        if manager._worker_thread:
            manager._worker_thread.join(timeout=5)

        status = manager.get_status()
        self.assertFalse(status["is_running"])
        self.assertEqual(len(status["link_results"]), 1)
        self.assertIn("Đã dừng theo yêu cầu", status["status_message"])

if __name__ == "__main__":
    unittest.main()
