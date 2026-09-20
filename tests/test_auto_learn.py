import unittest
import tempfile
import json
from pathlib import Path

from src.database.models import CommentModel
from src.database.db_manager import DatabaseManager
from src.detector.toxic_engine import ToxicEngine

class TestAutoLearn(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dict_file = Path(self.temp_dir.name) / "test_toxic_keywords.json"
        self.dataset_file = Path(self.temp_dir.name) / "test_training_dataset.json"

        # Create base test dictionary matching real config structure
        base_dict = {
            "categories": {
                "insult": {
                    "name_vi": "Lăng mạ",
                    "severity_multiplier": 1.2,
                    "words": ["ngu", "chó"]
                }
            },
            "emojis": {
                "clown": {
                    "emoji": "🤡",
                    "severity_multiplier": 0.5
                }
            },
            "whitelist": []
        }
        with open(self.dict_file, "w", encoding="utf-8") as f:
            json.dump(base_dict, f, ensure_ascii=False, indent=2)

        self.engine = ToxicEngine(dict_path=self.dict_file, dataset_path=self.dataset_file)
        self.db_path = Path(self.temp_dir.name) / "test_learn.db"
        self.db = DatabaseManager(db_path=self.db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_learn_from_user_evaluation_adds_to_dict_and_dataset(self):
        new_slang = ["trẩu tre", "bóc mẽ"]
        res = self.engine.learn_from_user_evaluation(
            text="Thằng này trẩu tre thật sự, bóc mẽ nó ra đi",
            user_review="bad",
            new_keywords=new_slang,
            category="insult",
            post_context="Bài viết về thanh niên lừa đảo",
            topic="Bóc phốt"
        )

        self.assertEqual(res["status"], "success")
        self.assertIn("trẩu tre", res["added_keywords"])
        self.assertIn("bóc mẽ", res["added_keywords"])

        # Check dictionary was updated on disk
        with open(self.dict_file, "r", encoding="utf-8") as f:
            updated_dict = json.load(f)
        insult_words = updated_dict["categories"]["insult"]["words"]
        self.assertIn("trẩu tre", insult_words)
        self.assertIn("bóc mẽ", insult_words)

        # Check training dataset was updated on disk
        self.assertTrue(self.dataset_file.exists())
        with open(self.dataset_file, "r", encoding="utf-8") as f:
            dataset = json.load(f)
        self.assertEqual(len(dataset), 1)
        sample = dataset[0]
        self.assertEqual(sample["text"], "Thằng này trẩu tre thật sự, bóc mẽ nó ra đi")
        self.assertEqual(sample["label"], "bad")
        self.assertEqual(sample["new_keywords"], new_slang)
        self.assertEqual(sample["topic"], "Bóc phốt")

        # Check engine instantly detects the new word without restart
        scan_res = self.engine.analyze("Bạn này nhìn trẩu tre quá")
        self.assertTrue(scan_res.is_toxic)
        self.assertIn("trẩu tre", scan_res.matched_words)

    def test_db_update_user_review(self):
        c = CommentModel(
            id="cmt_review_test_1",
            post_id="p1",
            post_url="https://threads.net/post/1",
            content="Nội dung kiểm tra tự đánh giá",
            is_toxic=False,
            toxic_score=0.2
        )
        self.db.upsert_comment(c)

        # Apply user review
        updated = self.db.update_user_review(
            comment_id="cmt_review_test_1",
            user_review="bad",
            user_score=0.95,
            user_keywords=["từ lóng test"]
        )
        self.assertTrue(updated)

        # Retrieve and verify
        curated_df = self.db.get_curated_export_df(filter_status="all")
        row = curated_df[curated_df["Mã ID"] == "cmt_review_test_1"].iloc[0]
        self.assertIn("Xấu luôn", str(row["Tự đánh giá của bạn (Xấu luôn / Chưa rõ / Trong sạch)"]))
        self.assertEqual(str(row["Từ lóng mới bổ sung (nếu có)"]), "từ lóng test")

    def test_propagate_learned_keywords(self):
        # Insert 2 unreviewed comments: one with the new slang, one clean
        c1 = CommentModel(
            id="cmt_future_1",
            post_id="p1",
            post_url="https://threads.net/p1",
            content="Thằng này md quá trời ơi",
            is_toxic=False,
            toxic_score=0.0,
            matched_words=[]
        )
        c2 = CommentModel(
            id="cmt_clean_1",
            post_id="p1",
            post_url="https://threads.net/p1",
            content="Chúc bạn một ngày vui vẻ và tốt lành",
            is_toxic=False,
            toxic_score=0.0,
            matched_words=[]
        )
        self.db.upsert_comment(c1)
        self.db.upsert_comment(c2)

        # Teach engine the word 'md'
        self.engine.learn_from_user_evaluation(
            text="md",
            user_review="bad",
            new_keywords=["md"],
            category="slang"
        )

        # Propagate
        updated_count = self.db.propagate_learned_keywords(["md"], self.engine)
        self.assertEqual(updated_count, 1)

        # Check comment in database
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM comments WHERE id = 'cmt_future_1'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["is_toxic"], 1)
            self.assertIn("md", json.loads(row["matched_words"]))
            self.assertGreaterEqual(row["toxic_score"], 0.4)

    def test_search_and_get_learned_keywords(self):
        self.engine.learn_from_user_evaluation(
            text="con này ảo tưởng sức mạnh",
            user_review="bad",
            new_keywords=["ảo tưởng"],
            category="slang"
        )

        # Search
        results = self.engine.search_keywords("ảo tưởng")
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0]["word"], "ảo tưởng")

        # Get user learned
        learned = self.engine.get_user_learned_keywords()
        words = [item["keyword"] for item in learned]
        self.assertIn("ảo tưởng", words)

if __name__ == "__main__":
    unittest.main()

