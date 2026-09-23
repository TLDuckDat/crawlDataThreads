"""
Unit tests for Category / Topic Purge and Filtering in Threads Bad Data Collector.
Verifies:
1. get_all_categories_in_db
2. count_content_by_category
3. delete_content_by_category (full wipe of posts, comments, replies)
4. keep_reviewed protection during category purge
5. get_category_preview
6. filter_category in cleanup queries
"""

import unittest
import tempfile
import json
from pathlib import Path

from src.database.db_manager import DatabaseManager
from src.database.models import PostModel, CommentModel


class TestCategoryPurge(unittest.TestCase):
    """Test suite for topic/category based content counting, filtering, and purging."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_cat_purge.db"
        self.db = DatabaseManager(self.db_path)

        # ─── Topic A: "Phân biệt vùng miền" ───
        # Post A1
        self.db.upsert_post(PostModel(
            id="post_region_1",
            url="https://threads.net/@u1/post/p1",
            author_username="u1",
            content="Bài viết về phân biệt vùng miền",
            categories=["Phân biệt vùng miền"]
        ))

        # Comment on Post A1 (inherits topic from post)
        self.db.upsert_comment(CommentModel(
            id="c_p1_root",
            post_id="post_region_1",
            post_url="https://threads.net/@u1/post/p1",
            author_username="u2",
            content="Comment gốc trên bài vùng miền",
            is_reply=False
        ))

        # Reply on Post A1
        self.db.upsert_comment(CommentModel(
            id="c_p1_reply",
            post_id="post_region_1",
            post_url="https://threads.net/@u1/post/p1",
            author_username="u3",
            content="Reply con trên bài vùng miền",
            is_reply=True,
            parent_comment_id="c_p1_root",
            f0="Comment gốc trên bài vùng miền",
            f1="Reply con trên bài vùng miền",
            reply_level=1
        ))

        # ─── Topic B: "Chửi thề / Tục tĩu" ───
        # Post B1
        self.db.upsert_post(PostModel(
            id="post_profanity_1",
            url="https://threads.net/@u4/post/p2",
            author_username="u4",
            content="Bài viết về đời sống thường ngày",
            categories=["Chửi thề / Tục tĩu"]
        ))

        # Comment with direct category tag on Post B1
        self.db.upsert_comment(CommentModel(
            id="c_p2_profane",
            post_id="post_profanity_1",
            post_url="https://threads.net/@u4/post/p2",
            author_username="u5",
            content="Bình luận chửi bới tục tĩu",
            categories=["Chửi thề / Tục tĩu"]
        ))

        # ─── Direct Tag on neutral post: ───
        # Post C: neutral
        self.db.upsert_post(PostModel(
            id="post_neutral_1",
            url="https://threads.net/@u6/post/p3",
            author_username="u6",
            content="Bài viết giải trí vui vẻ",
            categories=["Giải trí"]
        ))

        # Comment directly tagged with "Phân biệt vùng miền" on neutral post
        self.db.upsert_comment(CommentModel(
            id="c_neutral_region",
            post_id="post_neutral_1",
            post_url="https://threads.net/@u6/post/p3",
            author_username="u7",
            content="Comment phân biệt vùng miền lạc đề",
            categories=["Phân biệt vùng miền"]
        ))

        # Normal clean comment on neutral post
        self.db.upsert_comment(CommentModel(
            id="c_neutral_clean",
            post_id="post_neutral_1",
            post_url="https://threads.net/@u6/post/p3",
            author_username="u8",
            content="Bài viết hay lắm bạn ơi",
            categories=["Giải trí"]
        ))

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_get_all_categories_in_db(self):
        """Test retrieving all distinct categories across posts and comments."""
        cats = self.db.get_all_categories_in_db()
        self.assertIn("Phân biệt vùng miền", cats)
        self.assertIn("Chửi thề / Tục tĩu", cats)
        self.assertIn("Giải trí", cats)

    def test_count_content_by_category(self):
        """Test counting posts and comments associated with a category."""
        # "Phân biệt vùng miền":
        # Post: post_region_1 (1 post)
        # Comments: c_p1_root, c_p1_reply (belonging to post_region_1) + c_neutral_region (tagged) = 3 comments
        cnt = self.db.count_content_by_category("Phân biệt vùng miền")
        self.assertEqual(cnt["posts_count"], 1)
        self.assertEqual(cnt["comments_count"], 3)
        self.assertEqual(cnt["total_items"], 4)

        # "Chửi thề / Tục tĩu":
        # Post: post_profanity_1 (1 post)
        # Comments: c_p2_profane (1 comment)
        cnt_profane = self.db.count_content_by_category("Chửi thề / Tục tĩu")
        self.assertEqual(cnt_profane["posts_count"], 1)
        self.assertEqual(cnt_profane["comments_count"], 1)
        self.assertEqual(cnt_profane["total_items"], 2)

    def test_delete_content_by_category(self):
        """
        Test that deleting a category wipes all posts, all comments on those posts,
        and all comments tagged with that category, while leaving other categories completely intact.
        """
        res = self.db.delete_content_by_category("Phân biệt vùng miền")
        self.assertEqual(res["deleted_posts"], 1)
        self.assertEqual(res["deleted_comments"], 3)

        with self.db.get_connection() as conn:
            # post_region_1 should be gone
            rem_p = conn.execute("SELECT id FROM posts").fetchall()
            rem_p_ids = [r[0] for r in rem_p]
            self.assertNotIn("post_region_1", rem_p_ids)
            self.assertIn("post_profanity_1", rem_p_ids)
            self.assertIn("post_neutral_1", rem_p_ids)

            # c_p1_root, c_p1_reply, c_neutral_region should be gone
            rem_c = conn.execute("SELECT id FROM comments").fetchall()
            rem_c_ids = [r[0] for r in rem_c]
            self.assertNotIn("c_p1_root", rem_c_ids)
            self.assertNotIn("c_p1_reply", rem_c_ids)
            self.assertNotIn("c_neutral_region", rem_c_ids)

            # other comments must remain intact!
            self.assertIn("c_p2_profane", rem_c_ids)
            self.assertIn("c_neutral_clean", rem_c_ids)

    def test_delete_content_by_category_with_protection(self):
        """Test that keep_reviewed=True protects human-reviewed comments during category purge."""
        # Mark c_neutral_region as user-reviewed
        self.db.update_user_review("c_neutral_region", user_review="bad")

        # Purge with keep_reviewed=True
        res = self.db.delete_content_by_category("Phân biệt vùng miền", keep_reviewed=True)
        # Should delete 1 post, and 2 unreviewed comments (c_p1_root, c_p1_reply), keeping c_neutral_region
        self.assertEqual(res["deleted_posts"], 1)
        self.assertEqual(res["deleted_comments"], 2)

        with self.db.get_connection() as conn:
            rem_c = conn.execute("SELECT id FROM comments").fetchall()
            rem_c_ids = [r[0] for r in rem_c]
            self.assertIn("c_neutral_region", rem_c_ids)

    def test_get_category_preview(self):
        """Test getting preview samples for a category."""
        prev = self.db.get_category_preview("Phân biệt vùng miền", limit=5)
        self.assertEqual(len(prev["sample_posts"]), 1)
        self.assertEqual(prev["sample_posts"][0]["id"], "post_region_1")
        self.assertEqual(len(prev["sample_comments"]), 1)
        self.assertEqual(prev["sample_comments"][0]["id"], "c_neutral_region")

    def test_cleanup_filter_by_category(self):
        """Test filtering cleanup comments and counts by category."""
        # Comments matching "Phân biệt vùng miền" (either in comment categories or post categories)
        cnt = self.db.count_cleanup_comments(filter_category="Phân biệt vùng miền")
        self.assertEqual(cnt, 3)

        df = self.db.get_comments_for_cleanup_df(filter_category="Phân biệt vùng miền")
        self.assertEqual(len(df), 3)

        item = self.db.get_cleanup_comment_at_index(0, filter_category="Phân biệt vùng miền")
        self.assertIsNotNone(item)


    def test_count_content_by_multiple_categories(self):
        """Test counting posts and comments across multiple categories simultaneously."""
        # "Phân biệt vùng miền" (1 post, 3 comments) + "Chửi thề / Tục tĩu" (1 post, 1 comment)
        cnt = self.db.count_content_by_categories(["Phân biệt vùng miền", "Chửi thề / Tục tĩu"])
        self.assertEqual(cnt["posts_count"], 2)
        self.assertEqual(cnt["comments_count"], 4)
        self.assertEqual(cnt["total_items"], 6)
        self.assertEqual(len(cnt["by_category"]), 2)
        self.assertIn("Phân biệt vùng miền", cnt["by_category"])
        self.assertIn("Chửi thề / Tục tĩu", cnt["by_category"])

    def test_delete_content_by_multiple_categories(self):
        """Test deleting multiple categories at once in a single bulk operation."""
        res = self.db.delete_content_by_categories(["Phân biệt vùng miền", "Chửi thề / Tục tĩu"])
        self.assertEqual(res["deleted_posts"], 2)
        self.assertEqual(res["deleted_comments"], 4)

        with self.db.get_connection() as conn:
            rem_p = conn.execute("SELECT id FROM posts").fetchall()
            rem_p_ids = [r[0] for r in rem_p]
            self.assertEqual(rem_p_ids, ["post_neutral_1"])

            rem_c = conn.execute("SELECT id FROM comments").fetchall()
            rem_c_ids = [r[0] for r in rem_c]
            self.assertEqual(rem_c_ids, ["c_neutral_clean"])

    def test_get_categories_preview_multiple(self):
        """Test previewing samples across multiple selected categories."""
        prev = self.db.get_categories_preview(["Phân biệt vùng miền", "Chửi thề / Tục tĩu"], limit=5)
        self.assertEqual(len(prev["sample_posts"]), 2)
        # sample_comments has c_p2_profane and c_neutral_region
        self.assertEqual(len(prev["sample_comments"]), 2)

    def test_filter_cleanup_by_multiple_categories(self):
        """Test filtering cleanup comments and counts by a list of multiple categories."""
        cnt = self.db.count_cleanup_comments(filter_category=["Phân biệt vùng miền", "Chửi thề / Tục tĩu"])
        self.assertEqual(cnt, 4)

        df = self.db.get_comments_for_cleanup_df(filter_category=["Phân biệt vùng miền", "Chửi thề / Tục tĩu"])
        self.assertEqual(len(df), 4)


if __name__ == "__main__":
    unittest.main()

