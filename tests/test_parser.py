import unittest
from src.crawler.parser import (
    generate_item_id,
    EXPAND_MORE_BUTTONS_JS,
    EXTRACT_THREADS_DATA_JS,
    SCROLL_FEED_JS,
    CHECK_LOGIN_WALL_JS
)

class TestParser(unittest.TestCase):
    def test_generate_item_id_from_url(self):
        url = "https://www.threads.net/@user/post/C4abc123xyz"
        item_id = generate_item_id("post", url, "some text", "user")
        self.assertEqual(item_id, "post_C4abc123xyz")

    def test_generate_item_id_from_hash(self):
        item_id = generate_item_id("cmt", "", "nội dung bình luận", "nguyenvana")
        self.assertTrue(item_id.startswith("cmt_"))
        self.assertEqual(len(item_id), 16)  # cmt_ (4) + 12 hex chars

    def test_js_scripts_exist_and_valid(self):
        self.assertIn("EXPAND_MORE_BUTTONS_JS", globals())
        self.assertIn("scrollview", SCROLL_FEED_JS)
        self.assertIn("scrollIntoView", SCROLL_FEED_JS)
        self.assertIn("say more with threads", CHECK_LOGIN_WALL_JS, "CHECK_LOGIN_WALL_JS should check login strings")
        self.assertIn("div[role=\"dialog\"]", EXTRACT_THREADS_DATA_JS, "Parser should ignore dialog contents")
        self.assertIn("isLoginWallText", EXTRACT_THREADS_DATA_JS, "Parser should filter login wall texts")

if __name__ == "__main__":
    unittest.main()
