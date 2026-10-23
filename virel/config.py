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
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-flash-latest").strip()
THINKING_MODE = os.getenv("THINKING_MODE", "high").strip().lower()
ENABLE_SEARCH_GROUNDING = os.getenv("ENABLE_SEARCH_GROUNDING", "false").lower() in ("true", "1", "yes")
ENABLE_URL_CONTEXT = os.getenv("ENABLE_URL_CONTEXT", "true").lower() in ("true", "1", "yes")
PRESERVE_MARKDOWN = os.getenv("VIREL_PRESERVE_MARKDOWN", "false").lower() in ("true", "1", "yes")
RATE_LIMIT = os.getenv("VIREL_RATE_LIMIT", "30/minute").strip()
ENABLE_SERVER_TOOLS = os.getenv("VIREL_ENABLE_SERVER_TOOLS", "true").lower() in ("true", "1", "yes")

PORT = int(os.getenv("PORT", "8001"))
TARGET_URL = "https://aistudio.google.com/prompts/new_chat"

ACCOUNTS_STATE_PATH = os.path.join(RUNTIME_DIR, "accounts_state.json")

raw_profiles = os.getenv("CHROME_PROFILES", "").strip()
CHROME_PROFILES_LIST = [p.strip() for p in raw_profiles.split(",") if p.strip()] if raw_profiles else None
if CHROME_PROFILES_LIST:
    CHROME_PROFILES_LIST = [os.path.normpath(p if os.path.isabs(p) else os.path.join(BASE_DIR, p)) for p in CHROME_PROFILES_LIST]

raw_accounts = os.getenv("GOOGLE_ACCOUNTS", "").strip()
if raw_accounts:
    VIREL_GOOGLE_ACCOUNTS_COUNT = len([a for a in raw_accounts.split(",") if a.strip()])
else:
    VIREL_GOOGLE_ACCOUNTS_COUNT = int(os.getenv("VIREL_GOOGLE_ACCOUNTS_COUNT", "1"))
if VIREL_GOOGLE_ACCOUNTS_COUNT < 1:
    VIREL_GOOGLE_ACCOUNTS_COUNT = 1

VIREL_ACCOUNT_COOLDOWN_HOURS = float(os.getenv("VIREL_ACCOUNT_COOLDOWN_HOURS", "6"))
VIREL_ACCOUNT_COOLDOWN_SECONDS = max(60.0, VIREL_ACCOUNT_COOLDOWN_HOURS * 3600)



def positive_setting(name, default):
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


MAX_PDF_BYTES = positive_setting('VIREL_MAX_PDF_MB', 50) * 1024 * 1024
MAX_PDF_PAGES = positive_setting('VIREL_MAX_PDF_PAGES', 1000)
MAX_PDFS = positive_setting('VIREL_MAX_PDFS', 10)
MAX_REQUEST_BYTES = positive_setting('VIREL_MAX_REQUEST_MB', 128) * 1024 * 1024
MAX_AUDIO_BYTES = positive_setting('VIREL_MAX_AUDIO_MB', 25) * 1024 * 1024

MAX_VIDEO_BYTES = positive_setting("VIREL_MAX_VIDEO_MB", 50) * 1024 * 1024
MAX_VIDEOS = positive_setting("VIREL_MAX_VIDEOS", 2)
MAX_VIDEO_PIXELS = positive_setting("VIREL_MAX_VIDEO_PIXELS", 20_000_000)

DEFAULT_IMAGE_MODEL = os.getenv("DEFAULT_IMAGE_MODEL", "gemini-3.1-flash-lite-image").strip()
MAX_GENERATED_IMAGE_BYTES = positive_setting("VIREL_MAX_GENERATED_IMAGE_MB", 20) * 1024 * 1024

DEFAULT_SPEECH_MODEL = os.getenv('DEFAULT_SPEECH_MODEL', 'gemini-3.8-flash-tts').strip()
DEFAULT_SPEECH_VOICE = os.getenv('DEFAULT_SPEECH_VOICE', 'Fola').strip()
MAX_GENERATED_AUDIO_BYTES = positive_setting('VIREL_MAX_GENERATED_AUDIO_MB', 50) * 1024 * 1024
MAX_SPEECH_CHARACTERS = positive_setting('VIREL_MAX_SPEECH_CHARACTERS', 4096)
MAX_SPEECH_SECONDS = positive_setting('VIREL_MAX_SPEECH_SECONDS', 600)

TOOL_RUN_TTL_SECONDS = positive_setting("VIREL_TOOL_RUN_TTL_SECONDS", 600)

# File preprocessing limits; source/model/account limits still apply.
MAX_FILE_BYTES = positive_setting('VIREL_MAX_FILE_MB', 50) * 1024 * 1024
MAX_FILE_INPUTS = positive_setting('VIREL_MAX_FILE_INPUTS', 20)
MAX_DOCUMENT_TEXT_CHARS = positive_setting('VIREL_MAX_DOCUMENT_TEXT_CHARS', 2000000)
MAX_DOCUMENT_UNPACKED_BYTES = positive_setting('VIREL_MAX_DOCUMENT_UNPACKED_MB', 64) * 1024 * 1024
MAX_DOCUMENT_CELLS = positive_setting('VIREL_MAX_DOCUMENT_CELLS', 200000)
MAX_DOCUMENT_MEMORY_BYTES = positive_setting('VIREL_MAX_DOCUMENT_MEMORY_MB', 512) * 1024 * 1024


MAX_CONCURRENT = positive_setting("VIREL_MAX_CONCURRENT", 20)
MAX_QUEUE = positive_setting("VIREL_MAX_QUEUE", 100)
QUEUE_TIMEOUT_SECONDS = positive_setting("VIREL_QUEUE_TIMEOUT_SECONDS", 120)
MEMORY_RESERVE_MB = positive_setting("VIREL_MEMORY_RESERVE_MB", 1024)
TAB_MEMORY_MB = positive_setting("VIREL_TAB_MEMORY_MB", 512)
MAX_WAITING_TABS = positive_setting("VIREL_MAX_WAITING_TABS", 20)
