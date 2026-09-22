import re
import threading
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

from src.crawler.threads_crawler import ThreadsCrawler
from src.utils.logger import logger

def parse_multi_urls(raw_text: str) -> List[str]:
    """
    Extracts and normalizes a list of URLs from user input text.
    Handles newline separation, comma separation, semicolon separation, and whitespace.
    Removes duplicates while preserving order.
    """
    if not raw_text or not raw_text.strip():
        return []

    # Split by newlines, commas, semicolons
    raw_lines = re.split(r'[\r\n,;]+', raw_text)
    urls = []
    seen = set()
    for segment in raw_lines:
        tokens = segment.strip().split()
        for token in tokens:
            cleaned = token.strip().strip("'\"<>(),;[]{}")
            if not cleaned:
                continue
            # Ensure it's a URL-like string
            if cleaned.startswith("http://") or cleaned.startswith("https://") or "threads.net" in cleaned or "threads.com" in cleaned:
                if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
                    cleaned = "https://" + cleaned
                if cleaned not in seen:
                    seen.add(cleaned)
                    urls.append(cleaned)
    return urls

class CrawlerTaskManager:
    """
    Manages background crawl tasks running on independent daemon threads.
    Persists progress and status across Streamlit script reruns and tab switching.
    Supports batch crawling multiple Threads post URLs sequentially.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        self.is_running: bool = False
        self.task_type: str = ""  # "post" or "search"
        self.target: str = ""
        self.post_urls: List[str] = []
        self.total_links: int = 0
        self.current_link_idx: int = 0
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
        self.link_results: List[Dict[str, Any]] = []
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
        """Starts a background thread to crawl a single post and its comments."""
        return self.start_multi_post_crawl(
            post_urls=[post_url],
            max_comments=max_comments,
            scroll_delay=scroll_delay,
            headless=headless
        )

    def start_multi_post_crawl(
        self,
        post_urls: List[str],
        max_comments: int = 50,
        scroll_delay: float = 2.0,
        headless: bool = True
    ) -> bool:
        """Starts a background thread to crawl multiple posts sequentially."""
        with self._lock:
            if self.is_running and self._worker_thread and self._worker_thread.is_alive():
                logger.warning("A crawl task is already running in the background.")
                return False

            clean_urls = [u.strip() for u in post_urls if u and u.strip()]
            if not clean_urls:
                logger.warning("No valid URLs provided for crawl.")
                return False

            self._stop_event.clear()
            self.is_running = True
            self.task_type = "post"
            self.post_urls = clean_urls
            self.total_links = len(clean_urls)
            self.current_link_idx = 1
            self.target = clean_urls[0] if len(clean_urls) == 1 else f"{len(clean_urls)} bài viết Threads"
            self.max_items = max_comments
            self.scraped_count = 0
            self.root_count = 0
            self.child_count = 0
            self.toxic_count = 0
            self.status_message = f"Chuẩn bị cào {self.total_links} bài viết Threads..."
            self.latest_item = None
            self.start_time = time.time()
            self.end_time = None
            self.result = None
            self.link_results = []
            self.error = None
            self.login_wall_hit = False

            self._worker_thread = threading.Thread(
                target=self._run_multi_post_worker,
                args=(clean_urls, max_comments, scroll_delay, headless),
                daemon=True,
                name="ThreadsCrawler-MultiPostWorker"
            )
            self._worker_thread.start()
            logger.info(f"Background multi-post crawl thread started for {len(clean_urls)} URLs.")
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

    def _run_multi_post_worker(
        self,
        post_urls: List[str],
        max_comments: int,
        scroll_delay: float,
        headless: bool
    ):
        base_scraped = 0
        base_root = 0
        base_child = 0
        base_toxic = 0
        total_urls = len(post_urls)
        crawler = None

        try:
            crawler = ThreadsCrawler(headless=headless)
            for idx, post_url in enumerate(post_urls, 1):
                if self._stop_event.is_set():
                    logger.info(f"Stop event detected before crawling link {idx}/{total_urls}.")
                    break

                with self._lock:
                    self.current_link_idx = idx
                    self.target = post_url
                    prefix = f"[{idx}/{total_urls}] " if total_urls > 1 else ""
                    self.status_message = f"{prefix}Bắt đầu cào: {post_url}..."

                def make_progress_cb(link_idx: int, tot_links: int, b_scraped: int):
                    def cb(current: int, total: int, msg: str, latest: Optional[Dict[str, Any]]):
                        with self._lock:
                            self.scraped_count = b_scraped + current
                            prefix = f"[{link_idx}/{tot_links}] " if tot_links > 1 else ""
                            self.status_message = f"{prefix}{msg}"
                            if latest:
                                self.latest_item = latest
                                if latest.get("is_toxic"):
                                    self.toxic_count += 1
                                if latest.get("is_reply"):
                                    self.child_count += 1
                                else:
                                    self.root_count += 1
                    return cb

                current_cb = make_progress_cb(idx, total_urls, base_scraped)

                try:
                    res = crawler.crawl_post_and_comments(
                        post_url=post_url,
                        max_comments=max_comments,
                        scroll_delay=scroll_delay,
                        progress_callback=current_cb,
                        stop_check=self._stop_check
                    )
                except Exception as post_err:
                    logger.error(f"Error crawling link {post_url}: {post_err}", exc_info=True)
                    res = {
                        "target": post_url,
                        "comments_count": 0,
                        "root_comments_count": 0,
                        "child_comments_count": 0,
                        "toxic_comments_count": 0,
                        "status": "error",
                        "error": str(post_err)
                    }

                comments_in_this_post = res.get("comments_count", 0)
                root_in_this_post = res.get("root_comments_count", 0)
                child_in_this_post = res.get("child_comments_count", 0)
                toxic_in_this_post = res.get("toxic_comments_count", 0)

                base_scraped += comments_in_this_post
                base_root += root_in_this_post
                base_child += child_in_this_post
                base_toxic += toxic_in_this_post

                with self._lock:
                    self.scraped_count = base_scraped
                    self.root_count = base_root
                    self.child_count = base_child
                    self.toxic_count = base_toxic
                    if res.get("login_wall_hit"):
                        self.login_wall_hit = True
                    self.link_results.append(res)

                if self._stop_event.is_set():
                    break

            with self._lock:
                self.result = {
                    "total_links": total_urls,
                    "processed_links": len(self.link_results),
                    "comments_count": self.scraped_count,
                    "root_comments_count": self.root_count,
                    "child_comments_count": self.child_count,
                    "toxic_comments_count": self.toxic_count,
                    "login_wall_hit": self.login_wall_hit,
                    "link_results": self.link_results,
                    "status": "stopped" if self._stop_event.is_set() else "success"
                }
                if self._stop_event.is_set():
                    self.status_message = f"Đã dừng theo yêu cầu! Đã duyệt {len(self.link_results)}/{total_urls} bài viết, thu thập {self.scraped_count} bình luận ({self.toxic_count} độc hại)."
                else:
                    prefix = f"Hoàn tất cào {total_urls} bài viết!" if total_urls > 1 else "Hoàn tất cào!"
                    self.status_message = f"{prefix} Thu thập {self.scraped_count} bình luận ({self.toxic_count} độc hại)."
        except Exception as e:
            logger.error(f"Error in background multi-post crawl worker: {e}", exc_info=True)
            with self._lock:
                self.error = str(e)
                self.status_message = f"Lỗi: {e}"
        finally:
            with self._lock:
                self.is_running = False
                self.end_time = time.time()

    def _run_post_worker(self, post_url: str, max_comments: int, scroll_delay: float, headless: bool):
        self._run_multi_post_worker([post_url], max_comments, scroll_delay, headless)

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
                "total_links": self.total_links,
                "current_link_idx": self.current_link_idx,
                "post_urls": list(self.post_urls),
                "max_items": self.max_items,
                "scraped_count": self.scraped_count,
                "root_count": self.root_count,
                "child_count": self.child_count,
                "toxic_count": self.toxic_count,
                "status_message": self.status_message,
                "latest_item": self.latest_item,
                "elapsed_seconds": elapsed,
                "result": self.result,
                "link_results": list(self.link_results),
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
                self.post_urls = []
                self.total_links = 0
                self.current_link_idx = 0
                self.link_results = []
                self.status_message = "Sẵn sàng"
                self.latest_item = None
                self.result = None
                self.error = None

# Global Singleton instance
crawler_task_manager = CrawlerTaskManager()
