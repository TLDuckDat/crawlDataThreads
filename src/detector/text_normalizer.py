import re
import unicodedata

# Mapping Vietnamese characters with accents to non-accented
VIETNAMESE_ACCENT_MAP = {
    'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
    'ă': 'a', 'ằ': 'a', 'ắ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
    'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
    'đ': 'd',
    'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
    'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
    'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
    'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
    'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
    'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
    'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
    'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
    'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
}

# Common leetspeak obfuscations
LEET_MAP = {
    '@': 'a',
    '0': 'o',
    '1': 'i',
    '3': 'e',
    '4': 'a',
    '5': 's',
    '7': 't',
    '$': 's',
    '*': '',
    '_': ' ',
    '.': ' ',
    '-': ' ',
}

def remove_vietnamese_accents(text: str) -> str:
    """Convert accented Vietnamese string to plain ASCII."""
    text = unicodedata.normalize('NFD', text)
    result = []
    for char in text:
        if unicodedata.category(char) != 'Mn':
            c_lower = char.lower()
            if c_lower in VIETNAMESE_ACCENT_MAP:
                result.append(VIETNAMESE_ACCENT_MAP[c_lower])
            elif c_lower == 'đ':
                result.append('d')
            elif c_lower == 'Đ':
                result.append('D')
            else:
                result.append(char)
    return "".join(result)

def reduce_repeated_chars(text: str) -> str:
    """
    Reduce characters repeated more than twice into at most 2 characters.
    e.g. 'đmmmmmm' -> 'đmm', 'nguuuuuu' -> 'nguu', 'clgtttt' -> 'clgtt'
    """
    return re.sub(r'(.)\1{2,}', r'\1\1', text)

def deobfuscate_leetspeak(text: str) -> str:
    """Replace common leetspeak characters."""
    chars = []
    for c in text:
        chars.append(LEET_MAP.get(c, c))
    return "".join(chars)

def normalize_text(text: str) -> str:
    """
    Comprehensive text normalization for offensive language detection.
    """
    if not text:
        return ""
    # Unicode standard normalization
    text = unicodedata.normalize('NFC', text.strip().lower())
    # Reduce elongated characters (e.g. 'đmmmm' -> 'đmm')
    text = reduce_repeated_chars(text)
    # Collapse multiple whitespaces
    text = re.sub(r'\s+', ' ', text)
    return text

# Regex matching foreign scripts (Chinese, Japanese, Korean, Thai, Arabic, Cyrillic...)
FOREIGN_SCRIPTS_PATTERN = re.compile(
    r'[\u4e00-\u9fff'       # CJK Unified Ideographs (Chinese Hanzi / Japanese Kanji)
    r'\u3400-\u4dbf'       # CJK Unified Ideographs Extension A
    r'\uf900-\ufaff'       # CJK Compatibility Ideographs
    r'\u3000-\u303f'       # CJK Symbols and Punctuation
    r'\u3040-\u309f'       # Japanese Hiragana
    r'\u30a0-\u30ff'       # Japanese Katakana
    r'\u31f0-\u31ff'       # Japanese Katakana Phonetic Extensions
    r'\uff65-\uff9f'       # Japanese Halfwidth Katakana
    r'\uac00-\ud7af'       # Korean Hangul Syllables
    r'\u1100-\u11ff'       # Korean Hangul Jamo
    r'\u3130-\u318f'       # Korean Compatibility Jamo
    r'\u0e00-\u0e7f'       # Thai
    r'\u0600-\u06ff'       # Arabic
    r'\u0400-\u04ff'       # Cyrillic (Russian, etc.)
    r'\u0900-\u097f'       # Devanagari (Hindi)
    r']+'
)

LATIN_VIET_PATTERN = re.compile(r'[a-zA-ZàáạảãăắằẳẵặâấầẩẫậèéẹẻẽêếềểễệìíịỉĩòóọỏõôốồổỗộơớờởỡợùúụủũưứừửữựỳýỵỷỹđĐ]')

def contains_foreign_script(text: str) -> bool:
    """Check if text contains any Chinese, Japanese, Korean, Thai, Arabic, or Cyrillic characters."""
    if not text:
        return False
    return bool(FOREIGN_SCRIPTS_PATTERN.search(text))

def clean_to_viet_eng(text: str) -> str:
    """
    Strips out foreign characters (Chinese, Japanese, Korean, Thai, etc.)
    leaving only Vietnamese and English letters, numbers, punctuation, and emojis.
    Collapses all redundant spaces, newlines, and tabs.
    """
    if not text:
        return ""
    cleaned = FOREIGN_SCRIPTS_PATTERN.sub('', text)
    # Collapse multiple whitespace (spaces, tabs, newlines) into single space
    cleaned = " ".join(cleaned.split())
    return cleaned

def is_valid_viet_eng_content(text: str, max_foreign_ratio: float = 0.15) -> bool:
    """
    Determine if content is valid Vietnamese or English content.
    Returns False if the text is primarily or completely in foreign scripts (Chinese, Japanese, Korean...).
    """
    if not text or not str(text).strip():
        return False

    raw_text = str(text).strip()
    foreign_matches = FOREIGN_SCRIPTS_PATTERN.findall(raw_text)

    # If no foreign characters present, it's 100% Viet/Eng/Numbers/Icons
    if not foreign_matches:
        # Check if it has at least some meaningful alphanumeric or emoji content
        return len(raw_text) >= 1

    # Has foreign characters: calculate proportion
    foreign_char_count = sum(len(m) for m in foreign_matches)
    non_space_chars = len(re.sub(r'\s+', '', raw_text))
    foreign_ratio = foreign_char_count / max(1, non_space_chars)

    # Check if there are any Latin/Vietnamese letters
    has_latin = bool(LATIN_VIET_PATTERN.search(raw_text))

    # If no Latin/Vietnamese letters at all (e.g. 100% Chinese/Korean/Japanese), SKIP!
    if not has_latin:
        return False

    # If foreign characters dominate (e.g. > 15%), SKIP!
    if foreign_ratio > max_foreign_ratio:
        return False

    return True

def highlight_comment_text(text: str, highlight_words=None) -> str:
    """Highlight detected toxic words/emojis in HTML."""
    import html
    if not text:
        return ""
    escaped = html.escape(text)
    if not highlight_words:
        return escaped.replace("\n", "<br>")

    valid_words = [str(w).strip() for w in highlight_words if w and str(w).strip()]
    for w in sorted(set(valid_words), key=len, reverse=True):
        pattern = re.compile(rf"({re.escape(html.escape(w))})", re.IGNORECASE)
        escaped = pattern.sub(
            r"<mark style='background-color:#FEE2E2; color:#B91C1C; font-weight:700; padding:2px 6px; border-radius:4px; border:1px solid #FCA5A5;'>\1</mark>",
            escaped
        )
    return escaped.replace("\n", "<br>")

def extract_candidate_words(text: str, matched_words=None, matched_emojis=None) -> list:
    """Extract distinct words and tokens from comment text for interactive bad-word selection."""
    candidates = []
    seen = set()

    # 1. Matched words and emojis first
    if matched_words:
        for w in matched_words:
            w_s = str(w).strip()
            if w_s and w_s.lower() not in seen:
                candidates.append(w_s)
                seen.add(w_s.lower())
    if matched_emojis:
        for e in matched_emojis:
            e_s = str(e).strip()
            if e_s and e_s not in seen:
                candidates.append(e_s)
                seen.add(e_s)

    # 2. Extract words from comment text
    tokens = re.findall(r'[\wÀ-ỹ]+|[^\w\s]', text or "", re.UNICODE)
    ignore_punct = set('.,;:!?()[]{}\'\"/\\-–—_+=*&^%$#@~`<>|0123456789\t\r\n')
    for t in tokens:
        t_clean = t.strip()
        if t_clean and t_clean not in ignore_punct and len(t_clean) > 0:
            if t_clean.lower() not in seen:
                candidates.append(t_clean)
                seen.add(t_clean.lower())

    return candidates


