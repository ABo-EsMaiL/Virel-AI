"""Environment settings; paths remain rooted at the project directory."""

import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

API_KEY = os.getenv("VIREL_API_KEY", "").strip()
CHROME_PROFILE_DIR = os.getenv("CHROME_PROFILE_DIR", "./runtime/browser-profile")
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime")
SESSION_DATA_PATH = os.path.join(RUNTIME_DIR, "session.json")
if not os.path.isabs(CHROME_PROFILE_DIR):
    CHROME_PROFILE_DIR = os.path.normpath(os.path.join(BASE_DIR, CHROME_PROFILE_DIR))
TEMP_UPLOADS_DIR = os.path.join(RUNTIME_DIR, "uploads")
os.makedirs(TEMP_UPLOADS_DIR, exist_ok=True)
HEADLESS = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-3.8-flash").strip()
THINKING_MODE = os.getenv("THINKING_MODE", "high").strip().lower()
ENABLE_SEARCH_GROUNDING = os.getenv("ENABLE_SEARCH_GROUNDING", "false").lower() in ("true", "1", "yes")
RATE_LIMIT = os.getenv("VIREL_RATE_LIMIT", "30/minute").strip()
MAX_CONCURRENT = int(os.getenv("VIREL_MAX_CONCURRENT", "1"))
PORT = int(os.getenv("PORT", "8001"))
TARGET_URL = "https://aistudio.google.com/prompts/new_chat"
