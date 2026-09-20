import unittest
import tempfile
from pathlib import Path
from src.database.models import PostModel, CommentModel
from src.database.db_manager import DatabaseManager

class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_threads.db"
        self.db = DatabaseManager(db_path=self.db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_upsert_and_deduplication(self):
        # Insert post
        post = PostModel(
            id="post_123",
            url="https://www.threads.net/@user/post/123",
            author_username="testuser",
            content="Đây là bài đăng kiểm thử",
            is_toxic=False,
            toxic_score=0.0
        )
        self.db.upsert_post(post)

        # Re-insert updated post (should deduplicate/update without error)
        post.content = "Nội dung cập nhật"
        self.db.upsert_post(post)

        df_posts = self.db.get_posts_df(toxic_only=False)
        self.assertEqual(len(df_posts), 1)
        self.assertEqual(df_posts.iloc[0]["content"], "Nội dung cập nhật")

    def test_comment_storage_and_stats(self):
        # Insert toxic comment
        c1 = CommentModel(
            id="cmt_1",
            post_id="post_123",
            post_url="https://www.threads.net/@user/post/123",
            author_username="toxic_guy",
            content="Đm ngu học vcl",
            is_toxic=True,
            toxic_score=0.9,
            matched_words=["đm", "ngu học", "vcl"],
            categories=["Chửi thề", "Lăng mạ"]
        )
        self.db.upsert_comment(c1)

        # Insert clean comment
        c2 = CommentModel(
            id="cmt_2",
            post_id="post_123",
            post_url="https://www.threads.net/@user/post/123",
            author_username="nice_guy",
            content="Bài viết hay quá cảm ơn bạn",
            is_toxic=False,
            toxic_score=0.0
        )
        self.db.upsert_comment(c2)

        stats = self.db.get_stats()
        self.assertEqual(stats["total_comments"], 2)
        self.assertEqual(stats["toxic_comments"], 1)

        # Check top words
        top_words = self.db.get_top_toxic_words(5)
        words = [w["word"] for w in top_words]
        self.assertIn("đm", words)

    def test_unlimited_query(self):
        # Insert multiple comments
        for i in range(15):
            c = CommentModel(
                id=f"cmt_unlimited_{i}",
                post_id="post_123",
                post_url="https://www.threads.net/@user/post/123",
                author_username=f"user_{i}",
                content=f"Bình luận số {i}",
                is_toxic=(i % 2 == 0),
                toxic_score=0.8 if (i % 2 == 0) else 0.0,
                review_status="bad" if (i % 2 == 0) else "clean"
            )
            self.db.upsert_comment(c)

        # Test limit=None (unlimited)
        df_all = self.db.get_comments_export_df(limit=None)
        self.assertEqual(len(df_all), 15)

        # Test limit=0 (unlimited)
        df_zero = self.db.get_comments_export_df(limit=0)
        self.assertEqual(len(df_zero), 15)

        # Test with explicit limit
        df_limited = self.db.get_comments_export_df(limit=5)
        self.assertEqual(len(df_limited), 5)

    def test_child_comments_storage_and_hierarchy(self):
        # Insert a root comment
        c_root = CommentModel(
            id="cmt_root_101",
            post_id="post_999",
            post_url="https://www.threads.net/@target/post/999",
            author_username="root_user",
            content="Đây là bình luận gốc cấp 1",
            is_reply=False,
            comment_type_vi="Bình luận gốc"
        )
        self.db.upsert_comment(c_root)

        # Insert a child reply comment
        c_child = CommentModel(
            id="cmt_child_202",
            post_id="post_999",
            post_url="https://www.threads.net/@target/post/999",
            author_username="child_user",
            content="Đây là bình luận con trả lời cho bình luận gốc",
            is_reply=True,
            parent_comment_id="cmt_root_101",
            reply_to="@root_user",
            comment_type_vi="Bình luận con (Phản hồi)"
        )
        self.db.upsert_comment(c_child)

        stats = self.db.get_stats()
        self.assertGreaterEqual(stats["total_root_comments"], 1)
        self.assertGreaterEqual(stats["total_child_comments"], 1)

        # Filter root only
        df_root = self.db.get_comments_export_df(filter_comment_type="root")
        self.assertTrue(all(val == "Bình luận gốc" for val in df_root["Loại bình luận (Gốc / Bình luận con)"]))

        # Filter reply only
        df_child = self.db.get_comments_export_df(filter_comment_type="reply")
        self.assertTrue(all(val == "Bình luận con (Phản hồi)" for val in df_child["Loại bình luận (Gốc / Bình luận con)"]))
        self.assertIn("@root_user", df_child["Phản hồi cho (@Reply To)"].values)

if __name__ == "__main__":
    unittest.main()
