from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

@dataclass
class PostModel:
    id: str
    url: str
    author_username: str
    author_name: Optional[str] = ""
    author_profile_url: Optional[str] = ""
    content: str = ""
    posted_at: Optional[str] = ""
    likes: int = 0
    replies_count: int = 0
    reply_to: Optional[str] = ""
    image_urls: List[str] = field(default_factory=list)
    is_toxic: bool = False
    toxic_score: float = 0.0
    severity_vi: str = "Trong sạch"
    review_status: str = "clean"       # "bad", "ambiguous", "clean"
    review_status_vi: str = "Trong sạch" # "Xấu luôn (Rõ ràng)", "Chưa rõ (Nghi ngờ)", "Trong sạch"
    has_emoji_slang: bool = False
    matched_words: List[str] = field(default_factory=list)
    matched_emojis: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    session_id: Optional[str] = ""
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class CommentModel:
    id: str
    post_id: str
    post_url: str
    comment_url: Optional[str] = ""
    author_username: str = ""
    author_name: Optional[str] = ""
    author_profile_url: Optional[str] = ""
    content: str = ""
    posted_at: Optional[str] = ""
    likes: int = 0
    reply_to: Optional[str] = ""
    is_reply: bool = False
    parent_comment_id: Optional[str] = ""
    comment_type_vi: str = "Bình luận gốc"  # "Bình luận gốc" hoặc "Bình luận con (Phản hồi)"
    f0: str = ""  # Bình luận gốc (nếu cmt cần xử lý là reply)
    f1: str = ""  # Bình luận thế hệ F1 (reply cấp 1)
    f2: str = ""  # Bình luận thế hệ F2 (reply cấp 2)
    f3: str = ""  # Bình luận thế hệ F3 (reply cấp 3, nếu có)
    reply_level: int = 0  # 0: Gốc, 1: F1, 2: F2, 3: F3...
    image_urls: List[str] = field(default_factory=list)
    is_toxic: bool = False
    toxic_score: float = 0.0
    severity_vi: str = "Trong sạch"
    review_status: str = "clean"       # "bad", "ambiguous", "clean"
    review_status_vi: str = "Trong sạch" # "Xấu luôn (Rõ ràng)", "Chưa rõ (Nghi ngờ)", "Trong sạch"
    has_emoji_slang: bool = False
    matched_words: List[str] = field(default_factory=list)
    matched_emojis: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    session_id: Optional[str] = ""
    user_review: Optional[str] = ""       # "bad", "ambiguous", "clean"
    user_review_vi: Optional[str] = ""    # "Xấu luôn", "Chưa rõ", "Trong sạch"
    user_score: Optional[float] = None
    user_keywords: List[str] = field(default_factory=list)
    is_user_reviewed: bool = False
    user_reviewed_at: Optional[str] = ""
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class CrawlSessionModel:
    id: str
    target: str
    scrape_type: str  # "post", "search", "user", "feed"
    total_scraped: int = 0
    total_toxic: int = 0
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    status: str = "running"  # "running", "completed", "failed"
