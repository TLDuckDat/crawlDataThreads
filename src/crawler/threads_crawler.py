import time
import uuid
from typing import Optional, Callable, Dict, Any, List

import re
import requests
from config.settings import DEFAULT_SCROLL_DELAY, DEFAULT_MAX_COMMENTS, DEFAULT_HEADLESS
from src.crawler.browser import BrowserManager
from src.crawler.parser import (
    EXTRACT_THREADS_DATA_JS,
    EXPAND_MORE_BUTTONS_JS,
    SCROLL_FEED_JS,
    CHECK_LOGIN_WALL_JS,
    generate_item_id
)
from src.detector.toxic_engine import toxic_engine
from src.detector.text_normalizer import is_valid_viet_eng_content, clean_to_viet_eng
from src.database.models import PostModel, CommentModel
from src.database.db_manager import db_manager
from src.utils.logger import logger

def resolve_threads_url(url: str) -> str:
    """
    Resolve share links or redirects into canonical post URL.
    E.g. https://www.threads.com/share/Bn6CGp__YG/ -> https://www.threads.com/@y.xuan301/post/DZY08gZk2g8
    """
    url = url.strip()
    if "/share/" in url:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            r = requests.get(url, headers=headers, allow_redirects=False, timeout=10)
            loc = r.headers.get("Location")
            if loc:
                clean_url = loc.split("?")[0]
                if clean_url.startswith("/"):
                    clean_url = "https://www.threads.com" + clean_url
                logger.info(f"Resolved share URL {url} -> {clean_url}")
                return clean_url
        except Exception as e:
            logger.warning(f"Failed to resolve share URL via HTTP: {e}")
    return url.split("?")[0]

class ThreadsCrawler:
    """
    Crawler to extract Threads posts and comments in extreme detail
    and stream them directly into the Toxic Detection Engine and SQLite Database.
    """

    def __init__(self, headless: bool = DEFAULT_HEADLESS):
        self.headless = headless

    def crawl_post_and_comments(
        self,
        post_url: str,
        max_comments: Optional[int] = DEFAULT_MAX_COMMENTS,
        scroll_delay: float = DEFAULT_SCROLL_DELAY,
        progress_callback: Optional[Callable[[int, int, str, Optional[Dict]], None]] = None,
        stop_check: Optional[Callable[[], bool]] = None
    ) -> Dict[str, Any]:
        """
        Crawl a specific post and its reply thread with maximum detail.
        Auto-expands 'Xem thêm' and 'View more replies'.
        max_comments: None hoặc 0 nghĩa là KHÔNG GIỚI HẠN (cào đến khi hết bình luận).
        """
        canonical_url = resolve_threads_url(post_url)
        session_id = f"post_{uuid.uuid4().hex[:8]}"
        db_manager.create_session(session_id, canonical_url, "post")

        is_unlimited = (max_comments is None or max_comments <= 0)
        driver = None
        scraped_posts = 0
        scraped_comments = 0
        scraped_root_comments = 0
        scraped_child_comments = 0
        toxic_comments = 0
        seen_ids = set()

        try:
            logger.info(f"Starting detailed crawl for post URL: {canonical_url} (Original: {post_url}, Unlimited: {is_unlimited})")
            if progress_callback:
                progress_callback(0, 0 if is_unlimited else max_comments, f"Khởi động trình duyệt cho: {canonical_url}...", None)

            driver = BrowserManager.get_driver(headless=self.headless)
            
            # Start at Threads home
            driver.get("https://www.threads.com/")
            time.sleep(3)

            # Navigate via SPA to post page to prevent redirect to feed
            post_match = re.search(r'(/@[^/?#]+/post/[^/?#]+)', canonical_url)
            if post_match:
                post_path = post_match.group(1)
                logger.info(f"Navigating to post thread via SPA: {post_path}")
                driver.execute_script("""
                    const path = arguments[0];
                    const a = document.createElement('a');
                    a.href = path;
                    document.body.appendChild(a);
                    a.click();
                """, post_path)
                time.sleep(4)
            else:
                driver.get(canonical_url)
                time.sleep(4)

            current_scroll = 0
            max_scrolls = 100000 if is_unlimited else max(6, (max_comments or 50) // 4)
            no_new_data_count = 0

            main_post_saved = False
            main_post_id = generate_item_id("post", canonical_url, "", "")
            current_parent_comment_id = ""
            current_f0 = ""
            current_f0_author = ""
            current_f1 = ""
            current_f1_author = ""
            current_f2 = ""
            current_f2_author = ""
            current_f3 = ""
            current_level = 0
            current_thread_open = False

            while current_scroll < max_scrolls:
                if stop_check and stop_check():
                    logger.info("Nhận tín hiệu dừng cào từ người dùng. Đang hoàn tất và lưu dữ liệu...")
                    break

                if not is_unlimited and scraped_comments >= max_comments:
                    break

                # Auto-click 'Xem thêm' and 'Xem phản hồi' to expand truncated comments & replies
                try:
                    driver.execute_script(EXPAND_MORE_BUTTONS_JS)
                except Exception:
                    pass

                raw_items = driver.execute_script(EXTRACT_THREADS_DATA_JS) or []
                new_items_in_round = 0

                for idx, item in enumerate(raw_items):
                    content = item.get("content", "").strip()
                    username = item.get("username", "")
                    author_name = item.get("authorName", "")
                    author_profile_url = item.get("authorProfileUrl", f"https://www.threads.net/@{username}")
                    item_url = item.get("itemUrl", "")
                    time_str = item.get("timeStr", "")
                    likes = item.get("likes", 0)
                    image_urls = item.get("imageUrls", [])
                    is_reply_item = item.get("isReply", False)
                    reply_to = item.get("replyTo", "")

                    if not content:
                        continue

                    # Filter out foreign language content (Chinese, Japanese, Korean...)
                    if not is_valid_viet_eng_content(content):
                        continue
                    content = clean_to_viet_eng(content)
                    if not content or len(content) < 2:
                        continue

                    # First item on page is typically the main post
                    if not main_post_saved:
                        analysis = toxic_engine.analyze(content)
                        post_model = PostModel(
                            id=main_post_id,
                            url=canonical_url,
                            author_username=username,
                            author_name=author_name,
                            author_profile_url=author_profile_url,
                            content=content,
                            posted_at=time_str,
                            likes=likes,
                            image_urls=image_urls,
                            is_toxic=analysis.is_toxic,
                            toxic_score=analysis.score,
                            severity_vi=analysis.severity_vi,
                            review_status=analysis.review_status,
                            review_status_vi=analysis.review_status_vi,
                            has_emoji_slang=analysis.has_emoji_slang,
                            matched_words=analysis.matched_words,
                            matched_emojis=analysis.matched_emojis,
                            categories=analysis.category_names,
                            session_id=session_id
                        )
                        db_manager.upsert_post(post_model)
                        main_post_saved = True
                        scraped_posts += 1
                        seen_ids.add(content)
                        continue

                    # Subsequent items are comments
                    comment_id = generate_item_id("cmt", item_url, content, username)
                    if comment_id in seen_ids or content in seen_ids:
                        continue

                    seen_ids.add(comment_id)
                    seen_ids.add(content)

                    has_down_connector = item.get("hasDownConnector", False)

                    # Determine generation / hierarchy (f0, f1, f2, f3, reply_level)
                    if current_thread_open:
                        is_reply_item = True
                        current_level += 1
                        reply_level = current_level
                        parent_comment_id = current_parent_comment_id

                        if current_level == 1:
                            current_f1 = content
                            current_f1_author = username
                            f0 = current_f0
                            f1 = current_f1
                            f2 = ""
                            f3 = ""
                            comment_type_vi = "Bình luận con (F1)"
                        elif current_level == 2:
                            current_f2 = content
                            current_f2_author = username
                            f0 = current_f0
                            f1 = current_f1
                            f2 = current_f2
                            f3 = ""
                            comment_type_vi = "Bình luận con (F2)"
                        elif current_level == 3:
                            current_f3 = content
                            f0 = current_f0
                            f1 = current_f1
                            f2 = current_f2
                            f3 = current_f3
                            comment_type_vi = "Bình luận con (F3)"
                        else:
                            # Level > 3: User strictly only wants up to F3!
                            # Skip comments beyond F3
                            if not has_down_connector:
                                current_thread_open = False
                            continue

                        scraped_child_comments += 1
                        if not has_down_connector:
                            current_thread_open = False
                    else:
                        if is_reply_item or reply_to:
                            scraped_child_comments += 1
                            current_level = 1
                            reply_level = 1
                            parent_comment_id = current_parent_comment_id
                            current_f1 = content
                            f0 = current_f0
                            f1 = current_f1
                            f2 = ""
                            f3 = ""
                            comment_type_vi = "Bình luận con (F1)"
                            if has_down_connector:
                                current_thread_open = True
                            else:
                                current_thread_open = False
                        else:
                            scraped_root_comments += 1
                            current_f0 = content
                            current_f0_author = username
                            current_f1 = ""
                            current_f1_author = ""
                            current_f2 = ""
                            current_f2_author = ""
                            current_f3 = ""
                            current_level = 0
                            reply_level = 0
                            is_reply_item = False
                            parent_comment_id = ""
                            current_parent_comment_id = comment_id
                            comment_type_vi = "Bình luận gốc"
                            f0 = ""
                            f1 = ""
                            f2 = ""
                            f3 = ""
                            if has_down_connector:
                                current_thread_open = True
                            else:
                                current_thread_open = False

                    new_items_in_round += 1
                    scraped_comments += 1

                    # Run Toxic Analysis (Words + Slang + Emojis)
                    analysis = toxic_engine.analyze(content)
                    if analysis.is_toxic:
                        toxic_comments += 1
                        logger.warning(f"[TOXIC COMMENT] @{username}: {content[:60]}... -> {analysis.matched_words} {analysis.matched_emojis}")

                    comment_model = CommentModel(
                        id=comment_id,
                        post_id=main_post_id,
                        post_url=canonical_url,
                        comment_url=item_url,
                        author_username=username,
                        author_name=author_name,
                        author_profile_url=author_profile_url,
                        content=content,
                        posted_at=time_str,
                        likes=likes,
                        reply_to=reply_to,
                        is_reply=is_reply_item,
                        parent_comment_id=parent_comment_id,
                        comment_type_vi=comment_type_vi,
                        f0=f0,
                        f1=f1,
                        f2=f2,
                        f3=f3,
                        reply_level=reply_level,
                        image_urls=image_urls,
                        is_toxic=analysis.is_toxic,
                        toxic_score=analysis.score,
                        severity_vi=analysis.severity_vi,
                        review_status=analysis.review_status,
                        review_status_vi=analysis.review_status_vi,
                        has_emoji_slang=analysis.has_emoji_slang,
                        matched_words=analysis.matched_words,
                        matched_emojis=analysis.matched_emojis,
                        categories=analysis.category_names,
                        session_id=session_id
                    )
                    db_manager.upsert_comment(comment_model)

                    # Trigger progress callback
                    if progress_callback:
                        latest_info = {
                            "username": username,
                            "content": content,
                            "is_toxic": analysis.is_toxic,
                            "score": analysis.score,
                            "severity_vi": analysis.severity_vi,
                            "words": analysis.matched_words,
                            "emojis": analysis.matched_emojis,
                            "categories": analysis.category_names,
                            "is_reply": is_reply_item,
                            "reply_to": reply_to,
                            "comment_type_vi": comment_type_vi
                        }
                        target_str = "∞" if is_unlimited else str(max_comments)
                        status_msg = f"Đã thu thập: {scraped_comments}/{target_str} bình luận (Gốc: {scraped_root_comments}, Con: {scraped_child_comments}) | Độc hại: {toxic_comments}"
                        progress_callback(scraped_comments, 0 if is_unlimited else max_comments, status_msg, latest_info)

                    if not is_unlimited and scraped_comments >= max_comments:
                        break

                # Check for Meta login wall popup
                login_wall_hit = False
                try:
                    login_wall_hit = bool(driver.execute_script(CHECK_LOGIN_WALL_JS))
                except Exception:
                    pass

                if login_wall_hit:
                    logger.warning("[LOGIN WALL] Phát hiện hộp thoại yêu cầu đăng nhập của Threads/Meta.")

                if new_items_in_round == 0:
                    no_new_data_count += 1
                    if login_wall_hit and no_new_data_count >= 2:
                        warning_msg = (
                            f"⚠️ Đã chạm tường đăng nhập của Meta Threads (~{scraped_comments} bình luận). "
                            "Meta giới hạn khách chưa đăng nhập ở khoảng 20 bình luận gốc. "
                            "Vui lòng dùng tính năng 'Đăng nhập Threads' (Lưu phiên vào data/chrome_profile) để cào toàn bộ 1.3K+ bình luận."
                        )
                        logger.warning(warning_msg)
                        if progress_callback:
                            progress_callback(scraped_comments, 0 if is_unlimited else max_comments, warning_msg, None)
                        break

                    if no_new_data_count >= 5:
                        logger.info("Không có bình luận mới sau 5 lần cuộn, hoàn tất cào.")
                        break
                else:
                    no_new_data_count = 0

                # Scroll down using targeted container scroll script
                try:
                    driver.execute_script(SCROLL_FEED_JS)
                except Exception:
                    driver.execute_script("window.scrollBy(0, 1400);")

                time.sleep(scroll_delay)
                current_scroll += 1

            total_scraped = scraped_posts + scraped_comments
            db_manager.update_session(session_id, total_scraped, toxic_comments, "completed")
            logger.info(f"Crawl completed! Scraped: {total_scraped}, Root: {scraped_root_comments}, Child: {scraped_child_comments}, Toxic: {toxic_comments}")

            return {
                "session_id": session_id,
                "target": post_url,
                "posts_count": scraped_posts,
                "comments_count": scraped_comments,
                "root_comments_count": scraped_root_comments,
                "child_comments_count": scraped_child_comments,
                "toxic_comments_count": toxic_comments,
                "login_wall_hit": login_wall_hit,
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Error during crawl: {e}", exc_info=True)
            db_manager.update_session(session_id, scraped_comments, toxic_comments, "failed")
            return {
                "session_id": session_id,
                "target": post_url,
                "comments_count": scraped_comments,
                "toxic_comments_count": toxic_comments,
                "status": "error",
                "error": str(e)
            }
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    def crawl_search_query(
        self,
        query: str,
        limit: Optional[int] = 30,
        scroll_delay: float = DEFAULT_SCROLL_DELAY,
        progress_callback: Optional[Callable[[int, int, str, Optional[Dict]], None]] = None,
        stop_check: Optional[Callable[[], bool]] = None
    ) -> Dict[str, Any]:
        """
        Crawl Threads search page for controversial queries, drama keywords, or specific slang.
        limit: None hoặc 0 nghĩa là KHÔNG GIỚI HẠN.
        """
        session_id = f"search_{uuid.uuid4().hex[:8]}"
        search_url = f"https://www.threads.net/search?q={query}"
        db_manager.create_session(session_id, query, "search")

        is_unlimited = (limit is None or limit <= 0)
        driver = None
        scraped_posts = 0
        toxic_posts = 0
        seen_ids = set()

        try:
            logger.info(f"Starting search crawl for query: '{query}' (Unlimited: {is_unlimited})")
            if progress_callback:
                progress_callback(0, 0 if is_unlimited else limit, f"Tìm kiếm Threads với từ khóa: {query}...", None)

            driver = BrowserManager.get_driver(headless=self.headless)
            driver.get(search_url)
            time.sleep(4)

            current_scroll = 0
            max_scrolls = 100000 if is_unlimited else max(5, (limit or 30) // 4)
            no_new_data_count = 0

            while current_scroll < max_scrolls:
                if stop_check and stop_check():
                    logger.info("Nhận tín hiệu dừng tìm kiếm từ người dùng. Đang lưu dữ liệu...")
                    break

                if not is_unlimited and scraped_posts >= limit:
                    break

                try:
                    driver.execute_script(EXPAND_MORE_BUTTONS_JS)
                except Exception:
                    pass

                raw_items = driver.execute_script(EXTRACT_THREADS_DATA_JS) or []
                new_items_in_round = 0

                for item in raw_items:
                    content = item.get("content", "").strip()
                    username = item.get("username", "")
                    author_name = item.get("authorName", "")
                    author_profile_url = item.get("authorProfileUrl", f"https://www.threads.net/@{username}")
                    item_url = item.get("itemUrl", "")
                    time_str = item.get("timeStr", "")
                    likes = item.get("likes", 0)
                    image_urls = item.get("imageUrls", [])

                    if not content or content in seen_ids:
                        continue

                    # Filter out foreign language content (Chinese, Japanese, Korean...)
                    if not is_valid_viet_eng_content(content):
                        continue
                    content = clean_to_viet_eng(content)
                    if not content or len(content) < 2:
                        continue

                    post_id = generate_item_id("post_search", item_url, content, username)
                    if post_id in seen_ids or content in seen_ids:
                        continue

                    seen_ids.add(post_id)
                    seen_ids.add(content)
                    new_items_in_round += 1
                    scraped_posts += 1

                    analysis = toxic_engine.analyze(content)
                    if analysis.is_toxic:
                        toxic_posts += 1

                    post_model = PostModel(
                        id=post_id,
                        url=item_url or search_url,
                        author_username=username,
                        author_name=author_name,
                        author_profile_url=author_profile_url,
                        content=content,
                        posted_at=time_str,
                        likes=likes,
                        image_urls=image_urls,
                        is_toxic=analysis.is_toxic,
                        toxic_score=analysis.score,
                        severity_vi=analysis.severity_vi,
                        review_status=analysis.review_status,
                        review_status_vi=analysis.review_status_vi,
                        has_emoji_slang=analysis.has_emoji_slang,
                        matched_words=analysis.matched_words,
                        matched_emojis=analysis.matched_emojis,
                        categories=analysis.category_names,
                        session_id=session_id
                    )
                    db_manager.upsert_post(post_model)

                    if progress_callback:
                        latest_info = {
                            "username": username,
                            "content": content,
                            "is_toxic": analysis.is_toxic,
                            "score": analysis.score,
                            "severity_vi": analysis.severity_vi,
                            "words": analysis.matched_words,
                            "emojis": analysis.matched_emojis,
                            "categories": analysis.category_names
                        }
                        target_str = "∞" if is_unlimited else str(limit)
                        status_msg = f"Đã thu thập: {scraped_posts}/{target_str} bài đăng (Độc hại: {toxic_posts})"
                        progress_callback(scraped_posts, 0 if is_unlimited else limit, status_msg, latest_info)

                    if not is_unlimited and scraped_posts >= limit:
                        break

                if new_items_in_round == 0:
                    no_new_data_count += 1
                    if no_new_data_count >= 5:
                        logger.info("Không có bài viết mới sau 5 lần cuộn, hoàn tất tìm kiếm.")
                        break
                else:
                    no_new_data_count = 0

                try:
                    driver.execute_script(SCROLL_FEED_JS)
                except Exception:
                    driver.execute_script("window.scrollBy(0, 1200);")
                time.sleep(scroll_delay)
                current_scroll += 1

            db_manager.update_session(session_id, scraped_posts, toxic_posts, "completed")
            return {
                "session_id": session_id,
                "target": query,
                "posts_count": scraped_posts,
                "toxic_posts_count": toxic_posts,
                "status": "success"
            }
        except Exception as e:
            logger.error(f"Error during search crawl: {e}", exc_info=True)
            db_manager.update_session(session_id, scraped_posts, toxic_posts, "failed")
            return {"status": "error", "error": str(e)}
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
