import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Union, Tuple
import pandas as pd
from datetime import datetime
from contextlib import contextmanager

from config.settings import DB_PATH
from src.database.models import PostModel, CommentModel, CrawlSessionModel
from src.detector.text_normalizer import is_valid_viet_eng_content, clean_to_viet_eng, clean_ui_artifacts
from src.utils.logger import logger

class DatabaseManager:
    """Manages SQLite storage, indexing, and categorized comment exports for Threads toxic data."""

    def __init__(self, db_path: Optional[Union[Path, str]] = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            yield conn
        finally:
            conn.close()

    def _run_migrations(self, cursor: sqlite3.Cursor):
        """Auto-add new detailed and classification columns to existing tables."""
        # Posts migrations
        existing_post_cols = [r[1] for r in cursor.execute("PRAGMA table_info(posts);").fetchall()]
        post_col_defs = {
            "author_profile_url": "TEXT",
            "reply_to": "TEXT",
            "image_urls": "TEXT",
            "severity_vi": "TEXT DEFAULT 'Trong sạch'",
            "review_status": "TEXT DEFAULT 'clean'",
            "review_status_vi": "TEXT DEFAULT 'Trong sạch'",
            "has_emoji_slang": "BOOLEAN DEFAULT 0",
            "matched_emojis": "TEXT"
        }
        for col, col_type in post_col_defs.items():
            if col not in existing_post_cols:
                try:
                    cursor.execute(f"ALTER TABLE posts ADD COLUMN {col} {col_type};")
                except Exception:
                    pass

        # Comments migrations
        existing_comment_cols = [r[1] for r in cursor.execute("PRAGMA table_info(comments);").fetchall()]
        comment_col_defs = {
            "author_profile_url": "TEXT",
            "reply_to": "TEXT",
            "is_reply": "INTEGER DEFAULT 0",
            "parent_comment_id": "TEXT DEFAULT ''",
            "comment_type_vi": "TEXT DEFAULT 'Bình luận gốc'",
            "image_urls": "TEXT",
            "severity_vi": "TEXT DEFAULT 'Trong sạch'",
            "review_status": "TEXT DEFAULT 'clean'",
            "review_status_vi": "TEXT DEFAULT 'Trong sạch'",
            "has_emoji_slang": "BOOLEAN DEFAULT 0",
            "matched_emojis": "TEXT",
            "user_review": "TEXT DEFAULT ''",
            "user_review_vi": "TEXT DEFAULT ''",
            "user_score": "REAL",
            "user_keywords": "TEXT DEFAULT '[]'",
            "is_user_reviewed": "INTEGER DEFAULT 0",
            "user_reviewed_at": "TEXT DEFAULT ''",
            "f0": "TEXT DEFAULT ''",
            "f1": "TEXT DEFAULT ''",
            "f2": "TEXT DEFAULT ''",
            "f3": "TEXT DEFAULT ''",
            "reply_level": "INTEGER DEFAULT 0"
        }
        for col, col_type in comment_col_defs.items():
            if col not in existing_comment_cols:
                try:
                    cursor.execute(f"ALTER TABLE comments ADD COLUMN {col} {col_type};")
                except Exception:
                    pass

        # Ensure performance indexes exist on existing DBs
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_url ON posts(url);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_user_reviewed ON comments(is_user_reviewed);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_scraped ON comments(scraped_at);")
        except Exception:
            pass

    def init_db(self):
        """Create tables and indexes if they do not exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Crawl sessions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS crawl_sessions (
                    id TEXT PRIMARY KEY,
                    target TEXT NOT NULL,
                    scrape_type TEXT NOT NULL,
                    total_scraped INTEGER DEFAULT 0,
                    total_toxic INTEGER DEFAULT 0,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT DEFAULT 'running'
                )
            """)

            # Posts
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    author_username TEXT,
                    author_name TEXT,
                    author_profile_url TEXT,
                    content TEXT,
                    posted_at TEXT,
                    likes INTEGER DEFAULT 0,
                    replies_count INTEGER DEFAULT 0,
                    reply_to TEXT,
                    image_urls TEXT,
                    is_toxic BOOLEAN DEFAULT 0,
                    toxic_score REAL DEFAULT 0.0,
                    severity_vi TEXT DEFAULT 'Trong sạch',
                    review_status TEXT DEFAULT 'clean',
                    review_status_vi TEXT DEFAULT 'Trong sạch',
                    has_emoji_slang BOOLEAN DEFAULT 0,
                    matched_words TEXT,
                    matched_emojis TEXT,
                    categories TEXT,
                    session_id TEXT,
                    scraped_at TEXT
                )
            """)

            # Comments
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS comments (
                    id TEXT PRIMARY KEY,
                    post_id TEXT NOT NULL,
                    post_url TEXT NOT NULL,
                    comment_url TEXT,
                    author_username TEXT,
                    author_name TEXT,
                    author_profile_url TEXT,
                    content TEXT,
                    posted_at TEXT,
                    likes INTEGER DEFAULT 0,
                    reply_to TEXT,
                    is_reply INTEGER DEFAULT 0,
                    parent_comment_id TEXT DEFAULT '',
                    comment_type_vi TEXT DEFAULT 'Bình luận gốc',
                    f0 TEXT DEFAULT '',
                    f1 TEXT DEFAULT '',
                    f2 TEXT DEFAULT '',
                    f3 TEXT DEFAULT '',
                    reply_level INTEGER DEFAULT 0,
                    image_urls TEXT,
                    is_toxic BOOLEAN DEFAULT 0,
                    toxic_score REAL DEFAULT 0.0,
                    severity_vi TEXT DEFAULT 'Trong sạch',
                    review_status TEXT DEFAULT 'clean',
                    review_status_vi TEXT DEFAULT 'Trong sạch',
                    has_emoji_slang BOOLEAN DEFAULT 0,
                    matched_words TEXT,
                    matched_emojis TEXT,
                    categories TEXT,
                    session_id TEXT,
                    scraped_at TEXT
                )
            """)

            # Run migrations for existing DBs
            self._run_migrations(cursor)

            # Indexes for ultra-fast filtering
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_toxic ON posts(is_toxic);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_toxic ON comments(is_toxic);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_review_status ON comments(review_status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_username);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_author ON comments(author_username);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_url ON posts(url);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_user_reviewed ON comments(is_user_reviewed);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_scraped ON comments(scraped_at);")

            conn.commit()

            conn.commit()

    def upsert_post(self, post: PostModel) -> bool:
        """Insert or update a post with detailed fields and review status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO posts (
                    id, url, author_username, author_name, author_profile_url,
                    content, posted_at, likes, replies_count, reply_to, image_urls,
                    is_toxic, toxic_score, severity_vi, review_status, review_status_vi,
                    has_emoji_slang, matched_words, matched_emojis, categories, session_id, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    content=excluded.content,
                    likes=excluded.likes,
                    replies_count=excluded.replies_count,
                    reply_to=excluded.reply_to,
                    image_urls=excluded.image_urls,
                    is_toxic=excluded.is_toxic,
                    toxic_score=excluded.toxic_score,
                    severity_vi=excluded.severity_vi,
                    review_status=excluded.review_status,
                    review_status_vi=excluded.review_status_vi,
                    has_emoji_slang=excluded.has_emoji_slang,
                    matched_words=excluded.matched_words,
                    matched_emojis=excluded.matched_emojis,
                    categories=excluded.categories
            """, (
                post.id, post.url, post.author_username, post.author_name,
                post.author_profile_url or f"https://www.threads.net/@{post.author_username}",
                post.content, post.posted_at, post.likes, post.replies_count,
                post.reply_to or "", json.dumps(post.image_urls, ensure_ascii=False),
                1 if post.is_toxic else 0, post.toxic_score, post.severity_vi,
                post.review_status, post.review_status_vi,
                1 if post.has_emoji_slang else 0,
                json.dumps(post.matched_words, ensure_ascii=False),
                json.dumps(post.matched_emojis, ensure_ascii=False),
                json.dumps(post.categories, ensure_ascii=False),
                post.session_id, post.scraped_at
            ))
            conn.commit()
            return True

    def upsert_comment(self, comment: CommentModel) -> bool:
        """Insert or update a comment with detailed fields, replies and review status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO comments (
                    id, post_id, post_url, comment_url, author_username, author_name,
                    author_profile_url, content, posted_at, likes, reply_to,
                    is_reply, parent_comment_id, comment_type_vi,
                    f0, f1, f2, f3, reply_level,
                    image_urls,
                    is_toxic, toxic_score, severity_vi, review_status, review_status_vi,
                    has_emoji_slang, matched_words, matched_emojis, categories, session_id, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    content=excluded.content,
                    likes=excluded.likes,
                    reply_to=excluded.reply_to,
                    is_reply=excluded.is_reply,
                    parent_comment_id=excluded.parent_comment_id,
                    comment_type_vi=excluded.comment_type_vi,
                    f0=excluded.f0,
                    f1=excluded.f1,
                    f2=excluded.f2,
                    f3=excluded.f3,
                    reply_level=excluded.reply_level,
                    image_urls=excluded.image_urls,
                    is_toxic=excluded.is_toxic,
                    toxic_score=excluded.toxic_score,
                    severity_vi=excluded.severity_vi,
                    review_status=excluded.review_status,
                    review_status_vi=excluded.review_status_vi,
                    has_emoji_slang=excluded.has_emoji_slang,
                    matched_words=excluded.matched_words,
                    matched_emojis=excluded.matched_emojis,
                    categories=excluded.categories
            """, (
                comment.id, comment.post_id, comment.post_url, comment.comment_url,
                comment.author_username, comment.author_name,
                comment.author_profile_url or f"https://www.threads.net/@{comment.author_username}",
                comment.content, comment.posted_at, comment.likes,
                comment.reply_to or "",
                1 if comment.is_reply else 0,
                comment.parent_comment_id or "",
                comment.comment_type_vi or ("Bình luận con (Phản hồi)" if comment.is_reply else "Bình luận gốc"),
                comment.f0 or "",
                comment.f1 or "",
                comment.f2 or "",
                comment.f3 or "",
                comment.reply_level or 0,
                json.dumps(comment.image_urls, ensure_ascii=False),
                1 if comment.is_toxic else 0, comment.toxic_score, comment.severity_vi,
                comment.review_status, comment.review_status_vi,
                1 if comment.has_emoji_slang else 0,
                json.dumps(comment.matched_words, ensure_ascii=False),
                json.dumps(comment.matched_emojis, ensure_ascii=False),
                json.dumps(comment.categories, ensure_ascii=False),
                comment.session_id, comment.scraped_at
            ))
            conn.commit()
            return True

    def create_session(self, session_id: str, target: str, scrape_type: str):
        """Create a new crawl session record."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO crawl_sessions (id, target, scrape_type, started_at, status)
                VALUES (?, ?, ?, ?, 'running')
            """, (session_id, target, scrape_type, datetime.now().isoformat()))
            conn.commit()

    def update_session(self, session_id: str, total_scraped: int, total_toxic: int, status: str = "completed"):
        """Update crawl session upon finish."""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE crawl_sessions
                SET total_scraped = ?, total_toxic = ?, status = ?, completed_at = ?
                WHERE id = ?
            """, (total_scraped, total_toxic, status, datetime.now().isoformat(), session_id))
            conn.commit()

    def get_stats(self) -> Dict[str, Any]:
        """Get aggregate system statistics with classification counts."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            total_posts = cursor.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
            toxic_posts = cursor.execute("SELECT COUNT(*) FROM posts WHERE is_toxic = 1").fetchone()[0]
            total_comments = cursor.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
            toxic_comments = cursor.execute("SELECT COUNT(*) FROM comments WHERE is_toxic = 1").fetchone()[0]

            # Classification tiers for comments
            bad_comments = cursor.execute("SELECT COUNT(*) FROM comments WHERE review_status = 'bad'").fetchone()[0]
            ambiguous_comments = cursor.execute("SELECT COUNT(*) FROM comments WHERE review_status = 'ambiguous'").fetchone()[0]
            clean_comments = cursor.execute("SELECT COUNT(*) FROM comments WHERE review_status = 'clean'").fetchone()[0]

            total_items = total_posts + total_comments
            total_toxic = toxic_posts + toxic_comments
            rate = round((total_toxic / total_items * 100), 2) if total_items > 0 else 0.0

            # Count root comments vs child replies
            total_root_comments = cursor.execute("SELECT COUNT(*) FROM comments WHERE is_reply = 0 OR is_reply IS NULL").fetchone()[0]
            total_child_comments = cursor.execute("SELECT COUNT(*) FROM comments WHERE is_reply = 1").fetchone()[0]

            sessions = cursor.execute("SELECT * FROM crawl_sessions ORDER BY started_at DESC LIMIT 5").fetchall()

            return {
                "total_posts": total_posts,
                "toxic_posts": toxic_posts,
                "total_comments": total_comments,
                "total_root_comments": total_root_comments,
                "total_child_comments": total_child_comments,
                "toxic_comments": toxic_comments,
                "bad_comments": bad_comments,
                "ambiguous_comments": ambiguous_comments,
                "clean_comments": clean_comments,
                "total_items": total_items,
                "total_toxic": total_toxic,
                "toxic_rate_percent": rate,
                "recent_sessions": [dict(s) for s in sessions]
            }

    def get_existing_comment_hashes(self) -> tuple[set, set]:
        """
        Fast retrieval of existing comment IDs and normalized contents from database.
        Returns (set_of_ids, set_of_normalized_contents).
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute("SELECT id, content FROM comments").fetchall()
            ids = {r[0] for r in rows if r[0]}
            contents = {" ".join(str(r[1]).split()).lower() for r in rows if r[1]}
            return ids, contents

    def get_existing_post_hashes(self) -> tuple[set, set, set]:
        """
        Fast retrieval of existing post IDs, URLs, and normalized contents.
        Returns (set_of_ids, set_of_urls, set_of_normalized_contents).
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute("SELECT id, url, content FROM posts").fetchall()
            ids = {r[0] for r in rows if r[0]}
            urls = {r[1].strip() for r in rows if r[1]}
            contents = {" ".join(str(r[2]).split()).lower() for r in rows if r[2]}
            return ids, urls, contents

    def comment_exists(self, comment_id: str = "", content: str = "") -> bool:
        """Check if a comment already exists by ID or exact/normalized content."""
        if not comment_id and not content:
            return False
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if comment_id:
                res = cursor.execute("SELECT 1 FROM comments WHERE id = ? LIMIT 1", (comment_id,)).fetchone()
                if res:
                    return True
            if content:
                norm = " ".join(str(content).split()).lower()
                res = cursor.execute("SELECT 1 FROM comments WHERE LOWER(TRIM(content)) = ? LIMIT 1", (norm,)).fetchone()
                if res:
                    return True
            return False

    def post_exists(self, post_id: str = "", url: str = "", content: str = "") -> bool:
        """Check if a post already exists by ID, URL, or content."""
        if not post_id and not url and not content:
            return False
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if post_id:
                res = cursor.execute("SELECT 1 FROM posts WHERE id = ? LIMIT 1", (post_id,)).fetchone()
                if res:
                    return True
            if url:
                res = cursor.execute("SELECT 1 FROM posts WHERE url = ? LIMIT 1", (url.strip(),)).fetchone()
                if res:
                    return True
            if content:
                norm = " ".join(str(content).split()).lower()
                res = cursor.execute("SELECT 1 FROM posts WHERE LOWER(TRIM(content)) = ? LIMIT 1", (norm,)).fetchone()
                if res:
                    return True
            return False

    def get_comments_df(self, toxic_only: bool = False, review_status: Optional[str] = None, limit: Optional[int] = None) -> pd.DataFrame:
        """Fetch comments into a pandas DataFrame with review_status filter. limit=None means unlimited."""
        with self.get_connection() as conn:
            query = "SELECT * FROM comments WHERE 1=1"
            params = []
            if review_status:
                query += " AND review_status = ?"
                params.append(review_status)
            elif toxic_only:
                query += " AND is_toxic = 1"
            if limit is not None and limit > 0:
                query += f" ORDER BY scraped_at DESC LIMIT {limit}"
            else:
                query += " ORDER BY scraped_at DESC"
            df = pd.read_sql_query(query, conn, params=params)
            return df

    def get_posts_df(self, toxic_only: bool = False, review_status: Optional[str] = None, limit: Optional[int] = None) -> pd.DataFrame:
        """Fetch posts into a pandas DataFrame. limit=None means unlimited."""
        with self.get_connection() as conn:
            query = "SELECT * FROM posts WHERE 1=1"
            params = []
            if review_status:
                query += " AND review_status = ?"
                params.append(review_status)
            elif toxic_only:
                query += " AND is_toxic = 1"
            if limit is not None and limit > 0:
                query += f" ORDER BY scraped_at DESC LIMIT {limit}"
            else:
                query += " ORDER BY scraped_at DESC"
            df = pd.read_sql_query(query, conn, params=params)
            return df

    def get_detailed_export_df(self, table_type: str = "comments", toxic_only: bool = False, limit: Optional[int] = None, deduplicate: bool = True) -> pd.DataFrame:
        """Backward-compatible helper calling get_comments_export_df with full links."""
        filter_status = "toxic_only" if toxic_only else "all"
        return self.get_comments_export_df(filter_status=filter_status, include_links=True, limit=limit, deduplicate=deduplicate)

    def get_comments_export_df(
        self,
        filter_status: str = "all",
        filter_comment_type: str = "all",
        include_links: bool = False,
        limit: Optional[int] = None,
        viet_eng_only: bool = True,
        min_length: Optional[int] = 2,
        max_length: Optional[int] = 300,
        deduplicate: bool = True
    ) -> pd.DataFrame:
        """
        Query comments specifically for focused export:
        - filter_status:
            * 'bad': Chỉ lấy các bình luận xấu luôn (toxic_score >= 0.5)
            * 'ambiguous': Bình luận nghi ngờ (0.15 <= toxic_score < 0.5)
            * 'clean': Bình luận trong sạch (toxic_score < 0.15)
            * 'all' hoặc None: Toàn bộ bình luận để người dùng tự tổng hợp
        - filter_comment_type:
            * 'root': Chỉ lấy bình luận gốc
            * 'reply': Chỉ lấy bình luận con (phản hồi)
            * 'all' hoặc None: Cả bình luận gốc và bình luận con
        - Default includes ONLY comment text and classification (no link clutter)
        - If include_links=True, adds Post URL, Comment URL, Profile URL, IDs, Parent Comment ID.
        - limit: None hoặc 0 để lấy toàn bộ dữ liệu không giới hạn.
        - viet_eng_only: Lọc bỏ tiếng Trung, Nhật, Hàn... và làm sạch ký tự.
        - min_length / max_length: Lọc bỏ bình luận quá ngắn (< 2) và quá dài (> 300).
        - deduplicate: Loại bỏ bình luận trùng lặp nội dung khi xuất.
        """
        with self.get_connection() as conn:
            query = "SELECT * FROM comments WHERE 1=1"
            params = []
            if filter_status == "bad":
                query += " AND (review_status = 'bad' OR toxic_score >= 0.5)"
            elif filter_status == "ambiguous":
                query += " AND (review_status = 'ambiguous' OR (toxic_score >= 0.15 AND toxic_score < 0.5))"
            elif filter_status == "clean":
                query += " AND (review_status = 'clean' OR toxic_score < 0.15)"
            elif filter_status == "toxic_only":
                query += " AND is_toxic = 1"

            if filter_comment_type == "root":
                query += " AND (is_reply = 0 OR is_reply IS NULL)"
            elif filter_comment_type == "reply":
                query += " AND is_reply = 1"

            if limit is not None and limit > 0:
                query += f" ORDER BY scraped_at DESC LIMIT {limit}"
            else:
                query += " ORDER BY scraped_at DESC"
            df = pd.read_sql_query(query, conn, params=params)
            if df.empty:
                return df

            if viet_eng_only:
                df = df[df["content"].apply(is_valid_viet_eng_content)].copy()
                df["content"] = df["content"].apply(clean_to_viet_eng)
                if df.empty:
                    return df

            # Filter by comment length (default: 2 to 300 characters, ignoring < 2 like 'ừ', 'ờ' and > 300)
            if min_length is not None or max_length is not None:
                def length_filter(val):
                    cleaned = " ".join(str(val or "").split())
                    val_len = len(cleaned)
                    if min_length is not None and val_len < min_length:
                        return False
                    if max_length is not None and val_len > max_length:
                        return False
                    return True
                df = df[df["content"].apply(length_filter)].copy()
                if df.empty:
                    return df

            # Deduplicate by normalized content
            if deduplicate and not df.empty and "content" in df.columns:
                sort_cols = [c for c in ["is_user_reviewed", "toxic_score"] if c in df.columns]
                if sort_cols:
                    df = df.sort_values(by=sort_cols, ascending=[False] * len(sort_cols))
                df["_norm_content_dedup"] = df["content"].apply(lambda s: " ".join(str(s or "").split()).lower())
                df = df.drop_duplicates(subset=["_norm_content_dedup"], keep="first")
                df = df.drop(columns=["_norm_content_dedup"])
                if df.empty:
                    return df

            # Helper to format JSON lists to readable comma strings
            def format_list(val):
                if not val:
                    return ""
                try:
                    data = json.loads(val)
                    if isinstance(data, list):
                        return ", ".join(str(x) for x in data)
                    return str(data)
                except Exception:
                    return str(val)

            df["matched_words_str"] = df["matched_words"].apply(format_list)
            df["matched_emojis_str"] = df["matched_emojis"].apply(format_list)
            df["categories_str"] = df["categories"].apply(format_list)
            df["image_urls_str"] = df["image_urls"].apply(format_list)

            # Ensure review_status_vi is populated
            def resolve_status_vi(row):
                status = row.get("review_status", "")
                score = row.get("toxic_score", 0.0)
                if status == "bad" or score >= 0.5:
                    return "Xấu luôn (Rõ ràng)"
                elif status == "ambiguous" or score >= 0.15:
                    return "Chưa rõ (Nghi ngờ / Cần duyệt lại)"
                else:
                    return "Trong sạch"

            df["review_status_vi"] = df.apply(resolve_status_vi, axis=1)

            # Ensure comment_type_vi is populated
            def resolve_comment_type(row):
                is_r = row.get("is_reply", 0)
                c_type = str(row.get("comment_type_vi", ""))
                if is_r == 1 or is_r is True or "con" in c_type.lower() or "phản hồi" in c_type.lower():
                    return "Bình luận con (Phản hồi)"
                return "Bình luận gốc"

            df["comment_type_vi"] = df.apply(resolve_comment_type, axis=1)

            # Clean focused comment columns - f0 f1 f2 f3 placed before content
            core_columns = [
                ("author_username", "Tài khoản tác giả (@Username)"),
                ("author_name", "Tên hiển thị (Display Name)"),
                ("comment_type_vi", "Loại bình luận (Gốc / Bình luận con)"),
                ("reply_to", "Phản hồi cho (@Reply To)"),
                ("f0", "f0"),
                ("f1", "f1"),
                ("f2", "f2"),
                ("f3", "f3"),
                ("content", "Nội dung bình luận (Comment Text)"),
                ("review_status_vi", "Đánh giá phân loại (Review Status)"),
                ("toxic_score", "Điểm độc hại (Toxic Score)"),
                ("severity_vi", "Mức độ nghiêm trọng (Severity)"),
                ("matched_words_str", "Từ lóng / từ xúc phạm phát hiện"),
                ("matched_emojis_str", "Icon / Emoji nhạy cảm"),
                ("categories_str", "Nhóm vi phạm"),
                ("likes", "Lượt thích (Likes)"),
                ("posted_at", "Thời gian đăng (Posted At)")
            ]

            link_columns = [
                ("parent_comment_id", "Mã bình luận cha (Parent Comment ID)"),
                ("post_url", "Link bài viết gốc (Post URL)"),
                ("comment_url", "Link bình luận (Comment URL)"),
                ("author_profile_url", "Link trang cá nhân tác giả (Profile URL)"),
                ("id", "Mã bình luận (Comment ID)"),
                ("post_id", "Mã bài gốc (Post ID)"),
                ("image_urls_str", "Hình ảnh đính kèm (Images)"),
                ("scraped_at", "Thời gian thu thập (Scraped At)")
            ]

            chosen_columns = list(core_columns)
            if include_links:
                chosen_columns.extend(link_columns)

            col_keys = [c[0] for c in chosen_columns if c[0] in df.columns]
            rename_dict = {c[0]: c[1] for c in chosen_columns}

            out_df = df[col_keys].rename(columns=rename_dict)
            # Collapse whitespace across all text columns
            for c in out_df.columns:
                if out_df[c].dtype == object:
                    out_df[c] = out_df[c].apply(lambda s: " ".join(str(s).split()) if s is not None and not pd.isna(s) else "")

            return out_df

    def get_top_toxic_words(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Calculate frequency of detected toxic words across all comments and posts."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            words_freq = {}
            for table in ["posts", "comments"]:
                rows = cursor.execute(f"SELECT matched_words FROM {table} WHERE is_toxic = 1").fetchall()
                for (words_json,) in rows:
                    if words_json:
                        try:
                            words = json.loads(words_json)
                            for w in words:
                                words_freq[w] = words_freq.get(w, 0) + 1
                        except Exception:
                            pass
            sorted_words = sorted(words_freq.items(), key=lambda x: x[1], reverse=True)[:limit]
            return [{"word": w, "count": c} for w, c in sorted_words]

    def get_top_toxic_users(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Find users with the most toxic comments/posts."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT author_username, COUNT(*) as toxic_count
                FROM (
                    SELECT author_username FROM posts WHERE is_toxic = 1 AND author_username != ''
                    UNION ALL
                    SELECT author_username FROM comments WHERE is_toxic = 1 AND author_username != ''
                )
                GROUP BY author_username
                ORDER BY toxic_count DESC
                LIMIT ?
            """
            rows = cursor.execute(query, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def update_user_review(
        self,
        comment_id: str,
        user_review: str,
        user_score: Optional[float] = None,
        user_keywords: Optional[List[str]] = None
    ) -> bool:
        """Update a comment with user's manual evaluation, score, and newly learned keywords."""
        status_vi_map = {
            "bad": "Xấu luôn (Rõ ràng)",
            "ambiguous": "Chưa rõ (Nghi ngờ)",
            "clean": "Trong sạch"
        }
        user_review_vi = status_vi_map.get(user_review, user_review)
        now = datetime.now().isoformat()
        keywords_json = json.dumps(user_keywords or [], ensure_ascii=False)
        is_toxic_flag = 1 if user_review == "bad" else 0

        with self.get_connection() as conn:
            conn.execute("""
                UPDATE comments
                SET user_review = ?,
                    user_review_vi = ?,
                    user_score = COALESCE(?, toxic_score),
                    user_keywords = ?,
                    is_user_reviewed = 1,
                    user_reviewed_at = ?,
                    review_status = ?,
                    review_status_vi = ?,
                    is_toxic = ?
                WHERE id = ?
            """, (
                user_review, user_review_vi, user_score, keywords_json,
                now, user_review, user_review_vi, is_toxic_flag, comment_id
            ))
            conn.commit()
            return True

    def propagate_learned_keywords(self, new_keywords: List[str], engine: Any) -> int:
        """
        Active Learning Auto-Propagation:
        When new toxic keywords/slang are learned from user review,
        re-evaluate all unreviewed comments in the database that contain these keywords.
        Updates is_toxic, toxic_score, severity_vi, review_status, review_status_vi, matched_words, categories.
        Returns the number of comments updated.
        """
        if not new_keywords:
            return 0

        clean_keywords = [k.strip().lower() for k in new_keywords if k and len(k.strip()) >= 2]
        if not clean_keywords:
            return 0

        updated_count = 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute("""
                SELECT id, content FROM comments WHERE is_user_reviewed = 0 OR is_user_reviewed IS NULL
            """).fetchall()

            updates = []
            for row in rows:
                c_id, content = row["id"], row["content"]
                if not content:
                    continue
                content_lower = content.lower()
                if any(kw in content_lower for kw in clean_keywords):
                    analysis = engine.analyze(content)
                    if analysis.is_toxic:
                        updates.append((
                            1,
                            analysis.score,
                            analysis.severity_vi,
                            analysis.review_status,
                            analysis.review_status_vi,
                            json.dumps(analysis.matched_words, ensure_ascii=False),
                            json.dumps(analysis.category_names, ensure_ascii=False),
                            c_id
                        ))

            if updates:
                cursor.executemany("""
                    UPDATE comments
                    SET is_toxic = ?,
                        toxic_score = ?,
                        severity_vi = ?,
                        review_status = ?,
                        review_status_vi = ?,
                        matched_words = ?,
                        categories = ?
                    WHERE id = ?
                """, updates)
                conn.commit()
                updated_count = len(updates)
                logger.info(f"Active Learning Propagated: Updated {updated_count} unreviewed comments matching keywords: {clean_keywords}")

        return updated_count

    def reanalyze_all_unreviewed_comments(self, engine: Any) -> int:
        """
        Re-scan ALL unreviewed comments with the latest dictionary and toxic engine.
        Returns the number of toxic comments detected.
        """
        updated_count = 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute("""
                SELECT id, content FROM comments WHERE is_user_reviewed = 0 OR is_user_reviewed IS NULL
            """).fetchall()

            updates = []
            for row in rows:
                c_id, content = row["id"], row["content"]
                if not content:
                    continue
                analysis = engine.analyze(content)
                updates.append((
                    1 if analysis.is_toxic else 0,
                    analysis.score,
                    analysis.severity_vi,
                    analysis.review_status,
                    analysis.review_status_vi,
                    json.dumps(analysis.matched_words, ensure_ascii=False),
                    json.dumps(analysis.category_names, ensure_ascii=False),
                    c_id
                ))
                if analysis.is_toxic:
                    updated_count += 1

            if updates:
                cursor.executemany("""
                    UPDATE comments
                    SET is_toxic = ?,
                        toxic_score = ?,
                        severity_vi = ?,
                        review_status = ?,
                        review_status_vi = ?,
                        matched_words = ?,
                        categories = ?
                    WHERE id = ?
                """, updates)
                conn.commit()
                logger.info(f"Re-analyzed {len(updates)} unreviewed comments (Found {updated_count} toxic).")

        return updated_count

    def get_review_progress(self) -> Dict[str, Any]:
        """Get overall manual evaluation progress and breakdown."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            total = cursor.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
            reviewed = cursor.execute("SELECT COUNT(*) FROM comments WHERE is_user_reviewed = 1").fetchone()[0]
            unreviewed = total - reviewed
            pct = round((reviewed / total * 100), 1) if total > 0 else 0.0

            user_bad = cursor.execute("SELECT COUNT(*) FROM comments WHERE user_review = 'bad'").fetchone()[0]
            user_ambiguous = cursor.execute("SELECT COUNT(*) FROM comments WHERE user_review = 'ambiguous'").fetchone()[0]
            user_clean = cursor.execute("SELECT COUNT(*) FROM comments WHERE user_review = 'clean'").fetchone()[0]

            return {
                "total": total,
                "reviewed": reviewed,
                "unreviewed": unreviewed,
                "percent": pct,
                "user_bad": user_bad,
                "user_ambiguous": user_ambiguous,
                "user_clean": user_clean
            }

    def count_focus_review_comments(
        self,
        filter_review: str = "unreviewed",
        filter_type: str = "all",
        search_kw: str = ""
    ) -> int:
        """Count comments matching review queue criteria."""
        with self.get_connection() as conn:
            query = "SELECT COUNT(*) FROM comments c WHERE 1=1"
            params = []

            if filter_review == "unreviewed":
                query += " AND (c.is_user_reviewed = 0 OR c.is_user_reviewed IS NULL)"
            elif filter_review == "reviewed":
                query += " AND c.is_user_reviewed = 1"
            elif filter_review == "bad":
                query += " AND (c.review_status = 'bad' OR c.toxic_score >= 0.5)"
            elif filter_review == "ambiguous":
                query += " AND (c.review_status = 'ambiguous' OR (c.toxic_score >= 0.15 AND c.toxic_score < 0.5))"
            elif filter_review == "clean":
                query += " AND (c.review_status = 'clean' OR c.toxic_score < 0.15)"

            if filter_type == "root":
                query += " AND (c.is_reply = 0 OR c.is_reply IS NULL)"
            elif filter_type == "reply":
                query += " AND c.is_reply = 1"

            if search_kw:
                query += " AND (c.content LIKE ? OR c.author_username LIKE ? OR c.matched_words LIKE ?)"
                kw_wildcard = f"%{search_kw}%"
                params.extend([kw_wildcard, kw_wildcard, kw_wildcard])

            cursor = conn.cursor()
            return cursor.execute(query, params).fetchone()[0]

    def get_focus_review_comment_at_index(
        self,
        index: int,
        filter_review: str = "unreviewed",
        filter_type: str = "all",
        search_kw: str = "",
        order_by: str = "newest"
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single comment and its post context at a specific 0-based index."""
        with self.get_connection() as conn:
            query = """
                SELECT 
                    c.id, c.content, c.author_username, c.author_name, c.author_profile_url,
                    c.posted_at, c.likes, c.reply_to, c.is_reply, c.comment_type_vi,
                    c.f0, c.f1, c.f2, c.f3, c.reply_level,
                    c.comment_url, c.post_url, c.post_id,
                    c.is_toxic, c.toxic_score, c.severity_vi, c.review_status, c.review_status_vi,
                    c.has_emoji_slang, c.matched_words, c.matched_emojis, c.categories,
                    c.user_review, c.user_review_vi, c.user_score, c.user_keywords,
                    c.is_user_reviewed, c.user_reviewed_at, c.scraped_at,
                    p.content as post_content, p.categories as post_categories, p.author_username as post_author
                FROM comments c
                LEFT JOIN posts p ON c.post_id = p.id
                WHERE 1=1
            """
            params = []

            if filter_review == "unreviewed":
                query += " AND (c.is_user_reviewed = 0 OR c.is_user_reviewed IS NULL)"
            elif filter_review == "reviewed":
                query += " AND c.is_user_reviewed = 1"
            elif filter_review == "bad":
                query += " AND (c.review_status = 'bad' OR c.toxic_score >= 0.5)"
            elif filter_review == "ambiguous":
                query += " AND (c.review_status = 'ambiguous' OR (c.toxic_score >= 0.15 AND c.toxic_score < 0.5))"
            elif filter_review == "clean":
                query += " AND (c.review_status = 'clean' OR c.toxic_score < 0.15)"

            if filter_type == "root":
                query += " AND (c.is_reply = 0 OR c.is_reply IS NULL)"
            elif filter_type == "reply":
                query += " AND c.is_reply = 1"

            if search_kw:
                query += " AND (c.content LIKE ? OR c.author_username LIKE ? OR c.matched_words LIKE ?)"
                kw_wildcard = f"%{search_kw}%"
                params.extend([kw_wildcard, kw_wildcard, kw_wildcard])

            if order_by == "oldest":
                query += " ORDER BY c.scraped_at ASC"
            elif order_by == "toxic_score_desc":
                query += " ORDER BY c.toxic_score DESC, c.scraped_at DESC"
            elif order_by == "unreviewed_first":
                query += " ORDER BY c.is_user_reviewed ASC, c.scraped_at DESC"
            else:  # newest
                query += " ORDER BY c.scraped_at DESC"

            query += f" LIMIT 1 OFFSET {max(0, int(index))}"
            cursor = conn.cursor()
            row = cursor.execute(query, params).fetchone()
            if not row:
                return None

            item = dict(row)
            def safe_json(val):
                if not val:
                    return []
                try:
                    res = json.loads(val)
                    return res if isinstance(res, list) else [res]
                except Exception:
                    return [val] if val else []

            item["matched_words_list"] = safe_json(item.get("matched_words"))
            item["matched_emojis_list"] = safe_json(item.get("matched_emojis"))
            item["categories_list"] = safe_json(item.get("categories"))
            item["user_keywords_list"] = safe_json(item.get("user_keywords"))
            item["post_categories_list"] = safe_json(item.get("post_categories"))
            return item

    def get_curated_export_df(
        self,
        filter_status: str = "all",
        filter_comment_type: str = "all",
        limit: Optional[int] = None,
        viet_eng_only: bool = True,
        min_length: Optional[int] = 2,
        max_length: Optional[int] = 300,
        deduplicate: bool = True
    ) -> pd.DataFrame:
        """
        Query comments joined with posts, returning the structured requested columns:
        1. Mã ID
        2. Bài viết (Original Post text / Context)
        3. f0 (Bình luận gốc nếu cmt đang xét là reply)
        4. f1 (Reply F1)
        5. f2 (Reply F2)
        6. f3 (Reply F3)
        7. Nội dung (Nội dung bình luận đang xét)
        8. Điểm đánh giá (Score & Level)
        9. Chủ đề bài viết (Post category / topics)
        + Tự đánh giá và Từ lóng mới.
        - viet_eng_only: Lọc bỏ các bình luận tiếng Trung, Nhật, Hàn... và làm sạch ký tự.
        - min_length / max_length: Lọc bỏ các bình luận quá ngắn (< 2 như ừ, ờ) hoặc quá dài (> 300).
        - deduplicate: Loại bỏ bình luận trùng lặp nội dung khi xuất.
        """
        with self.get_connection() as conn:
            query = """
                SELECT 
                    c.id as comment_id,
                    c.content as comment_content,
                    c.f0,
                    c.f1,
                    c.f2,
                    c.f3,
                    c.reply_level,
                    c.is_reply,
                    c.toxic_score,
                    c.severity_vi,
                    c.review_status,
                    c.review_status_vi,
                    c.user_review,
                    c.user_review_vi,
                    c.user_keywords,
                    c.categories as comment_categories,
                    p.content as post_content,
                    p.url as post_url,
                    p.categories as post_categories
                FROM comments c
                LEFT JOIN posts p ON c.post_id = p.id
                WHERE 1=1
            """
            params = []
            if filter_status == "bad":
                query += " AND (c.review_status = 'bad' OR c.toxic_score >= 0.5)"
            elif filter_status == "ambiguous":
                query += " AND (c.review_status = 'ambiguous' OR (c.toxic_score >= 0.15 AND c.toxic_score < 0.5))"
            elif filter_status == "clean":
                query += " AND (c.review_status = 'clean' OR c.toxic_score < 0.15)"
            elif filter_status == "toxic_only":
                query += " AND c.is_toxic = 1"

            if filter_comment_type == "root":
                query += " AND (c.is_reply = 0 OR c.is_reply IS NULL)"
            elif filter_comment_type == "reply":
                query += " AND c.is_reply = 1"

            if limit is not None and limit > 0:
                query += f" ORDER BY c.scraped_at DESC LIMIT {limit}"
            else:
                query += " ORDER BY c.scraped_at DESC"

            df = pd.read_sql_query(query, conn, params=params)
            curated_empty_cols = [
                "Mã ID",
                "Bài viết",
                "f0",
                "f1",
                "f2",
                "f3",
                "Nội dung",
                "Điểm đánh giá",
                "Chủ đề bài viết",
                "Tự đánh giá của bạn (Xấu luôn / Chưa rõ / Trong sạch)",
                "Từ lóng mới bổ sung (nếu có)"
            ]

            if df.empty:
                return pd.DataFrame(columns=curated_empty_cols)

            # Filter out Chinese, Japanese, Korean, and other foreign language content
            if viet_eng_only:
                df = df[df["comment_content"].apply(is_valid_viet_eng_content)].copy()
                if df.empty:
                    return pd.DataFrame(columns=curated_empty_cols)

            # Filter by comment length (default: 2 to 300 characters, ignoring < 2 like 'ừ', 'ờ' and > 300)
            if min_length is not None or max_length is not None:
                def length_filter(val):
                    cleaned = " ".join(str(val or "").split())
                    val_len = len(cleaned)
                    if min_length is not None and val_len < min_length:
                        return False
                    if max_length is not None and val_len > max_length:
                        return False
                    return True
                df = df[df["comment_content"].apply(length_filter)].copy()
                if df.empty:
                    return pd.DataFrame(columns=curated_empty_cols)

            # Deduplicate by normalized content
            if deduplicate and not df.empty and "comment_content" in df.columns:
                sort_cols = [c for c in ["user_review", "toxic_score"] if c in df.columns]
                if sort_cols:
                    df = df.sort_values(by=sort_cols, ascending=[False] * len(sort_cols))
                df["_norm_content_dedup"] = df["comment_content"].apply(lambda s: " ".join(str(s or "").split()).lower())
                df = df.drop_duplicates(subset=["_norm_content_dedup"], keep="first")
                df = df.drop(columns=["_norm_content_dedup"])
                if df.empty:
                    return pd.DataFrame(columns=curated_empty_cols)

            # Helper for formatting topics / categories
            def format_categories(row):
                p_cats = row.get("post_categories")
                cats = []
                if p_cats:
                    try:
                        parsed = json.loads(p_cats)
                        if isinstance(parsed, list):
                            cats.extend(parsed)
                        else:
                            cats.append(str(p_cats))
                    except Exception:
                        cats.append(str(p_cats))
                if not cats:
                    c_cats = row.get("comment_categories")
                    if c_cats:
                        try:
                            parsed = json.loads(c_cats)
                            if isinstance(parsed, list):
                                cats.extend(parsed)
                            else:
                                cats.append(str(c_cats))
                        except Exception:
                            cats.append(str(c_cats))

                unique_cats = list(dict.fromkeys([str(c).strip() for c in cats if c]))
                return ", ".join(unique_cats) if unique_cats else "Thảo luận chung"

            # Helper for formatting score display
            def format_score_display(row):
                score = row.get("toxic_score", 0.0)
                status_vi = row.get("review_status_vi") or row.get("severity_vi", "Trong sạch")
                user_rev = str(row.get("user_review_vi") or "").strip()
                if user_rev:
                    return f"{round(score, 2)} ({status_vi}) [Bạn đánh giá: {user_rev}]"
                return f"{round(score, 2)} ({status_vi})"

            # Helper for post content fallback
            def format_post_content(row):
                p_text = str(row.get("post_content") or "").strip()
                if p_text:
                    return clean_to_viet_eng(p_text) if viet_eng_only else p_text
                return str(row.get("post_url") or "")

            def format_user_keywords(row):
                kws = row.get("user_keywords")
                if kws:
                    try:
                        parsed = json.loads(kws)
                        if isinstance(parsed, list):
                            return ", ".join(parsed)
                    except Exception:
                        return str(kws)
                return ""

            def clean_field(val):
                if not val or pd.isna(val):
                    return ""
                val_str = str(val).strip()
                cleaned = clean_to_viet_eng(val_str) if viet_eng_only else val_str
                return " ".join(cleaned.split())

            out_df = pd.DataFrame()
            out_df["Mã ID"] = df["comment_id"]
            out_df["Bài viết"] = df.apply(format_post_content, axis=1).apply(lambda s: " ".join(str(s).split()))
            out_df["f0"] = df["f0"].apply(clean_field) if "f0" in df.columns else ""
            out_df["f1"] = df["f1"].apply(clean_field) if "f1" in df.columns else ""
            out_df["f2"] = df["f2"].apply(clean_field) if "f2" in df.columns else ""
            out_df["f3"] = df["f3"].apply(clean_field) if "f3" in df.columns else ""
            out_df["Nội dung"] = (df["comment_content"].apply(clean_to_viet_eng) if viet_eng_only else df["comment_content"]).apply(lambda s: " ".join(str(s).split()))
            out_df["Điểm đánh giá"] = df.apply(format_score_display, axis=1).apply(lambda s: " ".join(str(s).split()))
            out_df["Chủ đề bài viết"] = df.apply(format_categories, axis=1).apply(lambda s: " ".join(str(s).split()))
            out_df["Tự đánh giá của bạn (Xấu luôn / Chưa rõ / Trong sạch)"] = df["user_review_vi"].fillna("").apply(lambda s: " ".join(str(s).split()))
            out_df["Từ lóng mới bổ sung (nếu có)"] = df.apply(format_user_keywords, axis=1).apply(lambda s: " ".join(str(s).split()))

            return out_df

    def backfill_comment_generations(self) -> int:
        """
        Reconstruct and populate f0, f1, f2, f3 and reply_level for all comments in the database.
        Detects thread hierarchies based on:
        1. Existing parent_comment_id or reply indicators.
        2. Sequence order and conversation dialogue flows (post author vs commenters, replies).
        Returns the number of comments updated.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            post_rows = cursor.execute("SELECT id, author_username FROM posts").fetchall()
            post_authors = {r["id"]: r["author_username"] for r in post_rows}

            comments = cursor.execute("""
                SELECT rowid, id, post_id, author_username, content, reply_to, is_reply, parent_comment_id
                FROM comments
                ORDER BY rowid ASC
            """).fetchall()

            if not comments:
                return 0

            from collections import defaultdict
            comments_by_post = defaultdict(list)
            for c in comments:
                comments_by_post[c["post_id"]].append(dict(c))

            updates = []
            excess_comment_ids = []
            for post_id, c_list in comments_by_post.items():
                post_author = post_authors.get(post_id, "")
                current_f0 = ""
                current_f0_author = ""
                current_f1 = ""
                current_f1_author = ""
                current_f2 = ""
                current_f2_author = ""
                current_f3 = ""
                current_level = 0

                for idx, cmt in enumerate(c_list):
                    c_id = cmt["id"]
                    author = cmt["author_username"] or ""
                    content = cmt["content"] or ""
                    reply_to = cmt.get("reply_to") or ""
                    existing_is_reply = cmt.get("is_reply") or 0
                    parent_id = cmt.get("parent_comment_id") or ""

                    is_reply = False
                    if reply_to or existing_is_reply == 1 or parent_id:
                        is_reply = True

                    if not is_reply and current_f0:
                        if author == post_author and current_f0_author != post_author:
                            is_reply = True
                        elif author == current_f0_author and current_f1_author:
                            is_reply = True
                        elif any(kw in content.lower() for kw in ["bà ơi", "bác ơi", "bạn ơi", "bác nói", "bà nói", "đúng z", "chuẩn nè", "ý là", "thế à", "vả nó", "chửi nó"]):
                            is_reply = True

                    if not is_reply:
                        current_f0 = content
                        current_f0_author = author
                        current_f1 = ""
                        current_f1_author = ""
                        current_f2 = ""
                        current_f2_author = ""
                        current_f3 = ""
                        current_level = 0

                        updates.append((
                            "",  # f0: empty when cmt is root ("nếu cmt cần xử lý là reply")
                            "",  # f1
                            "",  # f2
                            "",  # f3
                            0,   # reply_level
                            0,   # is_reply
                            "Bình luận gốc",
                            c_id
                        ))
                    else:
                        current_level += 1
                        level = current_level

                        if level == 1:
                            current_f1 = content
                            current_f1_author = author
                            f0_val = current_f0
                            f1_val = current_f1
                            f2_val = ""
                            f3_val = ""
                            cmt_type = "Bình luận con (F1)"
                        elif level == 2:
                            current_f2 = content
                            current_f2_author = author
                            f0_val = current_f0
                            f1_val = current_f1
                            f2_val = current_f2
                            f3_val = ""
                            cmt_type = "Bình luận con (F2)"
                        elif level == 3:
                            current_f3 = content
                            f0_val = current_f0
                            f1_val = current_f1
                            f2_val = current_f2
                            f3_val = current_f3
                            cmt_type = "Bình luận con (F3)"
                        else:
                            # User strictly only wants up to F3: Purge comments beyond F3
                            excess_comment_ids.append(c_id)
                            continue

                        updates.append((
                            f0_val,
                            f1_val,
                            f2_val,
                            f3_val,
                            level,
                            1,
                            cmt_type,
                            c_id
                        ))

            if excess_comment_ids:
                batch_size = 500
                for i in range(0, len(excess_comment_ids), batch_size):
                    batch = excess_comment_ids[i:i + batch_size]
                    placeholders = ",".join(["?"] * len(batch))
                    cursor.execute(f"DELETE FROM comments WHERE id IN ({placeholders})", batch)
                conn.commit()
                logger.info(f"Purged {len(excess_comment_ids)} excess comments beyond F3 during backfill.")

            if updates:
                cursor.executemany("""
                    UPDATE comments
                    SET f0 = ?,
                        f1 = ?,
                        f2 = ?,
                        f3 = ?,
                        reply_level = ?,
                        is_reply = ?,
                        comment_type_vi = ?
                    WHERE id = ?
                """, updates)
                conn.commit()
                logger.info(f"Backfilled generations (f0, f1, f2, f3) for {len(updates)} comments (strictly capped at F3).")

            return len(updates)

    def purge_comments_beyond_f3(self) -> int:
        """
        Delete all comments beyond F3 (reply_level > 3) to enforce maximum depth of F3.
        Returns the number of deleted records.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM comments 
                WHERE reply_level > 3 
                   OR comment_type_vi LIKE '%(F4%'
                   OR comment_type_vi LIKE '%(F5%'
                   OR comment_type_vi LIKE '%(F6%'
                   OR comment_type_vi LIKE '%(F7%'
                   OR comment_type_vi LIKE '%(F8%'
                   OR comment_type_vi LIKE '%(F9%'
                   OR comment_type_vi LIKE '%(F1%'
            """)
            count = cursor.rowcount
            conn.commit()
        logger.info(f"Purged {count} comments beyond F3 from database.")
        return count


    def purge_foreign_language_records(self) -> Dict[str, int]:
        """
        Scan SQLite database for comments and posts that contain predominantly
        Chinese, Japanese, Korean, Thai, Arabic, or Cyrillic characters and delete them.
        For remaining comments/posts, clean any stray foreign characters.
        """
        with self.get_connection() as conn:
            # 1. Purge foreign comments
            comments = conn.execute("SELECT id, content FROM comments").fetchall()
            ids_to_delete = []
            updates = []
            for row in comments:
                cid, content = row["id"], row["content"] or ""
                if not is_valid_viet_eng_content(content):
                    ids_to_delete.append(cid)
                else:
                    cleaned = clean_to_viet_eng(content)
                    if cleaned != content:
                        updates.append((cleaned, cid))

            for cid in ids_to_delete:
                conn.execute("DELETE FROM comments WHERE id = ?", (cid,))
            purged_comments = len(ids_to_delete)

            for cleaned, cid in updates:
                conn.execute("UPDATE comments SET content = ? WHERE id = ?", (cleaned, cid))
            cleaned_comments = len(updates)

            # 2. Purge foreign posts
            posts = conn.execute("SELECT id, content FROM posts").fetchall()
            post_ids_to_delete = []
            post_updates = []
            for row in posts:
                pid, content = row["id"], row["content"] or ""
                if content and not is_valid_viet_eng_content(content):
                    post_ids_to_delete.append(pid)
                else:
                    cleaned = clean_to_viet_eng(content)
                    if cleaned != content:
                        post_updates.append((cleaned, pid))

            for pid in post_ids_to_delete:
                conn.execute("DELETE FROM posts WHERE id = ?", (pid,))
            purged_posts = len(post_ids_to_delete)

            for cleaned, pid in post_updates:
                conn.execute("UPDATE posts SET content = ? WHERE id = ?", (cleaned, pid))

            conn.commit()

        logger.info(f"Purged {purged_comments} foreign comments, {purged_posts} foreign posts, cleaned {cleaned_comments} items.")
        return {
            "purged_comments": purged_comments,
            "purged_posts": purged_posts,
            "cleaned_comments": cleaned_comments
        }

    def clean_ui_artifacts_in_db(self) -> Dict[str, int]:
        """
        Cleans Threads UI artifacts ('Translate 1 / 2', 'Translate', '1 / 2' carousel indicators, etc.)
        from all posts and comments (including f0, f1, f2, f3) in the database.
        """
        with self.get_connection() as conn:
            # 1. Clean posts
            posts = conn.execute("SELECT id, content FROM posts").fetchall()
            post_updates = []
            for row in posts:
                pid, content = row["id"], row["content"] or ""
                cleaned = clean_ui_artifacts(content)
                if cleaned != content:
                    post_updates.append((cleaned, pid))

            for cleaned, pid in post_updates:
                conn.execute("UPDATE posts SET content = ? WHERE id = ?", (cleaned, pid))

            # 2. Clean comments and generations
            comments = conn.execute("SELECT id, content, f0, f1, f2, f3 FROM comments").fetchall()
            comment_updates = []
            for row in comments:
                cid = row["id"]
                c_content = row["content"] or ""
                f0 = row["f0"] or ""
                f1 = row["f1"] or ""
                f2 = row["f2"] or ""
                f3 = row["f3"] or ""

                new_c = clean_ui_artifacts(c_content)
                new_f0 = clean_ui_artifacts(f0) if f0 else ""
                new_f1 = clean_ui_artifacts(f1) if f1 else ""
                new_f2 = clean_ui_artifacts(f2) if f2 else ""
                new_f3 = clean_ui_artifacts(f3) if f3 else ""

                if new_c != c_content or new_f0 != f0 or new_f1 != f1 or new_f2 != f2 or new_f3 != f3:
                    comment_updates.append((new_c, new_f0, new_f1, new_f2, new_f3, cid))

            for new_c, new_f0, new_f1, new_f2, new_f3, cid in comment_updates:
                conn.execute(
                    "UPDATE comments SET content = ?, f0 = ?, f1 = ?, f2 = ?, f3 = ? WHERE id = ?",
                    (new_c, new_f0, new_f1, new_f2, new_f3, cid)
                )

            conn.commit()

        logger.info(f"Cleaned UI artifacts in DB: {len(post_updates)} posts, {len(comment_updates)} comments updated.")
        return {
            "cleaned_posts": len(post_updates),
            "cleaned_comments": len(comment_updates)
        }

    def count_duplicate_comments(self) -> int:
        """
        Count total redundant duplicate comments in the database.
        Returns the number of duplicate rows that can be purged (leaving 1 original per content).
        """
        from collections import Counter
        with self.get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute("""
                SELECT content
                FROM comments
                WHERE content IS NOT NULL AND TRIM(content) != ''
            """).fetchall()
            counter = Counter()
            for r in rows:
                norm = " ".join(str(r[0] or "").split()).lower()
                counter[norm] += 1
            total_redundant = sum(cnt - 1 for cnt in counter.values() if cnt > 1)
            return total_redundant

    def purge_duplicate_comments(self) -> Dict[str, int]:
        """
        Scan SQLite database for duplicate comments by normalized content.
        Preserves the best record per content group:
          1. Priority to user-reviewed comments (is_user_reviewed = 1)
          2. Priority to higher toxic score / more severe classification
          3. Earliest scraped_at timestamp
        Deletes the remaining redundant copies.
        Returns dict with statistics on purged comments.
        """
        from collections import defaultdict
        with self.get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute("""
                SELECT id, content, is_user_reviewed, toxic_score, scraped_at
                FROM comments
                WHERE content IS NOT NULL AND TRIM(content) != ''
            """).fetchall()

            groups = defaultdict(list)
            for r in rows:
                norm = " ".join(str(r["content"]).split()).lower()
                groups[norm].append(r)

            ids_to_delete = []
            for norm_text, items in groups.items():
                if len(items) <= 1:
                    continue
                sorted_items = sorted(
                    items,
                    key=lambda x: (
                        1 if x["is_user_reviewed"] else 0,
                        float(x["toxic_score"] or 0.0),
                        -(datetime.fromisoformat(x["scraped_at"]).timestamp() if x["scraped_at"] else 0)
                    ),
                    reverse=True
                )
                for dup in sorted_items[1:]:
                    ids_to_delete.append(dup["id"])

            for cid in ids_to_delete:
                cursor.execute("DELETE FROM comments WHERE id = ?", (cid,))

            purged_count = len(ids_to_delete)
            conn.commit()

        logger.info(f"Purged {purged_count} duplicate comments from database.")
        return {
            "purged_duplicates": purged_count,
            "remaining_comments": len(rows) - purged_count
        }

    def purge_duplicate_posts(self) -> int:
        """
        Purge duplicate posts by URL or normalized content.
        Keeps the earliest scraped post.
        """
        from collections import defaultdict
        with self.get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute("SELECT id, url, content, scraped_at FROM posts").fetchall()
            groups = defaultdict(list)
            for r in rows:
                url_key = str(r["url"]).strip() if r["url"] else ""
                content_key = " ".join(str(r["content"] or "").split()).lower()
                key = url_key or content_key
                groups[key].append(r)

            ids_to_delete = []
            for key, items in groups.items():
                if len(items) <= 1:
                    continue
                sorted_items = sorted(
                    items,
                    key=lambda x: str(x["scraped_at"] or ""),
                )
                for dup in sorted_items[1:]:
                    ids_to_delete.append(dup["id"])

            for pid in ids_to_delete:
                cursor.execute("DELETE FROM posts WHERE id = ?", (pid,))

            purged = len(ids_to_delete)
            conn.commit()

        logger.info(f"Purged {purged} duplicate posts from database.")
        return purged

    def delete_comments(self, comment_ids: List[str], cascade: bool = True) -> int:
        """
        Delete specific comments by ID list.
        If cascade=True (default), also finds and deletes all dependent child comments:
        - When an F2 comment is deleted, all of its F3 reply comments are automatically deleted.
        - When an F1 comment is deleted, its F2 and F3 replies are automatically deleted.
        - When an F0 (root) comment is deleted, all replies under it (F1, F2, F3) are automatically deleted.
        Returns the total number of deleted records.
        """
        if not comment_ids:
            return 0
        valid_ids = list(set(str(cid).strip() for cid in comment_ids if cid and str(cid).strip()))
        if not valid_ids:
            return 0

        with self.get_connection() as conn:
            cursor = conn.cursor()
            all_ids_to_delete = set(valid_ids)

            if cascade:
                placeholders = ",".join(["?"] * len(valid_ids))
                rows = cursor.execute(
                    f"SELECT id, post_id, content, reply_level FROM comments WHERE id IN ({placeholders})",
                    valid_ids
                ).fetchall()

                for r in rows:
                    cid = r["id"]
                    post_id = r["post_id"]
                    content = r["content"]
                    r_level = r["reply_level"] or 0

                    # 1. Direct children via parent_comment_id
                    child_rows = cursor.execute(
                        "SELECT id FROM comments WHERE parent_comment_id = ?",
                        (cid,)
                    ).fetchall()
                    for ch in child_rows:
                        all_ids_to_delete.add(ch["id"])

                    # 2. Hierarchy children matching in same post
                    if content:
                        if r_level == 2:  # F2 -> delete all F3 replies
                            f3_rows = cursor.execute(
                                "SELECT id FROM comments WHERE post_id = ? AND f2 = ? AND reply_level = 3",
                                (post_id, content)
                            ).fetchall()
                            for f3_r in f3_rows:
                                all_ids_to_delete.add(f3_r["id"])
                        elif r_level == 1:  # F1 -> delete F2 & F3 replies
                            f_rows = cursor.execute(
                                "SELECT id FROM comments WHERE post_id = ? AND f1 = ? AND reply_level >= 2",
                                (post_id, content)
                            ).fetchall()
                            for f_r in f_rows:
                                all_ids_to_delete.add(f_r["id"])
                        elif r_level == 0:  # F0 -> delete all replies
                            f_rows = cursor.execute(
                                "SELECT id FROM comments WHERE post_id = ? AND f0 = ? AND reply_level >= 1",
                                (post_id, content)
                            ).fetchall()
                            for f_r in f_rows:
                                all_ids_to_delete.add(f_r["id"])

            final_ids = list(all_ids_to_delete)
            total_deleted = 0
            batch_size = 500
            for i in range(0, len(final_ids), batch_size):
                batch = final_ids[i:i + batch_size]
                placeholders = ",".join(["?"] * len(batch))
                cursor.execute(f"DELETE FROM comments WHERE id IN ({placeholders})", batch)
                total_deleted += cursor.rowcount
            conn.commit()

        logger.info(f"User deleted {total_deleted} comments successfully (cascade={cascade}).")
        return total_deleted

    @staticmethod
    def _build_length_condition(
        col_name: str = "content",
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        length_op: Optional[str] = None,
        length_val: Optional[int] = None
    ) -> Tuple[str, List[Any]]:
        """
        Build SQL WHERE clause and parameters for length filtering.
        Supports:
          - length_op and length_val (operators: '<=', '<', '>=', '>', '==', '=', '!=')
          - min_length and max_length (range or bounds)
        """
        clause = ""
        params: List[Any] = []
        op_map = {
            "<=": "<=",
            "<": "<",
            ">=": ">=",
            ">": ">",
            "==": "=",
            "=": "=",
            "!=": "!="
        }
        if length_op and length_val is not None:
            clean_op = op_map.get(str(length_op).strip())
            if clean_op:
                clause += f" AND LENGTH(TRIM({col_name})) {clean_op} ?"
                params.append(int(length_val))
        else:
            if min_length is not None and int(min_length) > 0:
                clause += f" AND LENGTH(TRIM({col_name})) >= ?"
                params.append(int(min_length))
            if max_length is not None and int(max_length) > 0:
                clause += f" AND LENGTH(TRIM({col_name})) <= ?"
                params.append(int(max_length))
        return clause, params

    def count_comments_by_length(
        self,
        operator: str,
        length: int,
        keep_reviewed: bool = False
    ) -> int:
        """
        Count comments matching length operator ('<=', '<', '>=', '>', '==', '!=').
        If keep_reviewed=True, excludes comments where is_user_reviewed=1.
        """
        op_map = {"<=": "<=", "<": "<", ">=": ">=", ">": ">", "==": "=", "=": "=", "!=": "!="}
        sql_op = op_map.get(str(operator).strip())
        if not sql_op:
            raise ValueError(f"Toán tử không hợp lệ: {operator}. Chỉ hỗ trợ: <=, <, >=, >, ==, !=")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = f"SELECT COUNT(*) FROM comments WHERE LENGTH(TRIM(content)) {sql_op} ?"
            params: List[Any] = [int(length)]
            if keep_reviewed:
                query += " AND (is_user_reviewed = 0 OR is_user_reviewed IS NULL)"
            return cursor.execute(query, params).fetchone()[0]

    def delete_comments_by_length(
        self,
        operator: str,
        length: int,
        keep_reviewed: bool = True
    ) -> int:
        """
        Delete comments matching length operator ('<=', '<', '>=', '>', '==', '!=').
        If keep_reviewed=True, protects comments where is_user_reviewed=1.
        Returns the count of deleted comments.
        """
        op_map = {"<=": "<=", "<": "<", ">=": ">=", ">": ">", "==": "=", "=": "=", "!=": "!="}
        sql_op = op_map.get(str(operator).strip())
        if not sql_op:
            raise ValueError(f"Toán tử không hợp lệ: {operator}. Chỉ hỗ trợ: <=, <, >=, >, ==, !=")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = f"DELETE FROM comments WHERE LENGTH(TRIM(content)) {sql_op} ?"
            params: List[Any] = [int(length)]
            if keep_reviewed:
                query += " AND (is_user_reviewed = 0 OR is_user_reviewed IS NULL)"
            cursor.execute(query, params)
            deleted_count = cursor.rowcount
            conn.commit()

        logger.info(f"Deleted {deleted_count} comments matching length condition: {operator} {length} (keep_reviewed={keep_reviewed}).")
        return deleted_count

    def get_comments_by_length_preview(
        self,
        operator: str,
        length: int,
        keep_reviewed: bool = False,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieve sample comments matching length operator for UI preview.
        """
        op_map = {"<=": "<=", "<": "<", ">=": ">=", ">": ">", "==": "=", "=": "=", "!=": "!="}
        sql_op = op_map.get(str(operator).strip())
        if not sql_op:
            return []

        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = f"""
                SELECT id, author_username, content, LENGTH(TRIM(content)) as content_length,
                       is_user_reviewed, review_status_vi, toxic_score
                FROM comments
                WHERE LENGTH(TRIM(content)) {sql_op} ?
            """
            params: List[Any] = [int(length)]
            if keep_reviewed:
                query += " AND (is_user_reviewed = 0 OR is_user_reviewed IS NULL)"
            query += " ORDER BY scraped_at DESC LIMIT ?"
            params.append(int(limit))
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_posts_for_management(
        self,
        search_kw: str = "",
        author_username: str = "",
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Fetch posts with actual comments count in DB and metadata for management/deletion.
        """
        with self.get_connection() as conn:
            query = """
                SELECT 
                    p.id,
                    p.author_username,
                    p.content,
                    p.url,
                    p.likes,
                    p.replies_count,
                    p.categories,
                    p.is_toxic,
                    p.toxic_score,
                    p.severity_vi,
                    p.scraped_at,
                    (
                        SELECT COUNT(*) FROM comments c 
                        WHERE c.post_id = p.id OR c.post_url = p.url
                    ) as actual_comments_count
                FROM posts p
                WHERE 1=1
            """
            params = []
            if search_kw:
                query += " AND (p.content LIKE ? OR p.matched_words LIKE ?)"
                kw = f"%{search_kw.strip()}%"
                params.extend([kw, kw])
            if author_username:
                clean_user = author_username.strip().lstrip("@")
                query += " AND p.author_username = ?"
                params.append(clean_user)

            query += " ORDER BY p.scraped_at DESC"
            if limit is not None and limit > 0:
                query += f" LIMIT {int(limit)}"

            df = pd.read_sql_query(query, conn, params=params)
            return df

    def get_post_details(self, post_id_or_url: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single post along with its comment count and up to 5 sample comments.
        """
        target = str(post_id_or_url).strip()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            p_row = cursor.execute("""
                SELECT * FROM posts WHERE id = ? OR url = ?
            """, (target, target)).fetchone()
            if not p_row:
                return None

            post_data = dict(p_row)
            pid = post_data["id"]
            purl = post_data["url"]

            c_count = cursor.execute("""
                SELECT COUNT(*) FROM comments WHERE post_id = ? OR post_url = ?
            """, (pid, purl)).fetchone()[0]
            post_data["actual_comments_count"] = c_count

            sample_c = cursor.execute("""
                SELECT id, author_username, content, likes, review_status_vi, toxic_score, scraped_at
                FROM comments WHERE post_id = ? OR post_url = ?
                ORDER BY scraped_at DESC LIMIT 5
            """, (pid, purl)).fetchall()
            post_data["sample_comments"] = [dict(c) for c in sample_c]

            return post_data

    def count_content_by_posts(
        self,
        post_ids_or_urls: Union[str, List[str]],
        keep_reviewed: bool = False
    ) -> Dict[str, Any]:
        """
        Count total posts and comments associated with the specified post IDs or URLs.
        If keep_reviewed=True, comments with is_user_reviewed=1 are excluded from comments_count.
        """
        if isinstance(post_ids_or_urls, str):
            targets = [post_ids_or_urls.strip()] if post_ids_or_urls.strip() else []
        elif isinstance(post_ids_or_urls, (list, tuple, set)):
            targets = [str(x).strip() for x in post_ids_or_urls if x and str(x).strip()]
        else:
            targets = []

        if not targets:
            return {"posts_count": 0, "comments_count": 0, "total_items": 0, "post_ids": []}

        with self.get_connection() as conn:
            cursor = conn.cursor()
            ph = ",".join(["?"] * len(targets))
            p_rows = cursor.execute(f"""
                SELECT id, url FROM posts WHERE id IN ({ph}) OR url IN ({ph})
            """, targets + targets).fetchall()

            found_pids = [r["id"] for r in p_rows]
            found_urls = [r["url"] for r in p_rows if r["url"]]

            matching_c_ids = set()
            if found_pids or found_urls:
                for i in range(0, max(len(found_pids), len(found_urls)), 500):
                    chunk_pids = found_pids[i:i+500]
                    chunk_urls = found_urls[i:i+500]
                    clauses = []
                    params = []
                    if chunk_pids:
                        cph = ",".join(["?"] * len(chunk_pids))
                        clauses.append(f"post_id IN ({cph})")
                        params.extend(chunk_pids)
                    if chunk_urls:
                        uph = ",".join(["?"] * len(chunk_urls))
                        clauses.append(f"post_url IN ({uph})")
                        params.extend(chunk_urls)
                    if clauses:
                        q = f"SELECT id, is_user_reviewed FROM comments WHERE ({' OR '.join(clauses)})"
                        c_rows = cursor.execute(q, params).fetchall()
                        for r in c_rows:
                            if not (keep_reviewed and r["is_user_reviewed"]):
                                matching_c_ids.add(r["id"])

            return {
                "posts_count": len(found_pids),
                "comments_count": len(matching_c_ids),
                "total_items": len(found_pids) + len(matching_c_ids),
                "post_ids": found_pids
            }

    def delete_posts_cascade(
        self,
        post_ids_or_urls: Union[str, List[str]],
        keep_reviewed: bool = False
    ) -> Dict[str, Any]:
        """
        Cascade delete posts and all their related comments (roots & replies F1-F3).
        "thì ta sẽ xóa những thứ liên quan tới bài viết":
        - Deletes all comments on the specified posts.
        - Deletes the posts themselves from posts table.
        - If keep_reviewed=True, protects comments marked as is_user_reviewed=1.
        - Re-backfills comment generations hierarchy (F0-F3) for remaining data.
        Returns statistics of purged items.
        """
        if isinstance(post_ids_or_urls, str):
            targets = [post_ids_or_urls.strip()] if post_ids_or_urls.strip() else []
        elif isinstance(post_ids_or_urls, (list, tuple, set)):
            targets = [str(x).strip() for x in post_ids_or_urls if x and str(x).strip()]
        else:
            targets = []

        if not targets:
            return {
                "deleted_posts": 0,
                "deleted_comments": 0,
                "post_ids": [],
                "remaining_posts": 0,
                "remaining_comments": 0
            }

        with self.get_connection() as conn:
            cursor = conn.cursor()
            ph = ",".join(["?"] * len(targets))
            p_rows = cursor.execute(f"""
                SELECT id, url FROM posts WHERE id IN ({ph}) OR url IN ({ph})
            """, targets + targets).fetchall()

            found_pids = [r["id"] for r in p_rows]
            found_urls = [r["url"] for r in p_rows if r["url"]]

            comments_to_delete = set()
            if found_pids or found_urls:
                for i in range(0, max(len(found_pids), len(found_urls)), 500):
                    chunk_pids = found_pids[i:i+500]
                    chunk_urls = found_urls[i:i+500]
                    clauses = []
                    params = []
                    if chunk_pids:
                        cph = ",".join(["?"] * len(chunk_pids))
                        clauses.append(f"post_id IN ({cph})")
                        params.extend(chunk_pids)
                    if chunk_urls:
                        uph = ",".join(["?"] * len(chunk_urls))
                        clauses.append(f"post_url IN ({uph})")
                        params.extend(chunk_urls)
                    if clauses:
                        q = f"SELECT id, is_user_reviewed FROM comments WHERE ({' OR '.join(clauses)})"
                        c_rows = cursor.execute(q, params).fetchall()
                        for r in c_rows:
                            if not (keep_reviewed and r["is_user_reviewed"]):
                                comments_to_delete.add(r["id"])

            # Delete comments
            c_list = list(comments_to_delete)
            for i in range(0, len(c_list), 500):
                chunk = c_list[i:i+500]
                cph = ",".join(["?"] * len(chunk))
                cursor.execute(f"DELETE FROM comments WHERE id IN ({cph})", chunk)

            # Delete posts
            for i in range(0, len(found_pids), 500):
                chunk = found_pids[i:i+500]
                cph = ",".join(["?"] * len(chunk))
                cursor.execute(f"DELETE FROM posts WHERE id IN ({cph})", chunk)

            conn.commit()

            rem_c = cursor.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
            rem_p = cursor.execute("SELECT COUNT(*) FROM posts").fetchone()[0]

        # Re-backfill comment generations
        self.backfill_comment_generations()

        logger.info(f"Cascade purged {len(found_pids)} posts ({found_pids}): deleted {len(c_list)} comments.")
        return {
            "deleted_posts": len(found_pids),
            "deleted_comments": len(c_list),
            "post_ids": found_pids,
            "remaining_posts": rem_p,
            "remaining_comments": rem_c
        }

    def delete_post_cascade(
        self,
        post_id_or_url: str,
        keep_reviewed: bool = False
    ) -> Dict[str, Any]:
        """Convenience wrapper for deleting a single post and its related comments."""
        return self.delete_posts_cascade([post_id_or_url], keep_reviewed=keep_reviewed)

    def get_all_categories_in_db(self) -> List[str]:
        """
        Get all distinct categories/topics currently present across posts and comments in the database.
        """
        all_cats = set()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            p_rows = cursor.execute("SELECT categories FROM posts WHERE categories IS NOT NULL AND categories != ''").fetchall()
            for r in p_rows:
                try:
                    parsed = json.loads(r[0])
                    if isinstance(parsed, list):
                        all_cats.update([str(c).strip() for c in parsed if str(c).strip()])
                    elif parsed:
                        all_cats.add(str(parsed).strip())
                except Exception:
                    pass

            c_rows = cursor.execute("SELECT categories FROM comments WHERE categories IS NOT NULL AND categories != ''").fetchall()
            for r in c_rows:
                try:
                    parsed = json.loads(r[0])
                    if isinstance(parsed, list):
                        all_cats.update([str(c).strip() for c in parsed if str(c).strip()])
                    elif parsed:
                        all_cats.add(str(parsed).strip())
                except Exception:
                    pass

        return sorted(list(all_cats))

    def _build_category_condition(
        self,
        filter_category: Optional[Union[str, List[str]]] = None,
        c_alias: str = "",
        p_alias: str = ""
    ) -> Tuple[str, List[Any]]:
        """
        Build SQL condition and params for filtering comments by category/categories.
        Works for a single category string or a list of categories.
        """
        if not filter_category:
            return "", []

        if isinstance(filter_category, str):
            c_str = filter_category.strip()
            if not c_str or c_str.lower() in ("all", "(tất cả)"):
                return "", []
            cats = [c_str]
        elif isinstance(filter_category, (list, tuple, set)):
            cats = [
                str(c).strip() for c in filter_category
                if c and str(c).strip() and str(c).strip().lower() not in ("all", "(tất cả)")
            ]
        else:
            return "", []

        if not cats:
            return "", []

        ph = ",".join(["?"] * len(cats))
        col_c = f"{c_alias}.categories" if c_alias else "categories"

        if p_alias:
            col_p = f"{p_alias}.categories"
            clause = f""" AND (
                ({col_c} IS NOT NULL AND json_valid({col_c}) AND EXISTS (SELECT 1 FROM json_each({col_c}) WHERE value IN ({ph})))
                OR ({col_p} IS NOT NULL AND json_valid({col_p}) AND EXISTS (SELECT 1 FROM json_each({col_p}) WHERE value IN ({ph})))
            )"""
        else:
            col_post_id = f"{c_alias}.post_id" if c_alias else "post_id"
            clause = f""" AND (
                ({col_c} IS NOT NULL AND json_valid({col_c}) AND EXISTS (SELECT 1 FROM json_each({col_c}) WHERE value IN ({ph})))
                OR ({col_post_id} IN (SELECT id FROM posts WHERE categories IS NOT NULL AND json_valid(categories) AND EXISTS (SELECT 1 FROM json_each(categories) WHERE value IN ({ph}))))
            )"""

        params = cats + cats
        return clause, params

    def _build_post_condition(
        self,
        filter_post: Optional[Union[str, List[str]]] = None,
        c_alias: str = ""
    ) -> Tuple[str, List[Any]]:
        """
        Build SQL condition and params for filtering comments by post ID or URL.
        Works for single post or list of posts.
        """
        if not filter_post:
            return "", []

        if isinstance(filter_post, str):
            p_str = filter_post.strip()
            if not p_str or p_str.lower() in ("all", "(tất cả)", "(tất cả bài viết)"):
                return "", []
            p_targets = [p_str]
        elif isinstance(filter_post, (list, tuple, set)):
            p_targets = [
                str(p).strip() for p in filter_post
                if p and str(p).strip() and str(p).strip().lower() not in ("all", "(tất cả)", "(tất cả bài viết)")
            ]
        else:
            return "", []

        if not p_targets:
            return "", []

        col_post_id = f"{c_alias}.post_id" if c_alias else "post_id"
        col_post_url = f"{c_alias}.post_url" if c_alias else "post_url"

        ph = ",".join(["?"] * len(p_targets))
        clause = f" AND ({col_post_id} IN ({ph}) OR {col_post_url} IN ({ph}))"
        params = p_targets + p_targets
        return clause, params

    def count_content_by_categories(
        self,
        categories: Union[str, List[str]],
        keep_reviewed: bool = False
    ) -> Dict[str, Any]:
        """
        Count total posts and comments associated with one or multiple categories/topics.
        Includes:
          1. Posts tagged with any of these categories.
          2. Comments belonging to those posts.
          3. Comments directly tagged with any of these categories.
        If keep_reviewed=True, comments with is_user_reviewed=1 are excluded.
        Returns total statistics as well as breakdown per category.
        """
        if isinstance(categories, str):
            clean_cats = [categories.strip()] if categories.strip() else []
        elif isinstance(categories, (list, tuple, set)):
            clean_cats = [str(c).strip() for c in categories if c and str(c).strip()]
        else:
            clean_cats = []

        if not clean_cats:
            return {
                "categories": [],
                "posts_count": 0,
                "comments_count": 0,
                "total_items": 0,
                "by_category": {}
            }

        with self.get_connection() as conn:
            cursor = conn.cursor()
            ph_cats = ",".join(["?"] * len(clean_cats))

            # 1. Matching posts across all categories
            post_rows = cursor.execute(f"""
                SELECT id, url, categories FROM posts 
                WHERE categories IS NOT NULL AND json_valid(categories)
                  AND EXISTS (SELECT 1 FROM json_each(categories) WHERE value IN ({ph_cats}))
            """, clean_cats).fetchall()
            post_ids = [r["id"] for r in post_rows]
            post_urls = [r["url"] for r in post_rows if r["url"]]

            # 2. Matching comments across all categories
            matching_comment_ids = set()

            # Direct tagged comments
            direct_c_rows = cursor.execute(f"""
                SELECT id, is_user_reviewed, categories FROM comments
                WHERE categories IS NOT NULL AND json_valid(categories)
                  AND EXISTS (SELECT 1 FROM json_each(categories) WHERE value IN ({ph_cats}))
            """, clean_cats).fetchall()
            for r in direct_c_rows:
                if not (keep_reviewed and r["is_user_reviewed"]):
                    matching_comment_ids.add(r["id"])

            # Comments on matching posts
            if post_ids or post_urls:
                for i in range(0, max(len(post_ids), len(post_urls)), 500):
                    chunk_pids = post_ids[i:i+500]
                    chunk_urls = post_urls[i:i+500]
                    clauses = []
                    params = []
                    if chunk_pids:
                        ph = ",".join(["?"] * len(chunk_pids))
                        clauses.append(f"post_id IN ({ph})")
                        params.extend(chunk_pids)
                    if chunk_urls:
                        ph = ",".join(["?"] * len(chunk_urls))
                        clauses.append(f"post_url IN ({ph})")
                        params.extend(chunk_urls)
                    if clauses:
                        q = f"SELECT id, is_user_reviewed FROM comments WHERE ({' OR '.join(clauses)})"
                        post_c_rows = cursor.execute(q, params).fetchall()
                        for r in post_c_rows:
                            if not (keep_reviewed and r["is_user_reviewed"]):
                                matching_comment_ids.add(r["id"])

            # Breakdown per category
            by_category = {}
            for cat in clean_cats:
                p_for_cat = 0
                for r in post_rows:
                    try:
                        c_list = json.loads(r["categories"]) if r["categories"] else []
                        if cat in c_list:
                            p_for_cat += 1
                    except Exception:
                        pass
                
                c_for_cat = 0
                for r in direct_c_rows:
                    if not (keep_reviewed and r["is_user_reviewed"]):
                        try:
                            c_list = json.loads(r["categories"]) if r["categories"] else []
                            if cat in c_list:
                                c_for_cat += 1
                        except Exception:
                            pass
                by_category[cat] = {
                    "posts": p_for_cat,
                    "comments": c_for_cat,
                    "total": p_for_cat + c_for_cat
                }

            return {
                "categories": clean_cats,
                "posts_count": len(post_ids),
                "comments_count": len(matching_comment_ids),
                "total_items": len(post_ids) + len(matching_comment_ids),
                "by_category": by_category
            }

    def count_content_by_category(self, category: str, keep_reviewed: bool = False) -> Dict[str, int]:
        """Backward-compatible helper for a single category."""
        res = self.count_content_by_categories([category], keep_reviewed=keep_reviewed)
        return {
            "posts_count": res["posts_count"],
            "comments_count": res["comments_count"],
            "total_items": res["total_items"]
        }

    def delete_content_by_categories(
        self,
        categories: Union[str, List[str]],
        keep_reviewed: bool = False
    ) -> Dict[str, Any]:
        """
        Delete all posts and comments associated with one or multiple categories/topics.
        "xóa các chủ đề":
        - Deletes all posts tagged with any of the selected categories.
        - Deletes all comments on those posts.
        - Deletes all comments directly tagged with any of the selected categories.
        - Recalculates comment generation hierarchy (F0-F3).
        If keep_reviewed=True, preserves comments where is_user_reviewed=1.
        Returns dict with statistics on purged items across all categories.
        """
        if isinstance(categories, str):
            clean_cats = [categories.strip()] if categories.strip() else []
        elif isinstance(categories, (list, tuple, set)):
            clean_cats = [str(c).strip() for c in categories if c and str(c).strip()]
        else:
            clean_cats = []

        if not clean_cats:
            return {
                "categories": [],
                "deleted_comments": 0,
                "deleted_posts": 0,
                "remaining_comments": 0,
                "remaining_posts": 0
            }

        with self.get_connection() as conn:
            cursor = conn.cursor()
            ph_cats = ",".join(["?"] * len(clean_cats))

            # 1. Matching posts
            post_rows = cursor.execute(f"""
                SELECT id, url FROM posts 
                WHERE categories IS NOT NULL AND json_valid(categories)
                  AND EXISTS (SELECT 1 FROM json_each(categories) WHERE value IN ({ph_cats}))
            """, clean_cats).fetchall()
            post_ids = [r["id"] for r in post_rows]
            post_urls = [r["url"] for r in post_rows if r["url"]]

            # 2. Matching comments
            comments_to_delete = set()

            direct_c_rows = cursor.execute(f"""
                SELECT id, is_user_reviewed FROM comments
                WHERE categories IS NOT NULL AND json_valid(categories)
                  AND EXISTS (SELECT 1 FROM json_each(categories) WHERE value IN ({ph_cats}))
            """, clean_cats).fetchall()
            for r in direct_c_rows:
                if not (keep_reviewed and r["is_user_reviewed"]):
                    comments_to_delete.add(r["id"])

            if post_ids or post_urls:
                for i in range(0, max(len(post_ids), len(post_urls)), 500):
                    chunk_pids = post_ids[i:i+500]
                    chunk_urls = post_urls[i:i+500]
                    clauses = []
                    params = []
                    if chunk_pids:
                        ph = ",".join(["?"] * len(chunk_pids))
                        clauses.append(f"post_id IN ({ph})")
                        params.extend(chunk_pids)
                    if chunk_urls:
                        ph = ",".join(["?"] * len(chunk_urls))
                        clauses.append(f"post_url IN ({ph})")
                        params.extend(chunk_urls)
                    if clauses:
                        q = f"SELECT id, is_user_reviewed FROM comments WHERE ({' OR '.join(clauses)})"
                        post_c_rows = cursor.execute(q, params).fetchall()
                        for r in post_c_rows:
                            if not (keep_reviewed and r["is_user_reviewed"]):
                                comments_to_delete.add(r["id"])

            # Delete comments in chunks
            c_list = list(comments_to_delete)
            for i in range(0, len(c_list), 500):
                chunk = c_list[i:i+500]
                ph = ",".join(["?"] * len(chunk))
                cursor.execute(f"DELETE FROM comments WHERE id IN ({ph})", chunk)

            # Delete posts in chunks
            for i in range(0, len(post_ids), 500):
                chunk = post_ids[i:i+500]
                ph = ",".join(["?"] * len(chunk))
                cursor.execute(f"DELETE FROM posts WHERE id IN ({ph})", chunk)

            conn.commit()

            rem_c = cursor.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
            rem_p = cursor.execute("SELECT COUNT(*) FROM posts").fetchone()[0]

        # Re-backfill generations
        self.backfill_comment_generations()

        logger.info(f"Purged {len(clean_cats)} categories ({clean_cats}): deleted {len(c_list)} comments, {len(post_ids)} posts.")
        return {
            "categories": clean_cats,
            "category": ", ".join(clean_cats),
            "deleted_comments": len(c_list),
            "deleted_posts": len(post_ids),
            "remaining_comments": rem_c,
            "remaining_posts": rem_p
        }

    def delete_content_by_category(self, category: str, keep_reviewed: bool = False) -> Dict[str, int]:
        """Backward-compatible helper for a single category."""
        res = self.delete_content_by_categories([category], keep_reviewed=keep_reviewed)
        return {
            "category": category,
            "deleted_comments": res["deleted_comments"],
            "deleted_posts": res["deleted_posts"],
            "remaining_comments": res["remaining_comments"],
            "remaining_posts": res["remaining_posts"]
        }

    def get_categories_preview(
        self,
        categories: Union[str, List[str]],
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Get sample posts and sample comments matching any of the specified categories for UI preview.
        """
        if isinstance(categories, str):
            clean_cats = [categories.strip()] if categories.strip() else []
        elif isinstance(categories, (list, tuple, set)):
            clean_cats = [str(c).strip() for c in categories if c and str(c).strip()]
        else:
            clean_cats = []

        if not clean_cats:
            return {"sample_posts": [], "sample_comments": []}

        with self.get_connection() as conn:
            cursor = conn.cursor()
            ph_cats = ",".join(["?"] * len(clean_cats))

            p_rows = cursor.execute(f"""
                SELECT id, url, author_username, content, likes, scraped_at
                FROM posts
                WHERE categories IS NOT NULL AND json_valid(categories)
                  AND EXISTS (SELECT 1 FROM json_each(categories) WHERE value IN ({ph_cats}))
                ORDER BY scraped_at DESC LIMIT ?
            """, clean_cats + [int(limit)]).fetchall()

            c_rows = cursor.execute(f"""
                SELECT id, author_username, content, likes, review_status_vi, toxic_score, scraped_at
                FROM comments
                WHERE categories IS NOT NULL AND json_valid(categories)
                  AND EXISTS (SELECT 1 FROM json_each(categories) WHERE value IN ({ph_cats}))
                ORDER BY scraped_at DESC LIMIT ?
            """, clean_cats + [int(limit)]).fetchall()

            return {
                "sample_posts": [dict(r) for r in p_rows],
                "sample_comments": [dict(r) for r in c_rows]
            }

    def get_category_preview(self, category: str, limit: int = 5) -> Dict[str, Any]:
        """Backward-compatible helper for previewing a single category."""
        return self.get_categories_preview([category], limit=limit)

    def delete_comments_by_filter(
        self,
        search_kw: str = "",
        author_username: str = "",
        max_length: Optional[int] = None,
        min_length: Optional[int] = None,
        length_op: Optional[str] = None,
        length_val: Optional[int] = None,
        keep_reviewed: bool = False,
        filter_status: str = "all",
        filter_comment_type: str = "all",
        filter_category: Optional[Union[str, List[str]]] = None,
        filter_post: Optional[Union[str, List[str]]] = None
    ) -> int:
        """
        Bulk delete comments matching criteria (e.g. short spam, specific keyword, spam author, category, or post).
        Returns the count of deleted records.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "DELETE FROM comments WHERE 1=1"
            params = []

            if search_kw:
                query += " AND (content LIKE ? OR matched_words LIKE ?)"
                kw_wildcard = f"%{search_kw.strip()}%"
                params.extend([kw_wildcard, kw_wildcard])

            if author_username:
                clean_user = author_username.strip().lstrip("@")
                query += " AND author_username = ?"
                params.append(clean_user)

            len_clause, len_params = self._build_length_condition(
                "content", min_length=min_length, max_length=max_length, length_op=length_op, length_val=length_val
            )
            query += len_clause
            params.extend(len_params)

            if keep_reviewed:
                query += " AND (is_user_reviewed = 0 OR is_user_reviewed IS NULL)"

            if filter_status == "bad":
                query += " AND (review_status = 'bad' OR toxic_score >= 0.5)"
            elif filter_status == "ambiguous":
                query += " AND (review_status = 'ambiguous' OR (toxic_score >= 0.15 AND toxic_score < 0.5))"
            elif filter_status == "clean":
                query += " AND (review_status = 'clean' OR toxic_score < 0.15)"

            if filter_comment_type == "root":
                query += " AND (is_reply = 0 OR is_reply IS NULL)"
            elif filter_comment_type == "reply":
                query += " AND is_reply = 1"

            cat_clause, cat_params = self._build_category_condition(filter_category)
            query += cat_clause
            params.extend(cat_params)

            post_clause, post_params = self._build_post_condition(filter_post)
            query += post_clause
            params.extend(post_params)

            cursor.execute(query, params)
            deleted_count = cursor.rowcount
            conn.commit()

        logger.info(f"Bulk deleted {deleted_count} comments matching filter criteria.")
        return deleted_count

    def get_comments_for_cleanup_df(
        self,
        search_kw: str = "",
        author_username: str = "",
        max_length: Optional[int] = None,
        min_length: Optional[int] = None,
        length_op: Optional[str] = None,
        length_val: Optional[int] = None,
        filter_status: str = "all",
        filter_comment_type: str = "all",
        filter_category: Optional[Union[str, List[str]]] = None,
        filter_post: Optional[Union[str, List[str]]] = None,
        limit: Optional[int] = 500,
        offset: Optional[int] = 0,
        order_by: str = "newest"
    ) -> pd.DataFrame:
        """
        Fetch filtered comments formatted for interactive cleanup table with pagination support.
        Includes columns: id, author_username, content, length, comment_type_vi, reply_level, review_status_vi, likes, scraped_at, post_id, post_author, post_content, post_summary.
        """
        with self.get_connection() as conn:
            query = """
                SELECT 
                    c.id,
                    c.author_username,
                    c.content,
                    LENGTH(TRIM(c.content)) as content_length,
                    c.comment_type_vi,
                    c.reply_level,
                    c.review_status_vi,
                    c.f0,
                    c.f1,
                    c.likes,
                    c.scraped_at,
                    c.post_id,
                    COALESCE(p.author_username, '') as post_author,
                    COALESCE(p.content, '') as post_content,
                    c.post_url
                FROM comments c
                LEFT JOIN posts p ON c.post_id = p.id
                WHERE 1=1
            """
            params = []

            if search_kw:
                query += " AND (c.content LIKE ? OR c.matched_words LIKE ?)"
                kw_wildcard = f"%{search_kw.strip()}%"
                params.extend([kw_wildcard, kw_wildcard])

            if author_username:
                clean_user = author_username.strip().lstrip("@")
                query += " AND c.author_username = ?"
                params.append(clean_user)

            len_clause, len_params = self._build_length_condition(
                "c.content", min_length=min_length, max_length=max_length, length_op=length_op, length_val=length_val
            )
            query += len_clause
            params.extend(len_params)

            if filter_status == "bad":
                query += " AND (c.review_status = 'bad' OR c.toxic_score >= 0.5)"
            elif filter_status == "ambiguous":
                query += " AND (c.review_status = 'ambiguous' OR (c.toxic_score >= 0.15 AND c.toxic_score < 0.5))"
            elif filter_status == "clean":
                query += " AND (c.review_status = 'clean' OR c.toxic_score < 0.15)"

            if filter_comment_type == "root":
                query += " AND (c.is_reply = 0 OR c.is_reply IS NULL)"
            elif filter_comment_type == "reply":
                query += " AND c.is_reply = 1"

            cat_clause, cat_params = self._build_category_condition(filter_category, c_alias="c", p_alias="p")
            query += cat_clause
            params.extend(cat_params)

            post_clause, post_params = self._build_post_condition(filter_post, c_alias="c")
            query += post_clause
            params.extend(post_params)

            if order_by == "oldest":
                query += " ORDER BY c.scraped_at ASC"
            elif order_by == "toxic_score_desc":
                query += " ORDER BY c.toxic_score DESC, c.scraped_at DESC"
            elif order_by == "shortest_first":
                query += " ORDER BY LENGTH(TRIM(c.content)) ASC, c.scraped_at DESC"
            elif order_by == "longest_first":
                query += " ORDER BY LENGTH(TRIM(c.content)) DESC, c.scraped_at DESC"
            elif order_by == "post":
                query += " ORDER BY p.author_username ASC, c.post_id ASC, c.scraped_at DESC"
            else:  # newest
                query += " ORDER BY c.scraped_at DESC"

            if limit is not None and limit > 0:
                query += f" LIMIT {int(limit)}"
            if offset is not None and offset > 0:
                query += f" OFFSET {int(offset)}"

            df = pd.read_sql_query(query, conn, params=params)

            if not df.empty and "post_content" in df.columns:
                def make_post_summary(row):
                    p_auth = str(row.get("post_author", "") or "").strip()
                    p_txt = str(row.get("post_content", "") or "").strip()
                    if not p_txt and not p_auth:
                        p_id = str(row.get("post_id", "") or "").strip()
                        return f"[Bài {p_id}]" if p_id else "Chưa rõ bài viết"
                    snippet = (p_txt[:60] + "...") if len(p_txt) > 60 else p_txt
                    if p_auth:
                        return f"[@{p_auth}] {snippet}" if snippet else f"[@{p_auth}]"
                    return snippet
                df["post_summary"] = df.apply(make_post_summary, axis=1)
            elif "post_summary" not in df.columns:
                df["post_summary"] = ""
            return df

    def count_cleanup_comments(
        self,
        search_kw: str = "",
        author_username: str = "",
        max_length: Optional[int] = None,
        min_length: Optional[int] = None,
        length_op: Optional[str] = None,
        length_val: Optional[int] = None,
        filter_status: str = "all",
        filter_comment_type: str = "all",
        filter_category: Optional[Union[str, List[str]]] = None,
        filter_post: Optional[Union[str, List[str]]] = None
    ) -> int:
        """Count comments matching cleanup filter criteria."""
        with self.get_connection() as conn:
            query = "SELECT COUNT(*) FROM comments WHERE 1=1"
            params = []

            if search_kw:
                query += " AND (content LIKE ? OR matched_words LIKE ?)"
                kw_wildcard = f"%{search_kw.strip()}%"
                params.extend([kw_wildcard, kw_wildcard])

            if author_username:
                clean_user = author_username.strip().lstrip("@")
                query += " AND author_username = ?"
                params.append(clean_user)

            len_clause, len_params = self._build_length_condition(
                "content", min_length=min_length, max_length=max_length, length_op=length_op, length_val=length_val
            )
            query += len_clause
            params.extend(len_params)

            if filter_status == "bad":
                query += " AND (review_status = 'bad' OR toxic_score >= 0.5)"
            elif filter_status == "ambiguous":
                query += " AND (review_status = 'ambiguous' OR (toxic_score >= 0.15 AND toxic_score < 0.5))"
            elif filter_status == "clean":
                query += " AND (review_status = 'clean' OR toxic_score < 0.15)"

            if filter_comment_type == "root":
                query += " AND (is_reply = 0 OR is_reply IS NULL)"
            elif filter_comment_type == "reply":
                query += " AND is_reply = 1"

            cat_clause, cat_params = self._build_category_condition(filter_category)
            query += cat_clause
            params.extend(cat_params)

            post_clause, post_params = self._build_post_condition(filter_post)
            query += post_clause
            params.extend(post_params)

            cursor = conn.cursor()
            return cursor.execute(query, params).fetchone()[0]

    def get_cleanup_comment_at_index(
        self,
        index: int,
        search_kw: str = "",
        author_username: str = "",
        max_length: Optional[int] = None,
        min_length: Optional[int] = None,
        length_op: Optional[str] = None,
        length_val: Optional[int] = None,
        filter_status: str = "all",
        filter_comment_type: str = "all",
        filter_category: Optional[Union[str, List[str]]] = None,
        filter_post: Optional[Union[str, List[str]]] = None,
        order_by: str = "newest"
    ) -> Optional[Dict[str, Any]]:
        """Fetch single comment with full context for single-comment cleanup card."""
        with self.get_connection() as conn:
            query = """
                SELECT 
                    c.id, c.content, c.author_username, c.author_name, c.author_profile_url,
                    c.posted_at, c.likes, c.reply_to, c.is_reply, c.comment_type_vi,
                    c.f0, c.f1, c.f2, c.f3, c.reply_level,
                    c.comment_url, c.post_url, c.post_id,
                    c.is_toxic, c.toxic_score, c.severity_vi, c.review_status, c.review_status_vi,
                    c.has_emoji_slang, c.matched_words, c.matched_emojis, c.categories,
                    c.user_review, c.user_review_vi, c.user_score, c.user_keywords,
                    c.is_user_reviewed, c.user_reviewed_at, c.scraped_at,
                    p.content as post_content, p.categories as post_categories, p.author_username as post_author
                FROM comments c
                LEFT JOIN posts p ON c.post_id = p.id
                WHERE 1=1
            """
            params = []

            if search_kw:
                query += " AND (c.content LIKE ? OR c.matched_words LIKE ?)"
                kw_wildcard = f"%{search_kw.strip()}%"
                params.extend([kw_wildcard, kw_wildcard])

            if author_username:
                clean_user = author_username.strip().lstrip("@")
                query += " AND c.author_username = ?"
                params.append(clean_user)

            len_clause, len_params = self._build_length_condition(
                "c.content", min_length=min_length, max_length=max_length, length_op=length_op, length_val=length_val
            )
            query += len_clause
            params.extend(len_params)

            if filter_status == "bad":
                query += " AND (c.review_status = 'bad' OR c.toxic_score >= 0.5)"
            elif filter_status == "ambiguous":
                query += " AND (c.review_status = 'ambiguous' OR (c.toxic_score >= 0.15 AND c.toxic_score < 0.5))"
            elif filter_status == "clean":
                query += " AND (c.review_status = 'clean' OR c.toxic_score < 0.15)"

            if filter_comment_type == "root":
                query += " AND (c.is_reply = 0 OR c.is_reply IS NULL)"
            elif filter_comment_type == "reply":
                query += " AND c.is_reply = 1"

            cat_clause, cat_params = self._build_category_condition(filter_category, c_alias="c", p_alias="p")
            query += cat_clause
            params.extend(cat_params)

            post_clause, post_params = self._build_post_condition(filter_post, c_alias="c")
            query += post_clause
            params.extend(post_params)

            if order_by == "oldest":
                query += " ORDER BY c.scraped_at ASC"
            elif order_by == "toxic_score_desc":
                query += " ORDER BY c.toxic_score DESC, c.scraped_at DESC"
            elif order_by == "shortest_first":
                query += " ORDER BY LENGTH(TRIM(c.content)) ASC, c.scraped_at DESC"
            else:  # newest
                query += " ORDER BY c.scraped_at DESC"

            query += f" LIMIT 1 OFFSET {max(0, int(index))}"
            cursor = conn.cursor()
            row = cursor.execute(query, params).fetchone()
            if not row:
                return None

            item = dict(row)
            def safe_json(val):
                if not val:
                    return []
                try:
                    res = json.loads(val)
                    return res if isinstance(res, list) else [res]
                except Exception:
                    return [val] if val else []

            item["matched_words_list"] = safe_json(item.get("matched_words"))
            item["matched_emojis_list"] = safe_json(item.get("matched_emojis"))
            item["categories_list"] = safe_json(item.get("categories"))
            item["user_keywords_list"] = safe_json(item.get("user_keywords"))
            item["post_categories_list"] = safe_json(item.get("post_categories"))
            return item

    def clear_all_data(self) -> Dict[str, int]:
        """
        Xóa TOÀN BỘ dữ liệu: comments, posts và crawl_sessions.
        ⚠️ Hành động này KHÔNG THỂ HOÀN TÁC.
        Trả về dict với số lượng bản ghi đã xóa của từng bảng.
        """
        with self.get_connection() as conn:
            n_comments = conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
            n_posts    = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
            n_sessions = conn.execute("SELECT COUNT(*) FROM crawl_sessions").fetchone()[0]

            conn.execute("DELETE FROM comments")
            conn.execute("DELETE FROM posts")
            conn.execute("DELETE FROM crawl_sessions")
            # Reset auto-increment counters nếu có (SQLite với AUTOINCREMENT)
            try:
                conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('comments','posts','crawl_sessions')")
            except Exception:
                pass  # sqlite_sequence không tồn tại nếu DB không dùng AUTOINCREMENT
            conn.commit()

        logger.warning(
            f"[CLEAR ALL] Đã xóa toàn bộ CSDL: "
            f"{n_comments} bình luận, {n_posts} bài đăng, {n_sessions} phiên cào."
        )
        return {
            "deleted_comments": n_comments,
            "deleted_posts":    n_posts,
            "deleted_sessions": n_sessions,
        }

# Global DB manager instance
db_manager = DatabaseManager()
