"""
Unit tests for Post Cascade Deletion in Threads Bad Data Collector.
Verifies:
1. get_posts_for_management (listing posts with actual comment counts)
2. get_post_details (retrieving post details and sample comments)
3. count_content_by_posts (counting posts and related comments)
4. delete_post_cascade (full wipe of post and all comments on that post)
5. delete_posts_cascade (bulk wipe of multiple posts and all comments on them)
6. keep_reviewed protection during post purge
7. purge by URL or ID
"""

import unittest
import tempfile
from pathlib import Path

from src.database.db_manager import DatabaseManager
from src.database.models import PostModel, CommentModel


class TestPostPurge(unittest.TestCase):
    """Test suite for post-level cascade purging."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_post_purge.db"
        self.db = DatabaseManager(self.db_path)

        # ─── Post 1: target for deletion ───
        self.db.upsert_post(PostModel(
            id="post_target_1",
            url="https://threads.net/@u1/post/p1",
            author_username="u1",
            content="Bài viết drama số 1",
            likes=10,
            replies_count=2
        ))

        # Root comment on Post 1
        self.db.upsert_comment(CommentModel(
            id="c_p1_root",
            post_id="post_target_1",
            post_url="https://threads.net/@u1/post/p1",
            author_username="u2",
            content="Comment gốc trên bài 1",
            is_reply=False
        ))

        # Child reply on Post 1
        self.db.upsert_comment(CommentModel(
            id="c_p1_reply",
            post_id="post_target_1",
            post_url="https://threads.net/@u1/post/p1",
            author_username="u3",
            content="Comment con F1 trên bài 1",
            is_reply=True,
            parent_comment_id="c_p1_root",
            f0="Comment gốc trên bài 1",
            f1="Comment con F1 trên bài 1",
            reply_level=1
        ))

        # ─── Post 2: another target ───
        self.db.upsert_post(PostModel(
            id="post_target_2",
            url="https://threads.net/@u4/post/p2",
            author_username="u4",
            content="Bài viết drama số 2",
            likes=5,
            replies_count=1
        ))

        self.db.upsert_comment(CommentModel(
            id="c_p2_root",
            post_id="post_target_2",
            post_url="https://threads.net/@u4/post/p2",
            author_username="u5",
            content="Comment trên bài 2",
            is_reply=False
        ))

        # ─── Post 3: keeper post (must never be touched) ───
        self.db.upsert_post(PostModel(
            id="post_keeper",
            url="https://threads.net/@u6/post/p3",
            author_username="u6",
            content="Bài viết lành mạnh cần giữ lại",
            likes=100,
            replies_count=1
        ))

        self.db.upsert_comment(CommentModel(
            id="c_p3_root",
            post_id="post_keeper",
            post_url="https://threads.net/@u6/post/p3",
            author_username="u7",
            content="Comment trên bài keeper",
            is_reply=False
        ))

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_get_posts_for_management(self):
        """Test listing posts for management with comment counts."""
        df = self.db.get_posts_for_management()
        self.assertEqual(len(df), 3)
        self.assertIn("actual_comments_count", df.columns)

        p1_row = df[df["id"] == "post_target_1"].iloc[0]
        self.assertEqual(p1_row["actual_comments_count"], 2)

        p2_row = df[df["id"] == "post_target_2"].iloc[0]
        self.assertEqual(p2_row["actual_comments_count"], 1)

        # Test search filter
        df_search = self.db.get_posts_for_management(search_kw="drama")
        self.assertEqual(len(df_search), 2)

    def test_get_post_details(self):
        """Test getting detailed information and sample comments for a post."""
        details = self.db.get_post_details("post_target_1")
        self.assertIsNotNone(details)
        self.assertEqual(details["id"], "post_target_1")
        self.assertEqual(details["actual_comments_count"], 2)
        self.assertEqual(len(details["sample_comments"]), 2)

    def test_count_content_by_posts(self):
        """Test counting posts and related comments."""
        cnt = self.db.count_content_by_posts(["post_target_1"])
        self.assertEqual(cnt["posts_count"], 1)
        self.assertEqual(cnt["comments_count"], 2)
        self.assertEqual(cnt["total_items"], 3)

        cnt_multi = self.db.count_content_by_posts(["post_target_1", "post_target_2"])
        self.assertEqual(cnt_multi["posts_count"], 2)
        self.assertEqual(cnt_multi["comments_count"], 3)
        self.assertEqual(cnt_multi["total_items"], 5)

    def test_delete_post_cascade_single(self):
        """Test cascade deleting a single post and all its related comments."""
        res = self.db.delete_post_cascade("post_target_1")
        self.assertEqual(res["deleted_posts"], 1)
        self.assertEqual(res["deleted_comments"], 2)

        with self.db.get_connection() as conn:
            rem_p = conn.execute("SELECT id FROM posts").fetchall()
            rem_p_ids = [r[0] for r in rem_p]
            self.assertNotIn("post_target_1", rem_p_ids)
            self.assertIn("post_target_2", rem_p_ids)
            self.assertIn("post_keeper", rem_p_ids)

            rem_c = conn.execute("SELECT id FROM comments").fetchall()
            rem_c_ids = [r[0] for r in rem_c]
            self.assertNotIn("c_p1_root", rem_c_ids)
            self.assertNotIn("c_p1_reply", rem_c_ids)
            self.assertIn("c_p2_root", rem_c_ids)
            self.assertIn("c_p3_root", rem_c_ids)

    def test_delete_posts_cascade_multiple(self):
        """Test cascade deleting multiple posts at once."""
        res = self.db.delete_posts_cascade(["post_target_1", "post_target_2"])
        self.assertEqual(res["deleted_posts"], 2)
        self.assertEqual(res["deleted_comments"], 3)

        with self.db.get_connection() as conn:
            rem_p = conn.execute("SELECT id FROM posts").fetchall()
            rem_p_ids = [r[0] for r in rem_p]
            self.assertEqual(rem_p_ids, ["post_keeper"])

            rem_c = conn.execute("SELECT id FROM comments").fetchall()
            rem_c_ids = [r[0] for r in rem_c]
            self.assertEqual(rem_c_ids, ["c_p3_root"])

    def test_delete_post_cascade_keep_reviewed(self):
        """Test that keep_reviewed=True protects human-reviewed comments during post deletion."""
        # Mark c_p1_reply as reviewed
        self.db.update_user_review("c_p1_reply", user_review="bad")

        res = self.db.delete_post_cascade("post_target_1", keep_reviewed=True)
        self.assertEqual(res["deleted_posts"], 1)
        # Only unreviewed comment c_p1_root should be deleted
        self.assertEqual(res["deleted_comments"], 1)

        with self.db.get_connection() as conn:
            rem_c = conn.execute("SELECT id FROM comments").fetchall()
            rem_c_ids = [r[0] for r in rem_c]
            self.assertNotIn("c_p1_root", rem_c_ids)
            self.assertIn("c_p1_reply", rem_c_ids)

    def test_delete_post_cascade_by_url(self):
        """Test deleting a post by URL instead of ID."""
        res = self.db.delete_post_cascade("https://threads.net/@u1/post/p1")
        self.assertEqual(res["deleted_posts"], 1)
        self.assertEqual(res["deleted_comments"], 2)

        with self.db.get_connection() as conn:
            rem_p = conn.execute("SELECT id FROM posts").fetchall()
            rem_p_ids = [r[0] for r in rem_p]
            self.assertNotIn("post_target_1", rem_p_ids)

    def test_filter_comments_by_post_queries(self):
        """Test counting, listing, and indexing cleanup comments filtered by post."""
        # 1. Count by post ID
        cnt_p1 = self.db.count_cleanup_comments(filter_post="post_target_1")
        self.assertEqual(cnt_p1, 2)

        # 2. Count by post URL
        cnt_url = self.db.count_cleanup_comments(filter_post="https://threads.net/@u1/post/p1")
        self.assertEqual(cnt_url, 2)

        # 3. Count by multiple posts
        cnt_multi = self.db.count_cleanup_comments(filter_post=["post_target_1", "post_target_2"])
        self.assertEqual(cnt_multi, 3)

        # 4. Get cleanup dataframe filtered by post
        df_p1 = self.db.get_comments_for_cleanup_df(filter_post="post_target_1")
        self.assertEqual(len(df_p1), 2)
        p1_comment_ids = df_p1["id"].tolist()
        self.assertIn("c_p1_root", p1_comment_ids)
        self.assertIn("c_p1_reply", p1_comment_ids)
        self.assertIn("post_author", df_p1.columns)
        self.assertIn("post_content", df_p1.columns)
        self.assertIn("post_summary", df_p1.columns)
        self.assertIn("post_id", df_p1.columns)
        self.assertEqual(df_p1.iloc[0]["post_author"], "u1")
        self.assertIn("[@u1]", df_p1.iloc[0]["post_summary"])
        self.assertIn("drama số 1", df_p1.iloc[0]["post_summary"])

        # 5. Get comment at index filtered by post
        c_at_0 = self.db.get_cleanup_comment_at_index(0, filter_post="post_target_1")
        self.assertIsNotNone(c_at_0)
        self.assertEqual(c_at_0["post_id"], "post_target_1")

    def test_delete_comments_by_post_filter_all(self):
        """Test deleting all comments belonging to a filtered post while keeping post record intact."""
        del_cnt = self.db.delete_comments_by_filter(filter_post="post_target_1", keep_reviewed=False)
        self.assertEqual(del_cnt, 2)

        with self.db.get_connection() as conn:
            # Post itself still exists
            p_ids = [r[0] for r in conn.execute("SELECT id FROM posts").fetchall()]
            self.assertIn("post_target_1", p_ids)

            # Comments of post 1 are deleted
            c_ids = [r[0] for r in conn.execute("SELECT id FROM comments").fetchall()]
            self.assertNotIn("c_p1_root", c_ids)
            self.assertNotIn("c_p1_reply", c_ids)

            # Comments of other posts still exist
            self.assertIn("c_p2_root", c_ids)
            self.assertIn("c_p3_root", c_ids)

    def test_delete_selected_comments_of_post(self):
        """Test selecting specific comments under a filtered post to delete (chọn đối tượng cần xóa)."""
        # Under post_target_1, we select only c_p1_reply to delete
        deleted = self.db.delete_comments(["c_p1_reply"], cascade=False)
        self.assertEqual(deleted, 1)

        # Post 1 still has root comment, but reply is gone
        cnt_p1_rem = self.db.count_cleanup_comments(filter_post="post_target_1")
        self.assertEqual(cnt_p1_rem, 1)

        with self.db.get_connection() as conn:
            c_ids = [r[0] for r in conn.execute("SELECT id FROM comments").fetchall()]
            self.assertIn("c_p1_root", c_ids)
            self.assertNotIn("c_p1_reply", c_ids)

    def test_cleanup_df_pagination(self):
        """Test pagination support (limit, offset, order_by) in get_comments_for_cleanup_df."""
        # Total comments in setUp is 4 (c_p1_root, c_p1_reply, c_p2_root, c_p3_root)
        total_count = self.db.count_cleanup_comments()
        self.assertEqual(total_count, 4)

        # Page 1 (limit=2, offset=0)
        df_p1 = self.db.get_comments_for_cleanup_df(limit=2, offset=0, order_by="oldest")
        self.assertEqual(len(df_p1), 2)

        # Page 2 (limit=2, offset=2)
        df_p2 = self.db.get_comments_for_cleanup_df(limit=2, offset=2, order_by="oldest")
        self.assertEqual(len(df_p2), 2)

        # Ensure no overlap between page 1 and page 2
        p1_ids = set(df_p1["id"].tolist())
        p2_ids = set(df_p2["id"].tolist())
        self.assertEqual(len(p1_ids.intersection(p2_ids)), 0)
        self.assertEqual(len(p1_ids.union(p2_ids)), 4)

        # Test get_posts_for_management with limit=None
        df_posts_all = self.db.get_posts_for_management(limit=None)
        self.assertEqual(len(df_posts_all), 3)

    def test_cleanup_modes_flow(self):
        """Test simulating filter signature and pagination data flow for Data Editor mode."""
        import math

        search_kw = ""
        author_kw = ""
        filter_status = "all"
        filter_ctype = "all"
        cat_filter_val = None
        post_filter_val = None
        fl_op = None
        fl_val = None
        fl_min = None
        fl_max = None
        order_label_clean = "newest"

        # clean_sig must be definable in outer scope
        clean_sig = f"{search_kw}_{author_kw}_{filter_status}_{filter_ctype}_{cat_filter_val}_{post_filter_val}_{fl_op}_{fl_val}_{fl_min}_{fl_max}_{order_label_clean}"
        self.assertIsNotNone(clean_sig)

        # In Data Editor mode, tbl_sig can be constructed without NameError
        page_size = 50
        effective_post_filter = None
        tbl_sig = f"{clean_sig}_{effective_post_filter}_{page_size}"
        self.assertIn("50", tbl_sig)

        total_matching = self.db.count_cleanup_comments(filter_post=effective_post_filter)
        total_pages = max(1, math.ceil(total_matching / page_size))
        self.assertEqual(total_pages, 1)

        df_page = self.db.get_comments_for_cleanup_df(
            filter_post=effective_post_filter,
            limit=page_size,
            offset=0
        )
        self.assertEqual(len(df_page), 4)
        self.assertIn("post_summary", df_page.columns)


if __name__ == "__main__":
    unittest.main()
