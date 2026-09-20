import unittest
from src.detector.text_normalizer import normalize_text, reduce_repeated_chars, remove_vietnamese_accents, deobfuscate_leetspeak
from src.detector.toxic_engine import ToxicDetectionEngine

class TestToxicEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = ToxicDetectionEngine()

    def test_text_normalizer(self):
        # Repeated chars
        self.assertEqual(reduce_repeated_chars("đmmmmmmm"), "đmm")
        self.assertEqual(reduce_repeated_chars("nguuuuuu"), "nguu")
        # Leetspeak
        self.assertEqual(deobfuscate_leetspeak("c@c"), "cac")
        # Vietnamese accents
        self.assertEqual(remove_vietnamese_accents("Chào bạn"), "Chao ban")

    def test_clean_sentences(self):
        clean_samples = [
            "Hôm nay trời đẹp quá, chúc mọi người một ngày vui vẻ.",
            "Bài viết này chia sẻ rất nhiều kiến thức bổ ích, cảm ơn tác giả!",
            "Mình rất thích nội dung này.",
            "Cảm ơn bạn nhiều nhé!"
        ]
        for s in clean_samples:
            res = self.engine.analyze(s)
            self.assertFalse(res.is_toxic, f"False positive for: '{s}' with words {res.matched_words}")
            self.assertEqual(res.score, 0.0)

    def test_profanity_detection(self):
        profane_samples = [
            ("Cái này như lồn vậy", "lồn"),
            ("Đm nói nhiều vcl", "đm"),
            ("Thằng chó đẻ cút đi", "chó đẻ")
        ]
        for text, expected_word in profane_samples:
            res = self.engine.analyze(text)
            self.assertTrue(res.is_toxic, f"Failed to detect profanity in: '{text}'")
            self.assertGreaterEqual(res.score, 0.3)

    def test_insult_detection(self):
        insult_samples = [
            "Mày ngu học óc chó thế",
            "Đúng là thứ não tàn súc vật",
            "Đồ đần độn mất dạy"
        ]
        for text in insult_samples:
            res = self.engine.analyze(text)
            self.assertTrue(res.is_toxic, f"Failed to detect insult in: '{text}'")

    def test_regional_discrimination(self):
        regional_samples = [
            "Mấy thằng bake cút về nước",
            "Lũ namky mọi miên",
            "Bọn ba que đu càng cali"
        ]
        for text in regional_samples:
            res = self.engine.analyze(text)
            self.assertTrue(res.is_toxic, f"Failed to detect regional slur in: '{text}'")

    def test_violence_threat(self):
        threat_samples = [
            "Tao sẽ chém chết mày",
            "Ra đường tao đập nát mặt"
        ]
        for text in threat_samples:
            res = self.engine.analyze(text)
            self.assertTrue(res.is_toxic, f"Failed to detect threat in: '{text}'")

    def test_slang_and_unaccented(self):
        slang_samples = [
            "May dung co xam lol voi tao",
            "Dit me may thich gi",
            "Dung la thu oc cho",
            "Con di nay cut di"
        ]
        for text in slang_samples:
            res = self.engine.analyze(text)
            self.assertTrue(res.is_toxic, f"Failed to detect unaccented slang in: '{text}'")

    def test_emoji_detection(self):
        emoji_samples = [
            "Nhìn mặt ghét vl 🖕",
            "Bài viết như 💩",
            "Đúng là thằng hề 🤡",
            "Lũ bake 🐒"
        ]
        for text in emoji_samples:
            res = self.engine.analyze(text)
            self.assertTrue(res.is_toxic, f"Failed to detect toxic emoji in: '{text}'")
            self.assertTrue(res.has_emoji_slang, f"Expected has_emoji_slang=True for: '{text}'")
            self.assertGreater(len(res.matched_emojis), 0)

if __name__ == "__main__":
    unittest.main()
