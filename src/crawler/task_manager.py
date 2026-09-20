import threading
import time
from datetime import datetime
from typing import Optional, Dict, Any

from src.crawler.threads_crawler import ThreadsCrawler
from src.utils.logger import logger

class CrawlerTaskManager:
    """
    Manages background crawl tasks running on independent daemon threads.
    Persists progress and status across Streamlit script reruns and tab switching.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        self.is_running: bool = False
        self.task_type: str = ""  # "post" or "search"
        self.target: str = ""
        self.max_items: int = 0
        self.scraped_count: int = 0
        self.root_count: int = 0
        self.child_count: int = 0
        self.toxic_count: int = 0
        self.status_message: str = "Sẵn sàng"
        self.latest_item: Optional[Dict[str, Any]] = None
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.login_wall_hit: bool = False

    def is_active(self) -> bool:
        """Returns True if a background crawl thread is actively running."""
        with self._lock:
            return self.is_running and (self._worker_thread is not None and self._worker_thread.is_alive())

    def start_post_crawl(
        self,
        post_url: str,
        max_comments: int = 50,
        scroll_delay: float = 2.0,
        headless: bool = True
    ) -> bool:
        """Starts a background thread to crawl a post and its comments."""
        with self._lock:
            if self.is_running and self._worker_thread and self._worker_thread.is_alive():
                logger.warning("A crawl task is already running in the background.")
                return False

            self._stop_event.clear()
            self.is_running = True
            self.task_type = "post"
            self.target = post_url
            self.max_items = max_comments
            self.scraped_count = 0
            self.root_count = 0
            self.child_count = 0
            self.toxic_count = 0
            self.status_message = f"Bắt đầu cào bài viết: {post_url}..."
            self.latest_item = None
            self.start_time = time.time()
            self.end_time = None
            self.result = None
            self.error = None
            self.login_wall_hit = False

            self._worker_thread = threading.Thread(
                target=self._run_post_worker,
                args=(post_url, max_comments, scroll_delay, headless),
                daemon=True,
                name="ThreadsCrawler-PostWorker"
            )
            self._worker_thread.start()
            logger.info(f"Background crawl thread started for: {post_url}")
            return True

    def start_search_crawl(
        self,
        query: str,
        limit: int = 30,
        scroll_delay: float = 2.0,
        headless: bool = True
    ) -> bool:
        """Starts a background thread to crawl search results."""
        with self._lock:
            if self.is_running and self._worker_thread and self._worker_thread.is_alive():
                logger.warning("A crawl task is already running in the background.")
                return False

            self._stop_event.clear()
            self.is_running = True
            self.task_type = "search"
            self.target = query
            self.max_items = limit
            self.scraped_count = 0
            self.root_count = 0
            self.child_count = 0
            self.toxic_count = 0
            self.status_message = f"Bắt đầu tìm kiếm Threads: '{query}'..."
            self.latest_item = None
            self.start_time = time.time()
            self.end_time = None
            self.result = None
            self.error = None
            self.login_wall_hit = False

            self._worker_thread = threading.Thread(
                target=self._run_search_worker,
                args=(query, limit, scroll_delay, headless),
                daemon=True,
                name="ThreadsCrawler-SearchWorker"
            )
            self._worker_thread.start()
            logger.info(f"Background search thread started for: '{query}'")
            return True

    def stop_crawl(self) -> bool:
        """Requests the running background crawl thread to stop gracefully."""
        with self._lock:
            if not self.is_running:
                return False
            logger.info("Stopping background crawl task upon user request...")
            self._stop_event.set()
            self.status_message = "Đang dừng tiến trình cào và lưu dữ liệu..."
            return True

    def _progress_callback(self, current: int, total: int, msg: str, latest: Optional[Dict[str, Any]]):
        with self._lock:
            self.scraped_count = current
            self.status_message = msg
            if latest:
                self.latest_item = latest
                if latest.get("is_toxic"):
                    self.toxic_count += 1
                if latest.get("is_reply"):
                    self.child_count += 1
                else:
                    self.root_count += 1

    def _stop_check(self) -> bool:
        return self._stop_event.is_set()

    def _run_post_worker(self, post_url: str, max_comments: int, scroll_delay: float, headless: bool):
        try:
            crawler = ThreadsCrawler(headless=headless)
            res = crawler.crawl_post_and_comments(
                post_url=post_url,
                max_comments=max_comments,
                scroll_delay=scroll_delay,
                progress_callback=self._progress_callback,
                stop_check=self._stop_check
            )
            with self._lock:
                self.result = res
                self.login_wall_hit = bool(res.get("login_wall_hit", False))
                self.scraped_count = res.get("comments_count", self.scraped_count)
                self.root_count = res.get("root_comments_count", self.root_count)
                self.child_count = res.get("child_comments_count", self.child_count)
                self.toxic_count = res.get("toxic_comments_count", self.toxic_count)
                if self._stop_event.is_set():
                    self.status_message = f"Đã dừng theo yêu cầu! Thu thập được {self.scraped_count} bình luận ({self.toxic_count} độc hại)."
                else:
                    self.status_message = f"Hoàn tất cào! Thu thập {self.scraped_count} bình luận ({self.toxic_count} độc hại)."
        except Exception as e:
            logger.error(f"Error in background crawl worker: {e}", exc_info=True)
            with self._lock:
                self.error = str(e)
                self.status_message = f"Lỗi: {e}"
        finally:
            with self._lock:
                self.is_running = False
                self.end_time = time.time()

    def _run_search_worker(self, query: str, limit: int, scroll_delay: float, headless: bool):
        try:
            crawler = ThreadsCrawler(headless=headless)
            res = crawler.crawl_search_query(
                query=query,
                limit=limit,
                scroll_delay=scroll_delay,
                progress_callback=self._progress_callback,
                stop_check=self._stop_check
            )
            with self._lock:
                self.result = res
                self.scraped_count = res.get("posts_count", self.scraped_count)
                self.toxic_count = res.get("toxic_posts_count", self.toxic_count)
                if self._stop_event.is_set():
                    self.status_message = f"Đã dừng theo yêu cầu! Thu thập được {self.scraped_count} bài đăng ({self.toxic_count} vi phạm)."
                else:
                    self.status_message = f"Hoàn tất tìm kiếm! Thu thập {self.scraped_count} bài đăng ({self.toxic_count} vi phạm)."
        except Exception as e:
            logger.error(f"Error in background search worker: {e}", exc_info=True)
            with self._lock:
                self.error = str(e)
                self.status_message = f"Lỗi: {e}"
        finally:
            with self._lock:
                self.is_running = False
                self.end_time = time.time()

    def get_status(self) -> Dict[str, Any]:
        """Returns a thread-safe snapshot copy of current task status."""
        with self._lock:
            active = self.is_running and (self._worker_thread is not None and self._worker_thread.is_alive())
            elapsed = 0.0
            if self.start_time:
                end = self.end_time if self.end_time else time.time()
                elapsed = round(end - self.start_time, 1)

            return {
                "is_running": active,
                "task_type": self.task_type,
                "target": self.target,
                "max_items": self.max_items,
                "scraped_count": self.scraped_count,
                "root_count": self.root_count,
                "child_count": self.child_count,
                "toxic_count": self.toxic_count,
                "status_message": self.status_message,
                "latest_item": self.latest_item,
                "elapsed_seconds": elapsed,
                "result": self.result,
                "error": self.error,
                "login_wall_hit": self.login_wall_hit,
                "stop_requested": self._stop_event.is_set()
            }

    def reset_status(self):
        """Resets status to idle (only when not running)."""
        with self._lock:
            if not (self.is_running and self._worker_thread and self._worker_thread.is_alive()):
                self.is_running = False
                self.task_type = ""
                self.target = ""
                self.status_message = "Sẵn sàng"
                self.latest_item = None
                self.result = None
                self.error = None

# Global Singleton instance
crawler_task_manager = CrawlerTaskManager()
