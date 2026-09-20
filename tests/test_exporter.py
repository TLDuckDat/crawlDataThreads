import unittest
import tempfile
from pathlib import Path
from src.database.models import CommentModel
from src.database.db_manager import DatabaseManager
from src.exporter.exporter import DataExporter

class TestDataExporter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_export.db"
        self.export_dir = Path(self.temp_dir.name) / "exports"
        self.db = DatabaseManager(db_path=self.db_path)
        self.exporter = DataExporter(export_dir=self.export_dir)

        # Seed data
        c = CommentModel(
            id="cmt_exp_1",
            post_id="p_1",
            post_url="https://threads.net/post/1",
            author_username="bad_user",
            content="Mày ngu như bò vcl",
            is_toxic=True,
            toxic_score=0.8,
            matched_words=["ngu", "vcl"],
            categories=["Lăng mạ", "Chửi thề"]
        )
        self.db.upsert_comment(c)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_export_csv_and_json(self):
        # Override db_manager in exporter for test
        from src.database import db_manager
        orig_db = db_manager.db_path
        db_manager.db_path = self.db_path
        try:
            csv_path = self.exporter.export_to_csv(table_type="comments", toxic_only=False)
            self.assertTrue(csv_path.exists())
            self.assertGreater(csv_path.stat().st_size, 0)

            json_path = self.exporter.export_to_json(table_type="comments", toxic_only=False)
            self.assertTrue(json_path.exists())
            self.assertGreater(json_path.stat().st_size, 0)

            excel_path = self.exporter.export_to_excel(table_type="comments", toxic_only=False)
            self.assertTrue(excel_path.exists())
            self.assertGreater(excel_path.stat().st_size, 0)
        finally:
            db_manager.db_path = orig_db

    def test_export_comments_csv_with_replies(self):
        from src.database import db_manager
        orig_db = db_manager.db_path
        db_manager.db_path = self.db_path
        try:
            # Seed child comment
            c_child = CommentModel(
                id="cmt_exp_child_1",
                post_id="p_1",
                post_url="https://threads.net/post/1",
                author_username="reply_user",
                content="Bình luận phản hồi này",
                is_reply=True,
                parent_comment_id="cmt_exp_1",
                reply_to="@bad_user",
                comment_type_vi="Bình luận con (Phản hồi)"
            )
            self.db.upsert_comment(c_child)

            # Export replies only
            csv_path = self.exporter.export_comments_csv(filter_comment_type="reply", include_links=True)
            self.assertTrue(csv_path.exists())
            self.assertIn("con_phan_hoi", csv_path.name)

            content = csv_path.read_text(encoding="utf-8-sig")
            self.assertIn("Loại bình luận (Gốc / Bình luận con)", content)
            self.assertIn("Phản hồi cho (@Reply To)", content)
            self.assertIn("Bình luận con (Phản hồi)", content)
            self.assertIn("@bad_user", content)
            self.assertIn("cmt_exp_1", content) # parent comment ID
        finally:
            db_manager.db_path = orig_db

if __name__ == "__main__":
    unittest.main()
