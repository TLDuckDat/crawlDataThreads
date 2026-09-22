import unittest
import tempfile
from pathlib import Path
import openpyxl
import pandas as pd

from src.database.models import CommentModel, PostModel
from src.database.db_manager import DatabaseManager, db_manager
from src.exporter.exporter import DataExporter

class TestCuratedExport(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_curated.db"
        self.export_dir = Path(self.temp_dir.name) / "exports"
        self.db = DatabaseManager(db_path=self.db_path)
        self.exporter = DataExporter(export_dir=self.export_dir)

        # Seed post
        post = PostModel(
            id="post_curated_1",
            url="https://www.threads.net/@drama_queen/post/123",
            author_username="drama_queen",
            content="Bài viết drama cực căng tối nay các bác ơi",
            categories=["Drama showbiz"],
            is_toxic=False,
            toxic_score=0.1
        )
        self.db.upsert_post(post)

        # Seed comment 1 (bad)
        c1 = CommentModel(
            id="cmt_curated_1",
            post_id="post_curated_1",
            post_url="https://www.threads.net/@drama_queen/post/123",
            author_username="toxic_guy",
            content="Con này hãm lờ vl, ngu như chó",
            is_toxic=True,
            toxic_score=0.92,
            review_status="bad",
            review_status_vi="Xấu luôn (Rõ ràng)",
            matched_words=["hãm lờ", "ngu như chó"],
            categories=["Lăng mạ", "Chửi thề"],
            comment_type_vi="Bình luận gốc"
        )
        self.db.upsert_comment(c1)

        # Seed comment 2 (ambiguous)
        c2 = CommentModel(
            id="cmt_curated_2",
            post_id="post_curated_1",
            post_url="https://www.threads.net/@drama_queen/post/123",
            author_username="sarcastic_guy",
            content="Trông cũng ra gì đấy hề hước ghê 🤡",
            is_toxic=False,
            toxic_score=0.45,
            review_status="ambiguous",
            review_status_vi="Chưa rõ (Nghi ngờ)",
            matched_emojis=["🤡"],
            comment_type_vi="Bình luận con (Phản hồi)"
        )
        self.db.upsert_comment(c2)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_get_curated_export_df_columns(self):
        orig_db = db_manager.db_path
        db_manager.db_path = self.db_path
        try:
            df = self.db.get_curated_export_df(filter_status="all")
            self.assertFalse(df.empty)
            expected_cols = [
                "Mã ID",
                "Nội dung",
                "Điểm đánh giá",
                "Bài viết",
                "Chủ đề bài viết",
                "f0",
                "f1",
                "f2",
                "f3",
                "Tự đánh giá của bạn (Xấu luôn / Chưa rõ / Trong sạch)",
                "Từ lóng mới bổ sung (nếu có)"
            ]
            for col in expected_cols:
                self.assertIn(col, df.columns)

            row1 = df[df["Mã ID"] == "cmt_curated_1"].iloc[0]
            self.assertEqual(row1["Nội dung"], "Con này hãm lờ vl, ngu như chó")
            self.assertEqual(row1["Bài viết"], "Bài viết drama cực căng tối nay các bác ơi")
            self.assertEqual(row1["Chủ đề bài viết"], "Drama showbiz")
            self.assertIn("0.92", str(row1["Điểm đánh giá"]))
            self.assertIn("Xấu luôn", str(row1["Điểm đánh giá"]))
        finally:
            db_manager.db_path = orig_db

    def test_export_curated_excel_dimensions_and_wrap(self):
        orig_db = db_manager.db_path
        db_manager.db_path = self.db_path
        try:
            excel_path = self.exporter.export_curated_excel(filter_status="all")
            self.assertTrue(excel_path.exists())
            self.assertIn("danh_gia_4_cot", excel_path.name)

            # Load workbook and verify column dimensions and wrap text
            wb = openpyxl.load_workbook(excel_path)
            ws = wb.active
            self.assertEqual(ws.title, "Dữ liệu đánh giá")

            # Verify header values
            headers = [cell.value for cell in ws[1]]
            self.assertIn("Nội dung", headers)
            self.assertIn("Điểm đánh giá", headers)
            self.assertIn("Bài viết", headers)
            self.assertIn("Chủ đề bài viết", headers)

            # Verify column widths are fixed (not default None)
            self.assertIsNotNone(ws.column_dimensions["A"].width)
            self.assertIsNotNone(ws.column_dimensions["B"].width) # Nội dung
            self.assertIsNotNone(ws.column_dimensions["C"].width) # Điểm đánh giá
            self.assertIsNotNone(ws.column_dimensions["D"].width) # Bài viết
            self.assertGreaterEqual(ws.column_dimensions["B"].width, 40)
            self.assertGreaterEqual(ws.column_dimensions["D"].width, 40)

            # Verify wrap text is enabled on content cells
            row2_cells = ws[2]
            for cell in row2_cells:
                self.assertTrue(cell.alignment.wrap_text)

            wb.close()
        finally:
            db_manager.db_path = orig_db

    def test_export_curated_excel_with_hidden_columns(self):
        """Verify that when columns are hidden by user, Excel file strictly omits them and sizes remaining columns properly."""
        orig_db = db_manager.db_path
        db_manager.db_path = self.db_path
        try:
            # User chooses to keep only 2 columns: "Nội dung" and "Điểm đánh giá" (hides Mã ID, Bài viết, Chủ đề...)
            chosen_cols = ["Nội dung", "Điểm đánh giá"]
            excel_path = self.exporter.export_curated_excel(filter_status="all", columns=chosen_cols)
            self.assertTrue(excel_path.exists())

            wb = openpyxl.load_workbook(excel_path)
            ws = wb.active

            # Headers must contain ONLY the chosen columns
            headers = [cell.value for cell in ws[1] if cell.value is not None]
            self.assertEqual(headers, ["Nội dung", "Điểm đánh giá"])
            self.assertNotIn("Mã ID", headers)
            self.assertNotIn("Bài viết", headers)
            self.assertNotIn("Chủ đề bài viết", headers)
            self.assertEqual(len(headers), 2)

            # Column A is now "Nội dung", so its width should be 48 (not 16 for Mã ID)
            self.assertEqual(ws.column_dimensions["A"].width, 48)
            # Column B is "Điểm đánh giá", width 22
            self.assertEqual(ws.column_dimensions["B"].width, 22)

            # Wrap text must be True
            for cell in ws[2]:
                self.assertTrue(cell.alignment.wrap_text)

            wb.close()
        finally:
            db_manager.db_path = orig_db

    def test_export_curated_csv_with_hidden_columns(self):
        """Verify that CSV export strictly omits hidden columns."""
        orig_db = db_manager.db_path
        db_manager.db_path = self.db_path
        try:
            chosen_cols = ["Nội dung", "Bài viết"]
            csv_path = self.exporter.export_curated_csv(filter_status="all", columns=chosen_cols)
            self.assertTrue(csv_path.exists())

            df_read = pd.read_csv(csv_path, encoding="utf-8-sig")
            self.assertEqual(list(df_read.columns), ["Nội dung", "Bài viết"])
            self.assertNotIn("Mã ID", df_read.columns)
            self.assertNotIn("Điểm đánh giá", df_read.columns)
        finally:
            db_manager.db_path = orig_db

    def test_column_order_bai_viet_f0_f3_noi_dung(self):
        """Verify that column sequence follows: Mã ID -> Bài viết -> f0 -> f1 -> f2 -> f3 -> Nội dung."""
        orig_db = db_manager.db_path
        db_manager.db_path = self.db_path
        try:
            df = self.db.get_curated_export_df(filter_status="all")
            cols = list(df.columns)
            self.assertEqual(cols[0], "Mã ID")
            self.assertEqual(cols[1], "Bài viết")
            self.assertEqual(cols[2], "f0")
            self.assertEqual(cols[3], "f1")
            self.assertEqual(cols[4], "f2")
            self.assertEqual(cols[5], "f3")
            self.assertEqual(cols[6], "Nội dung")
            self.assertEqual(cols[7], "Điểm đánh giá")
            self.assertEqual(cols[8], "Chủ đề bài viết")
        finally:
            db_manager.db_path = orig_db

    def test_whitespace_splitting_in_curated_export(self):
        """Verify that multiple spaces, tabs, and newlines are cleanly collapsed into single spaces."""
        orig_db = db_manager.db_path
        db_manager.db_path = self.db_path
        try:
            from src.database.models import CommentModel
            messy_cmt = CommentModel(
                id="cmt_messy_space",
                post_id="post_curated_1",
                post_url="https://www.threads.com/@drama/post/1",
                comment_url="https://www.threads.com/@drama/post/1#cmt_messy",
                author_username="space_user",
                author_name="Space User",
                author_profile_url="https://www.threads.com/@space_user",
                content="  Câu này\n\n\n   có rất nhiều   khoảng trắng   và dòng thừa\t\t ",
                posted_at="2026-09-22 12:00:00",
                likes=1,
                reply_to="",
                is_reply=False,
                f0="  f0 gốc\n\n   nhiều cách   ",
                f1="",
                f2="",
                f3="",
                is_toxic=False,
                toxic_score=0.05,
                severity_vi="Trong sạch",
                review_status="clean",
                review_status_vi="Trong sạch"
            )
            self.db.upsert_comment(messy_cmt)

            df = self.db.get_curated_export_df(filter_status="all")
            row = df[df["Mã ID"] == "cmt_messy_space"].iloc[0]
            self.assertEqual(row["Nội dung"], "Câu này có rất nhiều khoảng trắng và dòng thừa")
            self.assertEqual(row["f0"], "f0 gốc nhiều cách")

            # Verify in Excel file as well
            excel_path = self.exporter.export_curated_excel(filter_status="all")
            wb = openpyxl.load_workbook(excel_path)
            ws = wb.active
            found_cell = False
            for r in ws.iter_rows(min_row=2, values_only=True):
                if r[0] == "cmt_messy_space":
                    # Col 1: Bài viết, Col 2: f0, Col 6: Nội dung
                    self.assertEqual(r[2], "f0 gốc nhiều cách")
                    self.assertEqual(r[6], "Câu này có rất nhiều khoảng trắng và dòng thừa")
                    found_cell = True
                    break
            self.assertTrue(found_cell)
            wb.close()
        finally:
            db_manager.db_path = orig_db

    def test_comment_length_threshold_filter(self):
        """Verify that comments < 2 chars (e.g. 'ừ', 'ờ', '.') and > 300 chars are filtered out."""
        orig_db = db_manager.db_path
        db_manager.db_path = self.db_path
        try:
            from src.database.models import CommentModel
            # 1. Too short (1 char: 'ừ')
            c_short = CommentModel(
                id="cmt_too_short",
                post_id="post_curated_1",
                post_url="https://www.threads.com/@drama/post/1",
                comment_url="https://www.threads.com/@drama/post/1#short",
                author_username="short_u",
                author_name="Short",
                author_profile_url="",
                content="ừ",
                posted_at="2026-09-22 12:00:00",
                likes=0,
                reply_to="",
                is_reply=False
            )
            # 2. Too short with spaces
            c_short_space = CommentModel(
                id="cmt_short_space",
                post_id="post_curated_1",
                post_url="https://www.threads.com/@drama/post/1",
                comment_url="https://www.threads.com/@drama/post/1#space",
                author_username="short_u2",
                author_name="Short 2",
                author_profile_url="",
                content="  ờ   ",
                posted_at="2026-09-22 12:00:00",
                likes=0,
                reply_to="",
                is_reply=False
            )
            # 3. Exactly 2 chars: "ok" (should be kept)
            c_exact_2 = CommentModel(
                id="cmt_exact_2",
                post_id="post_curated_1",
                post_url="https://www.threads.com/@drama/post/1",
                comment_url="https://www.threads.com/@drama/post/1#ok",
                author_username="ok_u",
                author_name="OK",
                author_profile_url="",
                content="ok",
                posted_at="2026-09-22 12:00:00",
                likes=0,
                reply_to="",
                is_reply=False
            )
            # 4. Too long (> 300 chars)
            c_too_long = CommentModel(
                id="cmt_too_long",
                post_id="post_curated_1",
                post_url="https://www.threads.com/@drama/post/1",
                comment_url="https://www.threads.com/@drama/post/1#long",
                author_username="long_u",
                author_name="Long",
                author_profile_url="",
                content="A" * 305,
                posted_at="2026-09-22 12:00:00",
                likes=0,
                reply_to="",
                is_reply=False
            )
            self.db.upsert_comment(c_short)
            self.db.upsert_comment(c_short_space)
            self.db.upsert_comment(c_exact_2)
            self.db.upsert_comment(c_too_long)

            # Query with default 2 to 300 filter
            df = self.db.get_curated_export_df(filter_status="all", min_length=2, max_length=300)
            ids = list(df["Mã ID"])
            self.assertNotIn("cmt_too_short", ids)
            self.assertNotIn("cmt_short_space", ids)
            self.assertNotIn("cmt_too_long", ids)
            self.assertIn("cmt_exact_2", ids)

            # Also check get_comments_export_df
            df_comm = self.db.get_comments_export_df(filter_status="all", include_links=True, min_length=2, max_length=300)
            comm_ids = list(df_comm["Mã bình luận (Comment ID)"])
            self.assertNotIn("cmt_too_short", comm_ids)
            self.assertNotIn("cmt_short_space", comm_ids)
            self.assertNotIn("cmt_too_long", comm_ids)
            self.assertIn("cmt_exact_2", comm_ids)
        finally:
            db_manager.db_path = orig_db

if __name__ == "__main__":
    unittest.main()
