import unittest
import tempfile
from pathlib import Path

from src.database.models import CommentModel, PostModel
from src.database.db_manager import DatabaseManager

class TestCommentCleanup(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_cleanup.db"
        self.db = DatabaseManager(db_path=self.db_path)

        # Seed post
        post = PostModel(
            id="post_clean_1",
            url="https://www.threads.net/@user/post/clean1",
            author_username="test_author",
            content="Bài viết kiểm thử tính năng lọc xóa",
            categories=["Kiểm thử"]
        )
        self.db.upsert_post(post)

        # Seed comments:
        # 1. Normal comment
        self.db.upsert_comment(CommentModel(
            id="c_normal_1",
            post_id="post_clean_1",
            post_url="https://www.threads.net/@user/post/clean1",
            author_username="user_normal",
            content="Bài viết này rất hữu ích, cảm ơn bạn nhiều",
            comment_type_vi="Bình luận gốc"
        ))

        # 2. Short spam comment (<= 2 chars)
        self.db.upsert_comment(CommentModel(
            id="c_short_1",
            post_id="post_clean_1",
            post_url="https://www.threads.net/@user/post/clean1",
            author_username="user_spammer",
            content=".",
            comment_type_vi="Bình luận gốc"
        ))

        # 3. Keyword spam comment ("check inbox mua hàng shopee")
        self.db.upsert_comment(CommentModel(
            id="c_spam_kw_1",
            post_id="post_clean_1",
            post_url="https://www.threads.net/@user/post/clean1",
            author_username="user_bot",
            content="Mọi người vào shopee săn sale và check inbox em nhé",
            comment_type_vi="Bình luận con (Phản hồi)",
            is_reply=True
        ))

        # 4. Spammer user comment
        self.db.upsert_comment(CommentModel(
            id="c_spammer_2",
            post_id="post_clean_1",
            post_url="https://www.threads.net/@user/post/clean1",
            author_username="spambot999",
            content="Follow chéo nhau đi mn ơi link bio",
            comment_type_vi="Bình luận gốc"
        ))

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_get_comments_for_cleanup_df(self):
        """Test retrieving cleanup DataFrame with filter options."""
        df_all = self.db.get_comments_for_cleanup_df()
        self.assertEqual(len(df_all), 4)
        self.assertIn("content_length", df_all.columns)
        self.assertIn("author_username", df_all.columns)
        self.assertIn("comment_type_vi", df_all.columns)

        # Filter by keyword
        df_kw = self.db.get_comments_for_cleanup_df(search_kw="shopee")
        self.assertEqual(len(df_kw), 1)
        self.assertEqual(df_kw.iloc[0]["id"], "c_spam_kw_1")

        # Filter by short length
        df_short = self.db.get_comments_for_cleanup_df(max_length=2)
        self.assertEqual(len(df_short), 1)
        self.assertEqual(df_short.iloc[0]["id"], "c_short_1")

        # Filter by author
        df_author = self.db.get_comments_for_cleanup_df(author_username="spambot999")
        self.assertEqual(len(df_author), 1)
        self.assertEqual(df_author.iloc[0]["id"], "c_spammer_2")

    def test_delete_comments_by_id_list(self):
        """Test deleting specific comments by their IDs."""
        deleted = self.db.delete_comments(["c_short_1", "c_spammer_2"])
        self.assertEqual(deleted, 2)

        df_remain = self.db.get_comments_for_cleanup_df()
        self.assertEqual(len(df_remain), 2)
        remaining_ids = df_remain["id"].tolist()
        self.assertNotIn("c_short_1", remaining_ids)
        self.assertNotIn("c_spammer_2", remaining_ids)
        self.assertIn("c_normal_1", remaining_ids)
        self.assertIn("c_spam_kw_1", remaining_ids)

    def test_delete_comments_by_search_keyword(self):
        """Test bulk deleting comments matching a keyword."""
        deleted = self.db.delete_comments_by_filter(search_kw="shopee")
        self.assertEqual(deleted, 1)

        df = self.db.get_comments_for_cleanup_df()
        self.assertEqual(len(df), 3)
        self.assertNotIn("c_spam_kw_1", df["id"].tolist())

    def test_delete_comments_by_max_length(self):
        """Test bulk deleting very short spam comments."""
        deleted = self.db.delete_comments_by_filter(max_length=2)
        self.assertEqual(deleted, 1)

        df = self.db.get_comments_for_cleanup_df()
        self.assertNotIn("c_short_1", df["id"].tolist())

    def test_delete_comments_by_author(self):
        """Test bulk deleting all comments by a specific author."""
        deleted = self.db.delete_comments_by_filter(author_username="@spambot999")
        self.assertEqual(deleted, 1)

        df = self.db.get_comments_for_cleanup_df()
        self.assertNotIn("c_spammer_2", df["id"].tolist())

    def test_curated_export_omits_deleted_comments(self):
        """Test that after deleting comments, curated export DataFrame immediately omits them."""
        # Delete the spam comments
        self.db.delete_comments(["c_short_1", "c_spam_kw_1", "c_spammer_2"])

        df_export = self.db.get_curated_export_df()
        self.assertEqual(len(df_export), 1)
        self.assertEqual(df_export.iloc[0]["Mã ID"], "c_normal_1")

if __name__ == "__main__":
    unittest.main()
