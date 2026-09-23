"""
Unit tests for cleaning Threads UI artifacts:
- 'Translate 1 / 2', 'Translate 1 / 3', 'Xem bản dịch 1 / 2'
- Trailing carousel numbers '1 / 2', '2 / 2'
- Trailing UI buttons 'Translate', 'Xem bản dịch', 'Dịch'
- Database level cleaning via db_manager.clean_ui_artifacts_in_db()
"""
import unittest
import tempfile
import shutil
from pathlib import Path

from src.detector.text_normalizer import clean_ui_artifacts, clean_to_viet_eng
from src.database.db_manager import DatabaseManager
from src.database.models import PostModel, CommentModel


class TestUIArtifactsCleaner(unittest.TestCase):
    """Test string-level cleaning of Threads UI noise."""

    def test_clean_translate_with_carousel_numbers(self):
        text = "top 1 cách thể hiện dân trí Việt Nam thấp 🙂 Translate 1 / 2"
        expected = "top 1 cách thể hiện dân trí Việt Nam thấp 🙂"
        self.assertEqual(clean_ui_artifacts(text), expected)

    def test_clean_translate_higher_carousel(self):
        text = "Bài viết về KOL drama kích war Translate 1 / 3"
        expected = "Bài viết về KOL drama kích war"
        self.assertEqual(clean_ui_artifacts(text), expected)

    def test_clean_translate_comment_carousel(self):
        text = "Sao Đom đóm bảo Jack vị vô sinh :(((( Translate 2 / 2"
        expected = "Sao Đom đóm bảo Jack vị vô sinh :(((("
        self.assertEqual(clean_ui_artifacts(text), expected)

    def test_clean_standalone_translate_at_end(self):
        text = "Nội dung bài viết kết thúc bằng Translate"
        expected = "Nội dung bài viết kết thúc bằng"
        self.assertEqual(clean_ui_artifacts(text), expected)

    def test_clean_vietnamese_ui_xem_ban_dich(self):
        text = "Status tiếng Anh nhưng Threads hiện nút Xem bản dịch 1 / 2"
        expected = "Status tiếng Anh nhưng Threads hiện nút"
        self.assertEqual(clean_ui_artifacts(text), expected)

    def test_clean_trailing_carousel_only(self):
        text = "Bài viết đăng kèm 2 ảnh 1 / 2"
        expected = "Bài viết đăng kèm 2 ảnh"
        self.assertEqual(clean_ui_artifacts(text), expected)

    def test_preserve_normal_dates_and_fractions(self):
        # Dates like 2/9 or 30/4 should remain untouched
        self.assertEqual(clean_ui_artifacts("Ngày 2/9 là ngày lễ"), "Ngày 2/9 là ngày lễ")
        # Fractions like 1/2 without spaces around slash
        self.assertEqual(clean_ui_artifacts("Tỷ lệ 1/2 thành công"), "Tỷ lệ 1/2 thành công")
        # Legitimate use of word 'dịch' in Vietnamese
        self.assertEqual(clean_ui_artifacts("dịch bài này giùm tao"), "dịch bài này giùm tao")
        self.assertEqual(clean_ui_artifacts("bản dịch này rất tệ"), "bản dịch này rất tệ")

    def test_clean_to_viet_eng_integrates_ui_cleaner(self):
        text = "Bài viết có emoji 🙂 và rác Translate 1 / 2"
        cleaned = clean_to_viet_eng(text)
        self.assertNotIn("Translate", cleaned)
        self.assertNotIn("1 / 2", cleaned)
        self.assertEqual(cleaned, "Bài viết có emoji 🙂 và rác")


class TestDBManagerCleanUIArtifacts(unittest.TestCase):
    """Test database-level cleanup of UI noise."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = Path(self.test_dir) / "test_threads.db"
        self.db = DatabaseManager(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_clean_ui_artifacts_in_db(self):
        # Insert post with Translate 1 / 2
        post = PostModel(
            id="post_test_ui",
            url="https://threads.net/@user/post/123",
            author_username="user",
            content="Post with image carousel Translate 1 / 2"
        )
        self.db.upsert_post(post)

        # Insert comment with Translate 2 / 2 and dirty f0
        comment = CommentModel(
            id="cmt_test_ui",
            post_id="post_test_ui",
            post_url=post.url,
            author_username="commenter",
            content="Comment reply with Translate 2 / 2",
            f0="Original comment root Translate 1 / 3"
        )
        self.db.upsert_comment(comment)

        # Run database cleanup
        res = self.db.clean_ui_artifacts_in_db()
        self.assertEqual(res["cleaned_posts"], 1)
        self.assertEqual(res["cleaned_comments"], 1)

        # Verify posts cleaned
        with self.db.get_connection() as conn:
            p_row = conn.execute("SELECT content FROM posts WHERE id = 'post_test_ui'").fetchone()
            self.assertEqual(p_row["content"], "Post with image carousel")

            c_row = conn.execute("SELECT content, f0 FROM comments WHERE id = 'cmt_test_ui'").fetchone()
            self.assertEqual(c_row["content"], "Comment reply with")
            self.assertEqual(c_row["f0"], "Original comment root")


if __name__ == "__main__":
    unittest.main()
