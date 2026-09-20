from enum import Enum
from dataclasses import dataclass, field
from typing import List

class ToxicCategory(str, Enum):
    PROFANITY = "profanity"                     # Chửi thề, tục tĩu
    INSULT = "insult"                           # Lăng mạ, xúc phạm nhân phẩm
    REGIONAL_DISCRIMINATION = "regional_discrimination" # Phân biệt vùng miền
    THREAT_VIOLENCE = "threat_violence"         # Đe dọa bạo lực
    HARASSMENT_SEXUAL = "harassment_sexual"     # Quấy rối, thô tục 18+
    SLANG = "slang"                             # Từ lóng / Teencode nhạy cảm

class ReviewStatus(str, Enum):
    BAD = "bad"                  # Xấu luôn (Độc hại rõ ràng)
    AMBIGUOUS = "ambiguous"      # Chưa rõ (Nghi ngờ / Cần duyệt lại)
    CLEAN = "clean"              # Trong sạch

REVIEW_STATUS_VI = {
    ReviewStatus.BAD: "Xấu luôn (Rõ ràng)",
    ReviewStatus.AMBIGUOUS: "Chưa rõ (Nghi ngờ)",
    ReviewStatus.CLEAN: "Trong sạch",
    "bad": "Xấu luôn (Rõ ràng)",
    "ambiguous": "Chưa rõ (Nghi ngờ)",
    "clean": "Trong sạch"
}

CATEGORY_LABELS = {
    ToxicCategory.PROFANITY: "Chửi thề / Tục tĩu",
    ToxicCategory.INSULT: "Lăng mạ / Xúc phạm",
    ToxicCategory.REGIONAL_DISCRIMINATION: "Phân biệt vùng miền",
    ToxicCategory.THREAT_VIOLENCE: "Đe dọa bạo lực",
    ToxicCategory.HARASSMENT_SEXUAL: "Quấy rối / Thô tục",
    ToxicCategory.SLANG: "Từ lóng / Teencode nhạy cảm",
    "slang": "Từ lóng / Teencode nhạy cảm"
}

SEVERITY_VI_LABELS = {
    "clean": "Trong sạch",
    "low": "Độc hại thấp",
    "medium": "Độc hại trung bình",
    "high": "Độc hại cao",
    "critical": "Cực kỳ nguy hại"
}

@dataclass
class ToxicWordMatch:
    word: str
    category: str
    category_name: str
    start_pos: int
    end_pos: int
    is_emoji: bool = False

@dataclass
class ToxicAnalysisResult:
    text: str
    is_toxic: bool
    score: float  # 0.0 to 1.0
    severity: str  # "clean", "low", "medium", "high", "critical"
    severity_vi: str = "Trong sạch"
    review_status: str = "clean"       # "bad", "ambiguous", "clean"
    review_status_vi: str = "Trong sạch" # "Xấu luôn (Rõ ràng)", "Chưa rõ (Nghi ngờ)", "Trong sạch"
    matched_words: List[str] = field(default_factory=list)
    matched_emojis: List[str] = field(default_factory=list)
    has_emoji_slang: bool = False
    categories: List[str] = field(default_factory=list)
    category_names: List[str] = field(default_factory=list)
    details: List[ToxicWordMatch] = field(default_factory=list)
