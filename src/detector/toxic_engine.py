import json
import re
from datetime import datetime
from typing import List, Dict, Set, Optional, Any
from pathlib import Path

from config.settings import (
    TOXIC_KEYWORDS_FILE,
    TRAINING_DATASET_FILE,
    TOXIC_SCORE_THRESHOLD,
    HIGH_SEVERITY_THRESHOLD
)
from src.detector.categories import (
    ToxicCategory, CATEGORY_LABELS, SEVERITY_VI_LABELS,
    ReviewStatus, REVIEW_STATUS_VI,
    ToxicWordMatch, ToxicAnalysisResult
)
from src.detector.text_normalizer import normalize_text, remove_vietnamese_accents, deobfuscate_leetspeak
from src.utils.logger import logger

class ToxicDetectionEngine:
    """
    Engine to analyze Vietnamese text and detect offensive, toxic, slang, and abusive language,
    including accents, unaccented variants, teencode, and sensitive emojis/icons.
    """

    def __init__(self, dict_path: Optional[Path] = None, dataset_path: Optional[Path] = None):
        self.dict_path = dict_path or TOXIC_KEYWORDS_FILE
        self.dataset_path = dataset_path or TRAINING_DATASET_FILE
        self.categories_data: Dict[str, Dict] = {}
        self.emojis_data: Dict[str, Dict] = {}
        self.whitelist: Set[str] = set()
        self.compiled_patterns: Dict[str, List[re.Pattern]] = {}
        self.load_dictionary()

    def load_dictionary(self):
        """Load toxic words, emojis, and rules from JSON file."""
        if not self.dict_path.exists():
            raise FileNotFoundError(f"Toxic dictionary file not found: {self.dict_path}")

        with open(self.dict_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.categories_data = data.get("categories", {})
        self.emojis_data = data.get("emojis", {})
        self.whitelist = set(w.lower().strip() for w in data.get("whitelist", []))
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for word boundary and phrase matching."""
        self.compiled_patterns = {}
        for cat, cat_info in self.categories_data.items():
            patterns = []
            words = cat_info.get("words", [])
            for word in words:
                word_clean = word.lower().strip()
                if not word_clean:
                    continue
                escaped = re.escape(word_clean)
                pattern_str = rf"(?<![\wÀ-ỹ]){escaped}(?![\wÀ-ỹ])"
                try:
                    p = re.compile(pattern_str, re.IGNORECASE)
                    patterns.append((word_clean, p))
                except re.error:
                    pass
            self.compiled_patterns[cat] = patterns

    def add_keyword(self, word: str, category: str = "profanity") -> bool:
        """Dynamically add a new toxic keyword."""
        word = word.lower().strip()
        if not word:
            return False
        if category not in self.categories_data:
            self.categories_data[category] = {
                "name_vi": CATEGORY_LABELS.get(category, category),
                "severity_multiplier": 1.0,
                "words": []
            }
        if word not in self.categories_data[category]["words"]:
            self.categories_data[category]["words"].append(word)
            self._compile_patterns()
            return True
        return False

    def remove_keyword(self, word: str) -> bool:
        """Remove a keyword from all categories."""
        word = word.lower().strip()
        removed = False
        for cat in self.categories_data:
            if word in self.categories_data[cat].get("words", []):
                self.categories_data[cat]["words"].remove(word)
                removed = True
        if removed:
            self._compile_patterns()
        return removed

    def save_dictionary(self):
        """Save current keywords back to disk."""
        data = {
            "categories": self.categories_data,
            "emojis": self.emojis_data,
            "whitelist": list(self.whitelist)
        }
        with open(self.dict_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def learn_from_user_evaluation(
        self,
        text: str,
        user_review: str,
        new_keywords: Optional[List[str]] = None,
        category: str = "profanity",
        post_context: str = "",
        topic: str = ""
    ) -> Dict[str, Any]:
        """
        Integrate human-in-the-loop evaluations into knowledge base:
        1. Add newly marked toxic keywords/slang into config/toxic_keywords.json.
        2. Append the verified sample into data/training_dataset.json for gradual automation.
        3. Recompile regex patterns immediately for instant learning.
        """
        text = (text or "").strip()
        added_keywords = []

        if user_review == "bad":
            if new_keywords:
                for kw in new_keywords:
                    clean_kw = kw.strip().lower()
                    if clean_kw and self.add_keyword(clean_kw, category=category):
                        added_keywords.append(clean_kw)

            if added_keywords:
                self.save_dictionary()
                logger.info(f"Learned {len(added_keywords)} new toxic keywords from user evaluation: {added_keywords}")

        # Update training dataset JSON
        dataset = []
        if TRAINING_DATASET_FILE.exists():
            try:
                with open(TRAINING_DATASET_FILE, "r", encoding="utf-8") as f:
                    dataset = json.load(f)
                    if not isinstance(dataset, list):
                        dataset = []
            except Exception:
                dataset = []

        # Avoid exact duplicate text in dataset
        existing_texts = {item.get("content", "") for item in dataset}
        if text and text not in existing_texts:
            status_labels = {
                "bad": "Xấu luôn (Rõ ràng)",
                "ambiguous": "Chưa rõ (Nghi ngờ)",
                "clean": "Trong sạch"
            }
            sample = {
                "content": text,
                "user_review": user_review,
                "user_review_vi": status_labels.get(user_review, user_review),
                "learned_keywords": added_keywords,
                "post_context": post_context,
                "topic": topic,
                "timestamp": datetime.now().isoformat()
            }
            dataset.append(sample)
            try:
                with open(TRAINING_DATASET_FILE, "w", encoding="utf-8") as f:
                    json.dump(dataset, f, ensure_ascii=False, indent=2)
                logger.info(f"Saved user evaluation to {TRAINING_DATASET_FILE.name} (Total samples: {len(dataset)})")
            except Exception as e:
                logger.error(f"Failed to write training dataset: {e}")

        return {
            "status": "success",
            "added_keywords": added_keywords,
            "total_dataset_samples": len(dataset)
        }

    def analyze(self, text: str) -> ToxicAnalysisResult:
        """
        Analyze a given string for offensive content, slang, and toxic emojis.
        Returns a ToxicAnalysisResult with score, severity, matched words, and emojis.
        """
        if not text or not text.strip():
            return ToxicAnalysisResult(
                text=text or "",
                is_toxic=False,
                score=0.0,
                severity="clean",
                severity_vi="Trong sạch",
                matched_words=[],
                matched_emojis=[],
                has_emoji_slang=False,
                categories=[],
                category_names=[],
                details=[]
            )

        # Check whitelist phrases first
        text_lower = text.lower()
        for white_phrase in self.whitelist:
            if white_phrase and white_phrase in text_lower:
                if len(text_lower.strip()) <= len(white_phrase) + 5:
                    return ToxicAnalysisResult(
                        text=text,
                        is_toxic=False,
                        score=0.0,
                        severity="clean",
                        severity_vi="Trong sạch",
                        matched_words=[],
                        matched_emojis=[],
                        has_emoji_slang=False,
                        categories=[],
                        category_names=[],
                        details=[]
                    )

        # Prepare normalized variants for multi-layer inspection
        norm_text = normalize_text(text)
        deobf_text = deobfuscate_leetspeak(norm_text)
        unaccented_text = remove_vietnamese_accents(norm_text)

        matches: List[ToxicWordMatch] = []
        detected_words_set: Set[str] = set()
        detected_emojis_set: Set[str] = set()
        detected_categories_set: Set[str] = set()
        total_raw_score = 0.0

        # Layer 1: Check Emoji / Icon slangs
        for emoji_char, emoji_info in self.emojis_data.items():
            if emoji_char in text:
                cat = emoji_info.get("category", "profanity")
                cat_name = self.categories_data.get(cat, {}).get("name_vi", CATEGORY_LABELS.get(cat, cat))
                label = f"{emoji_char} ({emoji_info.get('label', 'Icon nhạy cảm')})"
                detected_emojis_set.add(label)
                detected_categories_set.add(cat)
                weight = emoji_info.get("weight", 0.5)
                total_raw_score += weight
                matches.append(ToxicWordMatch(
                    word=label,
                    category=cat,
                    category_name=cat_name,
                    start_pos=text.find(emoji_char),
                    end_pos=text.find(emoji_char) + len(emoji_char),
                    is_emoji=True
                ))

        # Layer 2: Check Toxic Words & Slang (có dấu, không dấu, teencode)
        for cat, patterns in self.compiled_patterns.items():
            cat_info = self.categories_data.get(cat, {})
            cat_name = cat_info.get("name_vi", CATEGORY_LABELS.get(cat, cat))
            multiplier = cat_info.get("severity_multiplier", 1.0)

            for word_clean, pattern in patterns:
                found = False
                for t in [norm_text, deobf_text, unaccented_text]:
                    for m in pattern.finditer(t):
                        if word_clean not in detected_words_set:
                            matches.append(ToxicWordMatch(
                                word=word_clean,
                                category=cat,
                                category_name=cat_name,
                                start_pos=m.start(),
                                end_pos=m.end(),
                                is_emoji=False
                            ))
                            detected_words_set.add(word_clean)
                            detected_categories_set.add(cat)
                            total_raw_score += (0.35 * multiplier)
                            found = True
                    if found:
                        break

        # Calculate final normalized score (bounded [0.0, 1.0])
        score = min(1.0, round(total_raw_score, 2))
        is_toxic = score >= TOXIC_SCORE_THRESHOLD

        # Determine severity label
        if score == 0.0:
            severity = "clean"
        elif score < TOXIC_SCORE_THRESHOLD:
            severity = "low"
        elif score < HIGH_SEVERITY_THRESHOLD:
            severity = "medium"
        elif score < 0.9:
            severity = "high"
        else:
            severity = "critical"

        severity_vi = SEVERITY_VI_LABELS.get(severity, "Trong sạch")

        cat_names = [
            self.categories_data.get(c, {}).get("name_vi", CATEGORY_LABELS.get(c, c))
            for c in detected_categories_set
        ]

        has_emoji = len(detected_emojis_set) > 0

        # Determine review_status (Xấu luôn vs Chưa rõ nghi ngờ vs Trong sạch)
        has_heavy_violation = any(c in ["threat_violence", "regional_discrimination", "harassment_sexual"] for c in detected_categories_set)
        # Heavy profanity / strong insult
        strong_words = {"đm", "địt mẹ", "lồn", "cặc", "buồi", "chém chết", "giết mày", "bake", "namky", "cali", "óc chó", "súc vật"}
        has_strong_word = any(w in strong_words for w in detected_words_set)

        if score >= 0.5 or has_heavy_violation or has_strong_word:
            review_status = "bad"
        elif score >= 0.15 or len(detected_words_set) > 0 or has_emoji:
            review_status = "ambiguous"
        else:
            review_status = "clean"

        review_status_vi = REVIEW_STATUS_VI.get(review_status, "Trong sạch")

        return ToxicAnalysisResult(
            text=text,
            is_toxic=is_toxic,
            score=score,
            severity=severity,
            severity_vi=severity_vi,
            review_status=review_status,
            review_status_vi=review_status_vi,
            matched_words=list(detected_words_set),
            matched_emojis=list(detected_emojis_set),
            has_emoji_slang=has_emoji,
            categories=list(detected_categories_set),
            category_names=cat_names,
            details=matches
        )

    def learn_from_user_evaluation(
        self,
        text: str,
        user_review: str,
        new_keywords: Optional[List[str]] = None,
        category: str = "insult",
        post_context: str = "",
        topic: str = ""
    ) -> Dict[str, Any]:
        """
        Active Learning Loop:
        1. When user annotates a comment (Xấu luôn / Chưa rõ / Trong sạch),
           add any new slang or toxic keywords to config/toxic_keywords.json.
        2. Append the annotated record to data/training_dataset.json.
        3. Immediately reload dictionary & regex patterns in memory.
        """
        new_keywords = new_keywords or []
        added_keywords = []

        # 1. Update dictionary if new keywords provided
        if new_keywords:
            try:
                with open(self.dict_path, "r", encoding="utf-8") as f:
                    dict_data = json.load(f)

                # If dict has top-level toxic_words list
                if "toxic_words" in dict_data and isinstance(dict_data["toxic_words"], list):
                    tw_set = set(w.lower().strip() for w in dict_data["toxic_words"])
                    for kw in new_keywords:
                        kw_clean = kw.strip().lower()
                        if kw_clean and kw_clean not in tw_set:
                            dict_data["toxic_words"].append(kw.strip())
                            tw_set.add(kw_clean)
                            if kw.strip() not in added_keywords:
                                added_keywords.append(kw.strip())

                # If dict has categories
                if "categories" in dict_data and isinstance(dict_data["categories"], dict):
                    target_cat = category if category in dict_data["categories"] else (
                        "insult" if "insult" in dict_data["categories"] else next(iter(dict_data["categories"].keys()))
                    )
                    cat_val = dict_data["categories"][target_cat]
                    if isinstance(cat_val, dict):
                        cat_words = cat_val.setdefault("words", [])
                    elif isinstance(cat_val, list):
                        cat_words = cat_val
                    else:
                        cat_words = []

                    cat_set = set(w.lower().strip() for w in cat_words)
                    for kw in new_keywords:
                        kw_clean = kw.strip().lower()
                        if kw_clean and kw_clean not in cat_set:
                            cat_words.append(kw.strip())
                            cat_set.add(kw_clean)
                            if kw.strip() not in added_keywords:
                                added_keywords.append(kw.strip())

                if added_keywords:
                    with open(self.dict_path, "w", encoding="utf-8") as f:
                        json.dump(dict_data, f, ensure_ascii=False, indent=2)
                    self.load_dictionary()
                    logger.info(f"Learned {len(added_keywords)} new keywords into {self.dict_path.name}: {added_keywords}")
            except Exception as e:
                logger.error(f"Error updating toxic dictionary: {e}")

        # 2. Append sample to training dataset (JSON)
        dataset_path = getattr(self, "dataset_path", None) or TRAINING_DATASET_FILE
        try:
            dataset_path.parent.mkdir(parents=True, exist_ok=True)
            dataset_records = []
            if dataset_path.exists():
                try:
                    with open(dataset_path, "r", encoding="utf-8") as f:
                        dataset_records = json.load(f)
                        if not isinstance(dataset_records, list):
                            dataset_records = []
                except Exception:
                    dataset_records = []

            new_record = {
                "text": text,
                "label": user_review,
                "new_keywords": new_keywords,
                "post_context": post_context,
                "topic": topic,
                "reviewed_at": datetime.now().isoformat()
            }
            dataset_records.append(new_record)

            with open(dataset_path, "w", encoding="utf-8") as f:
                json.dump(dataset_records, f, ensure_ascii=False, indent=2)
            logger.info(f"Recorded annotation in {dataset_path.name} (Total: {len(dataset_records)} samples)")
        except Exception as e:
            logger.error(f"Error updating training dataset: {e}")

        return {
            "status": "success",
            "added_keywords": added_keywords,
            "user_review": user_review
        }

# Global engine instance
toxic_engine = ToxicDetectionEngine()
ToxicEngine = ToxicDetectionEngine
