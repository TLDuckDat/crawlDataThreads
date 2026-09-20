"""
Unit tests for Vietnamese/English language filter functions.
Tests:
    - contains_foreign_script()
    - is_valid_viet_eng_content()
    - clean_to_viet_eng()
    - db_manager.get_curated_export_df() viet_eng_only filtering
    - db_manager.purge_foreign_language_records()
"""
import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.detector.text_normalizer import (
    contains_foreign_script,
    is_valid_viet_eng_content,
    clean_to_viet_eng,
)


class TestContainsForeignScript(unittest.TestCase):
    """Tests for contains_foreign_script()"""

    def test_pure_vietnamese_no_foreign(self):
        self.assertFalse(contains_foreign_script("Thằng này nói chuyện kiểu gì vậy?"))

    def test_pure_english_no_foreign(self):
        self.assertFalse(contains_foreign_script("Hello, this is an English sentence."))

    def test_chinese_detected(self):
        self.assertTrue(contains_foreign_script("你好世界"))

    def test_japanese_hiragana_detected(self):
        self.assertTrue(contains_foreign_script("こんにちは"))

    def test_japanese_katakana_detected(self):
        self.assertTrue(contains_foreign_script("コンニチハ"))

    def test_korean_detected(self):
        self.assertTrue(contains_foreign_script("안녕하세요"))

    def test_arabic_detected(self):
        self.assertTrue(contains_foreign_script("مرحبا بالعالم"))

    def test_cyrillic_detected(self):
        self.assertTrue(contains_foreign_script("Привет мир"))

    def test_thai_detected(self):
        self.assertTrue(contains_foreign_script("สวัสดีชาวโลก"))

    def test_mixed_viet_chinese_detected(self):
        # Mixed content: has foreign characters
        self.assertTrue(contains_foreign_script("Thỏ Da LAB 周周"))

    def test_emoji_only_no_foreign(self):
        self.assertFalse(contains_foreign_script("🔥🤡💯"))

    def test_numbers_only_no_foreign(self):
        self.assertFalse(contains_foreign_script("12345 6789"))

    def test_empty_string_no_foreign(self):
        self.assertFalse(contains_foreign_script(""))

    def test_none_like_empty_no_foreign(self):
        self.assertFalse(contains_foreign_script(""))


class TestIsValidVietEngContent(unittest.TestCase):
    """Tests for is_valid_viet_eng_content()"""

    def test_valid_vietnamese(self):
        self.assertTrue(is_valid_viet_eng_content("Mày nói chuyện kiểu gì vậy hả đồ ngu?"))

    def test_valid_english(self):
        self.assertTrue(is_valid_viet_eng_content("This comment is completely in English!"))

    def test_valid_viet_with_emojis(self):
        self.assertTrue(is_valid_viet_eng_content("Ơi trời ơi cái này xấu thật 🤮🤦‍♀️"))

    def test_valid_mixed_viet_english(self):
        self.assertTrue(is_valid_viet_eng_content("Bạn ơi ok nhé! Let's do this!"))

    def test_invalid_pure_chinese(self):
        self.assertFalse(is_valid_viet_eng_content("你好世界，这是中文"))

    def test_invalid_pure_japanese(self):
        self.assertFalse(is_valid_viet_eng_content("おはようございます"))

    def test_invalid_pure_korean(self):
        self.assertFalse(is_valid_viet_eng_content("안녕하세요 저는 한국어를 합니다"))

    def test_invalid_pure_arabic(self):
        self.assertFalse(is_valid_viet_eng_content("مرحبا كيف حالك؟"))

    def test_valid_mostly_viet_tiny_foreign(self):
        # 2 foreign chars in mostly Vietnamese text → should be valid (cleaned)
        text = "Thỏ Da LAB ATVNCG2026 trên sân khấu Duy Khánh 周周"
        self.assertTrue(is_valid_viet_eng_content(text))

    def test_invalid_mostly_foreign_some_latin(self):
        # Barely any Latin, mostly CJK → should be invalid
        text = "你好世界这是中文 hi"  # 1 Latin word vs many CJK chars → ratio > 15%
        self.assertFalse(is_valid_viet_eng_content(text))

    def test_invalid_empty_string(self):
        self.assertFalse(is_valid_viet_eng_content(""))

    def test_invalid_whitespace_only(self):
        self.assertFalse(is_valid_viet_eng_content("   "))

    def test_valid_numbers_and_punctuation(self):
        # Numbers and punctuation alone should be "valid" (no foreign chars)
        self.assertTrue(is_valid_viet_eng_content("100% ok! #1 rank."))

    def test_custom_max_foreign_ratio(self):
        # With a strict 0% ratio, mixed text should fail
        text = "Thỏ Da LAB 周周"
        self.assertFalse(is_valid_viet_eng_content(text, max_foreign_ratio=0.0))


class TestCleanToVietEng(unittest.TestCase):
    """Tests for clean_to_viet_eng()"""

    def test_pure_vietnamese_unchanged(self):
        text = "Mày nói chuyện kiểu gì vậy hả?"
        self.assertEqual(clean_to_viet_eng(text), text)

    def test_removes_trailing_chinese(self):
        text = "Thỏ Da LAB ATVNCG2026 trên sân khấu Duy Khánh 周周"
        result = clean_to_viet_eng(text)
        self.assertNotIn("周", result)
        self.assertIn("Thỏ Da LAB", result)
        self.assertIn("Duy Khánh", result)

    def test_removes_japanese(self):
        text = "Hello こんにちは world"
        result = clean_to_viet_eng(text)
        self.assertNotIn("こんにちは", result)
        self.assertIn("Hello", result)
        self.assertIn("world", result)

    def test_removes_korean(self):
        text = "안녕하세요 Xin chào"
        result = clean_to_viet_eng(text)
        self.assertNotIn("안녕", result)
        self.assertIn("Xin chào", result)

    def test_preserves_emojis(self):
        text = "Trời ơi 🔥🤡 cái này quá đáng!"
        result = clean_to_viet_eng(text)
        self.assertIn("🔥", result)
        self.assertIn("🤡", result)

    def test_preserves_numbers(self):
        text = "Đây là lần 3, điểm 100%"
        result = clean_to_viet_eng(text)
        self.assertIn("3", result)
        self.assertIn("100%", result)

    def test_preserves_punctuation(self):
        text = "Ok, nhé! (đúng rồi)"
        result = clean_to_viet_eng(text)
        self.assertIn(",", result)
        self.assertIn("!", result)
        self.assertIn("(", result)

    def test_collapses_extra_spaces(self):
        text = "hello  world"
        result = clean_to_viet_eng(text)
        # Should not have double spaces after removing foreign chars
        self.assertNotIn("  ", result)

    def test_empty_string(self):
        self.assertEqual(clean_to_viet_eng(""), "")

    def test_pure_foreign_becomes_empty(self):
        result = clean_to_viet_eng("你好世界")
        # All CJK stripped → empty or whitespace
        self.assertEqual(result.strip(), "")

    def test_vietnamese_diacritics_preserved(self):
        text = "Ông ấy nói: tiếng Việt đẹp lắm!"
        result = clean_to_viet_eng(text)
        self.assertIn("tiếng Việt", result)
        self.assertIn("đẹp", result)

    def test_d_with_stroke_preserved(self):
        text = "Đây là chữ Đ viết hoa"
        result = clean_to_viet_eng(text)
        self.assertIn("Đây", result)
        self.assertIn("Đ", result)


class TestPurgeForeignLanguageRecords(unittest.TestCase):
    """Tests for db_manager.purge_foreign_language_records() using an in-memory SQLite DB."""

    def setUp(self):
        """Create a fresh in-memory DatabaseManager for each test."""
        import sqlite3
        import tempfile
        from pathlib import Path
        # Use a temporary file so we don't touch real data
        self._tmpfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmpfile.close()
        self.tmp_db_path = Path(self._tmpfile.name)

        from src.database.db_manager import DatabaseManager
        self.db = DatabaseManager(db_path=self.tmp_db_path)
        self._seed_data()

    def tearDown(self):
        import os
        try:
            os.unlink(self.tmp_db_path)
        except Exception:
            pass

    def _seed_data(self):
        """Insert a mix of Vietnamese, English, and foreign records."""
        from src.database.models import PostModel, CommentModel
        from datetime import datetime

        # Vietnamese post (should survive)
        p_viet = PostModel(
            id="post_viet_1",
            url="https://threads.net/post/1",
            author_username="user_viet",
            content="Mày nói chuyện kiểu gì vậy hả đồ ngu?",
            posted_at=datetime.now().isoformat()
        )
        self.db.upsert_post(p_viet)

        # Pure Chinese post (should be purged)
        p_cn = PostModel(
            id="post_cn_1",
            url="https://threads.net/post/2",
            author_username="user_cn",
            content="你好世界，这是纯中文内容",
            posted_at=datetime.now().isoformat()
        )
        self.db.upsert_post(p_cn)

        # Vietnamese comment (should survive)
        c_viet = CommentModel(
            id="cmt_viet_1",
            post_id="post_viet_1",
            post_url="https://threads.net/post/1",
            author_username="commenter_viet",
            content="Ủa sao lại thế này? Thật sự không hiểu!",
        )
        self.db.upsert_comment(c_viet)

        # Pure Korean comment (should be purged)
        c_kr = CommentModel(
            id="cmt_kr_1",
            post_id="post_viet_1",
            post_url="https://threads.net/post/1",
            author_username="commenter_kr",
            content="안녕하세요 저는 한국어를 합니다",
        )
        self.db.upsert_comment(c_kr)

        # Mixed Vietnamese + tiny Chinese (should be cleaned, NOT deleted)
        c_mixed = CommentModel(
            id="cmt_mixed_1",
            post_id="post_viet_1",
            post_url="https://threads.net/post/1",
            author_username="commenter_mixed",
            content="Thỏ Da LAB ATVNCG2026 trên sân khấu Duy Khánh 周周",
        )
        self.db.upsert_comment(c_mixed)

    def test_purge_removes_foreign_comments(self):
        result = self.db.purge_foreign_language_records()
        self.assertGreaterEqual(result["purged_comments"], 1, "Should delete at least 1 pure-foreign comment (Korean)")

    def test_purge_removes_foreign_posts(self):
        result = self.db.purge_foreign_language_records()
        self.assertGreaterEqual(result["purged_posts"], 1, "Should delete at least 1 pure-foreign post (Chinese)")

    def test_purge_cleans_mixed_comments(self):
        result = self.db.purge_foreign_language_records()
        self.assertGreaterEqual(result["cleaned_comments"], 1, "Should clean at least 1 mixed-language comment")

    def test_purge_keeps_vietnamese_comments(self):
        self.db.purge_foreign_language_records()
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT content FROM comments WHERE id = 'cmt_viet_1'"
            ).fetchone()
        self.assertIsNotNone(row, "Vietnamese comment should still exist after purge")
        self.assertIn("Ủa sao lại thế này", row[0])

    def test_purge_cleaned_comment_has_no_foreign_chars(self):
        self.db.purge_foreign_language_records()
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT content FROM comments WHERE id = 'cmt_mixed_1'"
            ).fetchone()
        if row:  # comment still exists (was cleaned, not deleted)
            self.assertNotIn("周", row[0], "Stray Chinese characters should be removed")
            self.assertIn("Duy Khánh", row[0], "Vietnamese text should be preserved")

    def test_purge_idempotent(self):
        """Running purge twice should give 0 on the second run."""
        self.db.purge_foreign_language_records()
        result2 = self.db.purge_foreign_language_records()
        self.assertEqual(result2["purged_comments"], 0)
        self.assertEqual(result2["purged_posts"], 0)


class TestVietEngExportFilter(unittest.TestCase):
    """Tests that get_curated_export_df correctly filters foreign records."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        self._tmpfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmpfile.close()
        self.tmp_db_path = Path(self._tmpfile.name)

        from src.database.db_manager import DatabaseManager
        self.db = DatabaseManager(db_path=self.tmp_db_path)
        self._seed_data()

    def tearDown(self):
        import os
        try:
            os.unlink(self.tmp_db_path)
        except Exception:
            pass

    def _seed_data(self):
        from src.database.models import PostModel, CommentModel
        from datetime import datetime
        p = PostModel(
            id="post_1",
            url="https://threads.net/post/1",
            author_username="user",
            content="Mày nói chuyện kiểu gì vậy?",
            posted_at=datetime.now().isoformat()
        )
        self.db.upsert_post(p)

        c_viet = CommentModel(
            id="c_viet_1",
            post_id="post_1",
            post_url="https://threads.net/post/1",
            author_username="a",
            content="Đây là bình luận tiếng Việt bình thường.",
        )
        self.db.upsert_comment(c_viet)

        c_kr = CommentModel(
            id="c_kr_1",
            post_id="post_1",
            post_url="https://threads.net/post/1",
            author_username="b",
            content="안녕하세요 저는 한국어를 합니다",
        )
        self.db.upsert_comment(c_kr)

    def test_viet_eng_only_filters_foreign(self):
        df = self.db.get_curated_export_df(filter_status="all", viet_eng_only=True)
        ids = df["Mã ID"].tolist()
        self.assertIn("c_viet_1", ids, "Vietnamese comment should appear")
        self.assertNotIn("c_kr_1", ids, "Korean comment should be filtered out")

    def test_viet_eng_only_false_keeps_all(self):
        df = self.db.get_curated_export_df(filter_status="all", viet_eng_only=False)
        ids = df["Mã ID"].tolist()
        self.assertIn("c_viet_1", ids)
        self.assertIn("c_kr_1", ids, "With viet_eng_only=False, Korean comment should appear")


if __name__ == "__main__":
    unittest.main(verbosity=2)
