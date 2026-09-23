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

    def test_count_cleanup_comments(self):
        """Test counting comments matching various cleanup filter criteria."""
        total = self.db.count_cleanup_comments()
        self.assertEqual(total, 4)

        # Keyword filter
        cnt_kw = self.db.count_cleanup_comments(search_kw="shopee")
        self.assertEqual(cnt_kw, 1)

        # Max length filter
        cnt_short = self.db.count_cleanup_comments(max_length=2)
        self.assertEqual(cnt_short, 1)

        # Author filter
        cnt_auth = self.db.count_cleanup_comments(author_username="spambot999")
        self.assertEqual(cnt_auth, 1)

        # Reply filter
        cnt_reply = self.db.count_cleanup_comments(filter_comment_type="reply")
        self.assertEqual(cnt_reply, 1)

    def test_get_cleanup_comment_at_index(self):
        """Test retrieving a single comment with full context for card view."""
        item = self.db.get_cleanup_comment_at_index(index=0)
        self.assertIsNotNone(item)
        self.assertIn("content", item)
        self.assertIn("author_username", item)
        self.assertIn("post_content", item)
        self.assertIn("matched_words_list", item)

        # Filter by keyword
        item_kw = self.db.get_cleanup_comment_at_index(index=0, search_kw="shopee")
        self.assertIsNotNone(item_kw)
        self.assertEqual(item_kw["id"], "c_spam_kw_1")
        self.assertEqual(item_kw["post_content"], "Bài viết kiểm thử tính năng lọc xóa")

    def test_single_comment_delete_workflow(self):
        """Test 1-by-1 deletion: deleting one item leaves the others intact and shifts index."""
        # Total before: 4
        self.assertEqual(self.db.count_cleanup_comments(), 4)

        # Get first item
        first_item = self.db.get_cleanup_comment_at_index(index=0, order_by="oldest")
        self.assertIsNotNone(first_item)
        del_id = first_item["id"]

        # Delete single comment
        deleted = self.db.delete_comments([del_id])
        self.assertEqual(deleted, 1)

        # Total after: 3
        self.assertEqual(self.db.count_cleanup_comments(), 3)

        # New first item should not be the deleted one
        new_first = self.db.get_cleanup_comment_at_index(index=0, order_by="oldest")
        self.assertIsNotNone(new_first)
        self.assertNotEqual(new_first["id"], del_id)

    def test_count_comments_by_length_operators(self):
        """Test count_comments_by_length with various operators (<=, >=, <, >, ==)."""
        # Comments lengths: 43, 1, 51, 34
        # <= 1: c_short_1 (len 1) -> 1
        self.assertEqual(self.db.count_comments_by_length("<=", 1), 1)
        # <= 2: c_short_1 (len 1) -> 1
        self.assertEqual(self.db.count_comments_by_length("<=", 2), 1)
        # < 2: c_short_1 (len 1) -> 1
        self.assertEqual(self.db.count_comments_by_length("<", 2), 1)
        # >= 40: c_normal_1 (43), c_spam_kw_1 (51) -> 2
        self.assertEqual(self.db.count_comments_by_length(">=", 40), 2)
        # > 50: c_spam_kw_1 (51) -> 1
        self.assertEqual(self.db.count_comments_by_length(">", 50), 1)
        # == 1: c_short_1 (1) -> 1
        self.assertEqual(self.db.count_comments_by_length("==", 1), 1)
        # == 100: none -> 0
        self.assertEqual(self.db.count_comments_by_length("==", 100), 0)

    def test_delete_comments_by_length_with_protection(self):
        """Test deleting comments by length with protect_reviewed option."""
        # Insert a reviewed short comment
        self.db.upsert_comment(CommentModel(
            id="c_short_reviewed",
            post_id="post_clean_1",
            post_url="https://www.threads.net/@user/post/clean1",
            author_username="user_reviewer",
            content="ok",
            is_user_reviewed=True,
            user_review="clean"
        ))
        self.db.update_user_review("c_short_reviewed", user_review="clean")

        # We now have: c_short_1 (len 1, unreviewed) and c_short_reviewed (len 2, reviewed)
        # With keep_reviewed=True (default), deleting <= 2 should only delete c_short_1
        deleted_protected = self.db.delete_comments_by_length("<=", 2, keep_reviewed=True)
        self.assertEqual(deleted_protected, 1)

        # Verify c_short_reviewed still exists
        item = self.db.get_cleanup_comment_at_index(index=0, search_kw="ok")
        self.assertIsNotNone(item)
        self.assertEqual(item["id"], "c_short_reviewed")

        # Now delete <= 2 with keep_reviewed=False -> should delete c_short_reviewed
        deleted_unprotected = self.db.delete_comments_by_length("<=", 2, keep_reviewed=False)
        self.assertEqual(deleted_unprotected, 1)

    def test_get_comments_by_length_preview(self):
        """Test previewing comments matching length criteria."""
        preview = self.db.get_comments_by_length_preview(">=", 40, limit=5)
        self.assertEqual(len(preview), 2)
        self.assertTrue(all(item["content_length"] >= 40 for item in preview))

    def test_cleanup_filter_by_range_and_op(self):
        """Test filtering cleanup comments by range (min_length, max_length) and length_op."""
        # Range 30 to 45: c_normal_1 (43), c_spammer_2 (34)
        df_range = self.db.get_comments_for_cleanup_df(min_length=30, max_length=45)
        self.assertEqual(len(df_range), 2)

        # Operator >= 50: c_spam_kw_1 (51)
        df_op = self.db.get_comments_for_cleanup_df(length_op=">=", length_val=50)
        self.assertEqual(len(df_op), 1)
        self.assertEqual(df_op.iloc[0]["id"], "c_spam_kw_1")

        cnt_op = self.db.count_cleanup_comments(length_op="<=", length_val=2)
        self.assertEqual(cnt_op, 1)

if __name__ == "__main__":
    unittest.main()

