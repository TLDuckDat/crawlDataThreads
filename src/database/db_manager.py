import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
import pandas as pd
from datetime import datetime
from contextlib import contextmanager

from config.settings import DB_PATH
from src.database.models import PostModel, CommentModel, CrawlSessionModel
from src.detector.text_normalizer import is_valid_viet_eng_content, clean_to_viet_eng
from src.utils.logger import logger

class DatabaseManager:
    """Manages SQLite storage, indexing, and categorized comment exports for Threads toxic data."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
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
            "user_reviewed_at": "TEXT DEFAULT ''"
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
                    is_reply, parent_comment_id, comment_type_vi, image_urls,
                    is_toxic, toxic_score, severity_vi, review_status, review_status_vi,
                    has_emoji_slang, matched_words, matched_emojis, categories, session_id, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    content=excluded.content,
                    likes=excluded.likes,
                    reply_to=excluded.reply_to,
                    is_reply=excluded.is_reply,
                    parent_comment_id=excluded.parent_comment_id,
                    comment_type_vi=excluded.comment_type_vi,
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

    def get_detailed_export_df(self, table_type: str = "comments", toxic_only: bool = False, limit: Optional[int] = None) -> pd.DataFrame:
        """Backward-compatible helper calling get_comments_export_df with full links."""
        filter_status = "toxic_only" if toxic_only else "all"
        return self.get_comments_export_df(filter_status=filter_status, include_links=True, limit=limit)

    def get_comments_export_df(
        self,
        filter_status: Optional[str] = None,       # "all", "bad", "ambiguous", "clean", or "toxic_only"
        filter_comment_type: Optional[str] = None, # "all", "root" (Bình luận gốc), "reply" (Bình luận con)
        include_links: bool = False,                # Mặc định False để tập trung vào bình luận
        limit: Optional[int] = None,               # None = Không giới hạn số lượng
        viet_eng_only: bool = True                  # Bỏ qua bình luận tiếng Trung, Nhật, Hàn...
    ) -> pd.DataFrame:
        """
        Specialized exporter for Comments:
        - Automatically groups/filters into:
            * 'bad': Dữ liệu đánh giá là Xấu luôn (Rõ ràng)
            * 'ambiguous': Dữ liệu Chưa rõ (Nghi ngờ / Cần duyệt lại)
            * 'all': Toàn bộ bình luận để người dùng tự tổng hợp
        - filter_comment_type:
            * 'root': Chỉ bình luận gốc
            * 'reply': Chỉ bình luận con (phản hồi)
            * 'all' hoặc None: Cả bình luận gốc và bình luận con
        - Default includes ONLY comment text and classification (no link clutter)
        - If include_links=True, adds Post URL, Comment URL, Profile URL, IDs, Parent Comment ID.
        - limit: None hoặc 0 để lấy toàn bộ dữ liệu không giới hạn.
        - viet_eng_only: Lọc bỏ tiếng Trung, Nhật, Hàn... và làm sạch ký tự.
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

            # Clean focused comment columns
            core_columns = [
                ("author_username", "Tài khoản tác giả (@Username)"),
                ("author_name", "Tên hiển thị (Display Name)"),
                ("comment_type_vi", "Loại bình luận (Gốc / Bình luận con)"),
                ("reply_to", "Phản hồi cho (@Reply To)"),
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
        viet_eng_only: bool = True
    ) -> pd.DataFrame:
        """
        Query comments joined with posts, returning the 4 core requested columns:
        1. Nội dung (Comment text)
        2. Điểm đánh giá (Score & Level)
        3. Bài viết (Original Post text / Context)
        4. Chủ đề bài viết (Post category / topics)
        + 1 auxiliary column for manual self-annotation.
        - viet_eng_only: Lọc bỏ các bình luận tiếng Trung, Nhật, Hàn... và làm sạch ký tự.
        """
        with self.get_connection() as conn:
            query = """
                SELECT 
                    c.id as comment_id,
                    c.content as comment_content,
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
            if df.empty:
                return pd.DataFrame(columns=[
                    "Mã ID",
                    "Nội dung",
                    "Điểm đánh giá",
                    "Bài viết",
                    "Chủ đề bài viết",
                    "Tự đánh giá của bạn (Xấu luôn / Chưa rõ / Trong sạch)",
                    "Từ lóng mới bổ sung (nếu có)"
                ])

            # Filter out Chinese, Japanese, Korean, and other foreign language content
            if viet_eng_only:
                df = df[df["comment_content"].apply(is_valid_viet_eng_content)].copy()
                if df.empty:
                    return pd.DataFrame(columns=[
                        "Mã ID",
                        "Nội dung",
                        "Điểm đánh giá",
                        "Bài viết",
                        "Chủ đề bài viết",
                        "Tự đánh giá của bạn (Xấu luôn / Chưa rõ / Trong sạch)",
                        "Từ lóng mới bổ sung (nếu có)"
                    ])

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

            out_df = pd.DataFrame()
            out_df["Mã ID"] = df["comment_id"]
            out_df["Nội dung"] = df["comment_content"].apply(clean_to_viet_eng) if viet_eng_only else df["comment_content"]
            out_df["Điểm đánh giá"] = df.apply(format_score_display, axis=1)
            out_df["Bài viết"] = df.apply(format_post_content, axis=1)
            out_df["Chủ đề bài viết"] = df.apply(format_categories, axis=1)
            out_df["Tự đánh giá của bạn (Xấu luôn / Chưa rõ / Trong sạch)"] = df["user_review_vi"].fillna("")
            out_df["Từ lóng mới bổ sung (nếu có)"] = df.apply(format_user_keywords, axis=1)

            return out_df

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
