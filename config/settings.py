import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
EXPORTS_DIR = DATA_DIR / "exports"
CONFIG_DIR = BASE_DIR / "config"

# Database
DB_PATH = DATA_DIR / "threads_data.db"

# Persistent User Profiles (for Threads Login Session)
CHROME_PROFILE_DIR = DATA_DIR / "chrome_profile"
EDGE_PROFILE_DIR = DATA_DIR / "edge_profile"

# Toxic Dictionary Path
TOXIC_KEYWORDS_FILE = CONFIG_DIR / "toxic_keywords.json"
TRAINING_DATASET_FILE = DATA_DIR / "training_dataset.json"

# Crawler Settings
DEFAULT_HEADLESS = True
DEFAULT_PAGE_LOAD_TIMEOUT = 30
DEFAULT_SCROLL_DELAY = 2.0  # seconds between scrolls to load comments
DEFAULT_MAX_SCROLLS = 20
DEFAULT_MAX_COMMENTS = 100

# Browser User-Agent
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# Toxic Detection Thresholds
TOXIC_SCORE_THRESHOLD = 0.3  # Score >= 0.3 is marked as toxic / offensive
HIGH_SEVERITY_THRESHOLD = 0.7  # Score >= 0.7 is critical toxicity

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
