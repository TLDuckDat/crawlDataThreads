import unittest
import tempfile
from pathlib import Path
import json

from src.database.db_manager import DatabaseManager
from src.database.models import CommentModel, PostModel
from src.detector.toxic_engine import ToxicDetectionEngine

class TestFocusReview(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_focus.db"
        self.db = DatabaseManager(db_path=self.db_path)

        # Create test post
        post = PostModel(
            id="post_test_1",
            url="https://www.threads.net/@user/post/1",
            author_username="user_test",
            content="Chủ đề về showbiz và âm nhạc",
            categories=["drama"]
        )
        self.db.upsert_post(post)

        # Create test comments
        c1 = CommentModel(
            id="cmt_1",
            post_id="post_test_1",
            post_url="https://www.threads.net/@user/post/1",
            author_username="commenter_1",
            content="Thằng này ngu như bò cút đi 🖕",
            is_toxic=True,
            toxic_score=0.85,
            severity_vi="Nghiêm trọng",
            review_status="bad",
            review_status_vi="Xấu luôn (Rõ ràng)",
            matched_words=["ngu như bò", "cút"],
            matched_emojis=["🖕"],
            categories=["profanity"]
        )
        c2 = CommentModel(
            id="cmt_2",
            post_id="post_test_1",
            post_url="https://www.threads.net/@user/post/1",
            author_username="commenter_2",
            content="Bài hát nghe cũng được đấy chứ",
            is_toxic=False,
            toxic_score=0.0,
            severity_vi="Trong sạch",
            review_status="clean",
            review_status_vi="Trong sạch"
        )
        c3 = CommentModel(
            id="cmt_3",
            post_id="post_test_1",
            post_url="https://www.threads.net/@user/post/1",
            author_username="commenter_3",
            content="Cũng bình thường thôi có gì mà ảo tưởng",
            is_toxic=False,
            toxic_score=0.25,
            severity_vi="Trung bình",
            review_status="ambiguous",
            review_status_vi="Chưa rõ (Nghi ngờ)"
        )
        self.db.upsert_comment(c1)
        self.db.upsert_comment(c2)
        self.db.upsert_comment(c3)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_review_progress_initial(self):
        prog = self.db.get_review_progress()
        self.assertEqual(prog["total"], 3)
        self.assertEqual(prog["reviewed"], 0)
        self.assertEqual(prog["unreviewed"], 3)
        self.assertEqual(prog["percent"], 0.0)

    def test_count_focus_review_comments(self):
        count_all = self.db.count_focus_review_comments(filter_review="all")
        self.assertEqual(count_all, 3)

        count_unreviewed = self.db.count_focus_review_comments(filter_review="unreviewed")
        self.assertEqual(count_unreviewed, 3)

        count_bad = self.db.count_focus_review_comments(filter_review="bad")
        self.assertEqual(count_bad, 1)

        count_ambiguous = self.db.count_focus_review_comments(filter_review="ambiguous")
        self.assertEqual(count_ambiguous, 1)

        count_clean = self.db.count_focus_review_comments(filter_review="clean")
        self.assertEqual(count_clean, 1)

    def test_get_comment_at_index_and_update(self):
        item = self.db.get_focus_review_comment_at_index(0, filter_review="bad")
        self.assertIsNotNone(item)
        self.assertEqual(item["id"], "cmt_1")
        self.assertIn("ngu như bò", item["matched_words_list"])
        self.assertIn("🖕", item["matched_emojis_list"])
        self.assertEqual(item["post_content"], "Chủ đề về showbiz và âm nhạc")

        # Update user review
        self.db.update_user_review(
            comment_id="cmt_1",
            user_review="bad",
            user_keywords=["ngu như bò", "cút"]
        )

        prog = self.db.get_review_progress()
        self.assertEqual(prog["reviewed"], 1)
        self.assertEqual(prog["unreviewed"], 2)
        self.assertEqual(prog["user_bad"], 1)

        # Now unreviewed should have 2 comments
        count_unreviewed = self.db.count_focus_review_comments(filter_review="unreviewed")
        self.assertEqual(count_unreviewed, 2)

    def test_highlight_and_candidate_tokens(self):
        from src.detector.text_normalizer import highlight_comment_text, extract_candidate_words
        text = "Thằng này ngu như bò cút đi 🖕"
        tokens = extract_candidate_words(text, matched_words=["ngu như bò"], matched_emojis=["🖕"])
        self.assertIn("ngu như bò", tokens)
        self.assertIn("🖕", tokens)
        self.assertIn("Thằng", tokens)

        html_out = highlight_comment_text(text, highlight_words=["ngu như bò", "🖕"])
        self.assertIn("<mark", html_out)
        self.assertIn("ngu như bò", html_out)

if __name__ == "__main__":
    unittest.main()

