"""Configuration loader and environment verification.

Loads environment variables, validates paths, and provides configuration constants.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = BASE_DIR / "workspace"
DOWNLOADS_DIR = WORKSPACE_DIR / "downloads"
OUTPUTS_DIR = WORKSPACE_DIR / "outputs"

# Ensure runtime directories exist
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Load .env file
load_dotenv(dotenv_path=BASE_DIR / ".env")

# Telegram configurations
BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
_raw_user_id = os.getenv("ALLOWED_USER_ID", "0").strip()
try:
    ALLOWED_USER_ID: int = int(_raw_user_id)
except ValueError:
    raise ValueError(f"Invalid ALLOWED_USER_ID: {_raw_user_id}. Must be an integer.")

# Antigravity configurations
ANTIGRAVITY_BIN: str = os.getenv("ANTIGRAVITY_BIN", "antigravity").strip()
ANTIGRAVITY_MODEL: str = os.getenv("ANTIGRAVITY_MODEL", "gemini-3.8-flash-medium").strip()
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
# Task execution timeout (default: 1800s / 30 minutes)
_raw_timeout = os.getenv("TASK_TIMEOUT_SECONDS", "1800").strip()
try:
    TASK_TIMEOUT_SECONDS: int = int(_raw_timeout)
except ValueError:
    TASK_TIMEOUT_SECONDS = 1800

# Optional network proxy
HTTP_PROXY: str = os.getenv("HTTP_PROXY", "").strip()
HTTPS_PROXY: str = os.getenv("HTTPS_PROXY", "").strip()

# Apply proxies to current environment if provided
if HTTP_PROXY:
    os.environ["HTTP_PROXY"] = HTTP_PROXY
    os.environ["http_proxy"] = HTTP_PROXY
if HTTPS_PROXY:
    os.environ["HTTPS_PROXY"] = HTTPS_PROXY
    os.environ["https_proxy"] = HTTPS_PROXY

# Ensure PATH contains ~/.local/bin where nlm and notebooklm-mcp usually reside
LOCAL_BIN = Path.home() / ".local" / "bin"
if LOCAL_BIN.exists() and str(LOCAL_BIN) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{LOCAL_BIN}:{os.environ.get('PATH', '')}"


def validate_config() -> None:
    """Validate critical configuration settings on startup."""
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not configured in .env!")
    if not ALLOWED_USER_ID:
        raise ValueError("ALLOWED_USER_ID is not configured in .env!")
