import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.database.db_manager import DatabaseManager
from src.database.models import CommentModel, PostModel
from src.crawler.threads_crawler import ThreadsCrawler
from src.exporter.exporter import DataExporter


class TestDeduplication(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_dedup.db"
        self.db_manager = DatabaseManager(db_path=self.db_path)
        self.export_dir = Path(self.temp_dir) / "exports"
        self.exporter = DataExporter(export_dir=self.export_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_comment_and_post_exists(self):
        """Test comment_exists and post_exists methods."""
        post = PostModel(
            id="post_1",
            url="https://www.threads.net/@user/post/xyz1",
            author_username="user1",
            content="Bài viết kiểm tra trùng lặp",
            posted_at="2026-09-23T10:00:00"
        )
        self.db_manager.upsert_post(post)

        comment = CommentModel(
            id="cmt_1",
            post_id="post_1",
            post_url="https://www.threads.net/@user/post/xyz1",
            author_username="commenter1",
            content="Bình luận thử nghiệm trùng",
            posted_at="2026-09-23T10:05:00"
        )
        self.db_manager.upsert_comment(comment)

        # Check comment existence by ID
        self.assertTrue(self.db_manager.comment_exists(comment_id="cmt_1"))
        self.assertFalse(self.db_manager.comment_exists(comment_id="cmt_nonexistent"))

        # Check comment existence by normalized content (case & whitespace insensitive)
        self.assertTrue(self.db_manager.comment_exists(content="  BÌNH LUẬN   thử nghiệm trùng  "))
        self.assertFalse(self.db_manager.comment_exists(content="Nội dung chưa từng có"))

        # Check post existence
        self.assertTrue(self.db_manager.post_exists(post_id="post_1"))
        self.assertTrue(self.db_manager.post_exists(url="https://www.threads.net/@user/post/xyz1"))
        self.assertTrue(self.db_manager.post_exists(content="bài viết kiểm tra trùng lặp"))
        self.assertFalse(self.db_manager.post_exists(post_id="post_999"))

    def test_get_existing_hashes(self):
        """Test retrieving all existing hashes for fast in-memory dedup lookup."""
        post = PostModel(
            id="post_h1",
            url="https://www.threads.net/@u1/post/h1",
            author_username="u1",
            content="Post Hash Test"
        )
        self.db_manager.upsert_post(post)

        cmt = CommentModel(
            id="cmt_h1",
            post_id="post_h1",
            post_url="https://www.threads.net/@u1/post/h1",
            author_username="u2",
            content="Comment Hash Test"
        )
        self.db_manager.upsert_comment(cmt)

        c_ids, c_contents = self.db_manager.get_existing_comment_hashes()
        self.assertIn("cmt_h1", c_ids)
        self.assertIn("comment hash test", c_contents)

        p_ids, p_urls, p_contents = self.db_manager.get_existing_post_hashes()
        self.assertIn("post_h1", p_ids)
        self.assertIn("https://www.threads.net/@u1/post/h1", p_urls)
        self.assertIn("post hash test", p_contents)

    def test_count_and_purge_duplicate_comments(self):
        """Test counting duplicates and purging duplicate comments while keeping reviewed ones."""
        # Insert 3 comments with the exact same content
        # cmt_dup1: regular unreviewed
        cmt1 = CommentModel(
            id="cmt_dup1",
            post_id="post_test",
            post_url="https://threads.net/p/1",
            author_username="user1",
            content="Nội dung bị lặp lại nhiều lần",
            scraped_at="2026-09-23T01:00:00"
        )
        self.db_manager.upsert_comment(cmt1)

        # cmt_dup2: user reviewed as 'bad'
        cmt2 = CommentModel(
            id="cmt_dup2",
            post_id="post_test",
            post_url="https://threads.net/p/1",
            author_username="user2",
            content="Nội dung bị lặp lại nhiều lần",
            is_user_reviewed=True,
            user_review="bad",
            user_review_vi="Xấu luôn",
            toxic_score=0.9,
            scraped_at="2026-09-23T02:00:00"
        )
        self.db_manager.upsert_comment(cmt2)

        # cmt_dup3: unreviewed copy with extra spacing
        cmt3 = CommentModel(
            id="cmt_dup3",
            post_id="post_test",
            post_url="https://threads.net/p/1",
            author_username="user3",
            content="  Nội dung   bị lặp lại  nhiều lần  ",
            scraped_at="2026-09-23T03:00:00"
        )
        self.db_manager.upsert_comment(cmt3)

        # Distinct comment
        cmt4 = CommentModel(
            id="cmt_unique",
            post_id="post_test",
            post_url="https://threads.net/p/1",
            author_username="user4",
            content="Một câu hoàn toàn khác biệt",
            scraped_at="2026-09-23T04:00:00"
        )
        self.db_manager.upsert_comment(cmt4)

        # Count redundant duplicate comments: 3 copies of same content -> 2 redundant
        dup_count = self.db_manager.count_duplicate_comments()
        self.assertEqual(dup_count, 2)

        # Purge duplicates
        res = self.db_manager.purge_duplicate_comments()
        self.assertEqual(res["purged_duplicates"], 2)
        self.assertEqual(res["remaining_comments"], 2)

        # Verify that cmt_dup2 (the reviewed one) was preserved!
        with self.db_manager.get_connection() as conn:
            remaining = conn.execute("SELECT id, is_user_reviewed FROM comments ORDER BY id").fetchall()
            remaining_ids = [r["id"] for r in remaining]
            self.assertIn("cmt_dup2", remaining_ids)
            self.assertIn("cmt_unique", remaining_ids)
            self.assertNotIn("cmt_dup1", remaining_ids)
            self.assertNotIn("cmt_dup3", remaining_ids)

        # Duplicates count should now be 0
        self.assertEqual(self.db_manager.count_duplicate_comments(), 0)

    def test_purge_duplicate_posts(self):
        """Test purging duplicate posts."""
        p1 = PostModel(
            id="p_dup1",
            url="https://threads.net/@u/post/dup1",
            content="Bài viết trùng",
            author_username="u",
            scraped_at="2026-09-23T01:00:00"
        )
        p2 = PostModel(
            id="p_dup2",
            url="https://threads.net/@u/post/dup1",  # Same URL
            content="Bài viết trùng khác ID",
            author_username="u",
            scraped_at="2026-09-23T02:00:00"
        )
        p3 = PostModel(
            id="p_unique",
            url="https://threads.net/@u/post/unique",
            content="Bài viết riêng",
            author_username="u",
            scraped_at="2026-09-23T03:00:00"
        )
        self.db_manager.upsert_post(p1)
        self.db_manager.upsert_post(p2)
        self.db_manager.upsert_post(p3)

        purged = self.db_manager.purge_duplicate_posts()
        self.assertEqual(purged, 1)

    def test_export_deduplication(self):
        """Test that export functions eliminate duplicate rows when deduplicate=True."""
        # Insert a post
        post = PostModel(
            id="post_exp",
            url="https://threads.net/@u/post/exp",
            content="Bài viết export",
            author_username="u"
        )
        self.db_manager.upsert_post(post)

        # Insert 3 comments, 2 of which have identical content
        c1 = CommentModel(
            id="c_e1",
            post_id="post_exp",
            post_url="https://threads.net/p/exp",
            content="Nội dung xuất trùng lặp",
            author_username="a",
            toxic_score=0.8,
            is_toxic=True
        )
        c2 = CommentModel(
            id="c_e2",
            post_id="post_exp",
            post_url="https://threads.net/p/exp",
            content="Nội dung xuất trùng lặp",
            author_username="b",
            toxic_score=0.2,
            is_toxic=False
        )
        c3 = CommentModel(
            id="c_e3",
            post_id="post_exp",
            post_url="https://threads.net/p/exp",
            content="Bình luận độc nhất",
            author_username="c",
            toxic_score=0.1,
            is_toxic=False
        )
        self.db_manager.upsert_comment(c1)
        self.db_manager.upsert_comment(c2)
        self.db_manager.upsert_comment(c3)

        # Export with deduplicate=False -> 3 rows
        df_all = self.db_manager.get_comments_export_df(deduplicate=False)
        self.assertEqual(len(df_all), 3)

        # Export with deduplicate=True -> 2 rows (duplicate dropped)
        df_dedup = self.db_manager.get_comments_export_df(deduplicate=True)
        self.assertEqual(len(df_dedup), 2)

        # Curated export with deduplicate=True
        df_curated = self.db_manager.get_curated_export_df(deduplicate=True)
        self.assertEqual(len(df_curated), 2)

    def test_crawler_skips_duplicates(self):
        """Test crawler skipping comments already in DB when deduplicate=True."""
        # Pre-seed DB with a comment
        existing_comment = CommentModel(
            id="cmt_preseed",
            post_id="post_pre",
            post_url="https://threads.net/p/pre",
            author_username="user_pre",
            content="Bình luận đã có từ trước trong CSDL"
        )
        self.db_manager.upsert_comment(existing_comment)

        with patch("src.crawler.threads_crawler.db_manager", self.db_manager):
            crawler = ThreadsCrawler(headless=True)
            # Verify hashes are loaded
            db_ids, db_contents = self.db_manager.get_existing_comment_hashes()
            self.assertIn("cmt_preseed", db_ids)
            self.assertIn("bình luận đã có từ trước trong csdl", db_contents)


if __name__ == "__main__":
    unittest.main()
