"""Bot configuration loaded from environment variables."""

import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    """Get required environment variable or exit with clear error."""
    value = os.environ.get(name)
    if not value:
        print(f"ERROR: Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


BOT_TOKEN: str = _require_env("BOT_TOKEN")
CHAT_ID: int = int(_require_env("CHAT_ID"))
TIMEZONE: str = "Asia/Ho_Chi_Minh"
DB_PATH: str = os.environ.get("DB_PATH", "data/bot.db")
PERSISTENCE_PATH: str = os.environ.get("PERSISTENCE_PATH", "data/bot_persistence")

# Pyrogram MTProto credentials (from https://my.telegram.org)
API_ID: int = int(_require_env("API_ID"))
API_HASH: str = _require_env("API_HASH")
