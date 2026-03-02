"""Entry point for the Telegram Football Vote Bot.

Sets up the Application with:
  - PicklePersistence for job state survival
  - Scheduled jobs (Friday poll, Monday reminder, Monday close, daily member sync)
  - Command handlers (/list, /inactive, /help, /testpoll)
  - PollAnswer handler for real-time vote tracking
  - ChatMemberHandler for join/leave tracking
  - Auto-registration MessageHandler (fallback)
"""

import asyncio
import datetime
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PicklePersistence,
    PollAnswerHandler,
    filters,
)
from bot.config import BOT_TOKEN, PERSISTENCE_PATH, TIMEZONE
from bot.database import init_db
from bot.handlers.commands import (
    auto_register,
    cmd_getallmember,
    cmd_help,
    cmd_inactive,
    cmd_list,
    cmd_testclose,
    cmd_testpoll,
    cmd_testreminder,
    handle_chat_member_update,
)
from bot.handlers.poll_handler import handle_poll_answer
from bot.scheduler.jobs import (
    close_weekly_poll,
    create_weekly_poll,
    send_vote_reminder,
)
from bot.sync_members import sync_group_members

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class _VNFormatter(logging.Formatter):
    """Logging formatter that always uses Asia/Ho_Chi_Minh timezone."""

    def converter(self, timestamp):
        from datetime import datetime as _dt, timezone as _tz
        return _dt.fromtimestamp(timestamp, tz=ZoneInfo(TIMEZONE))

    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        if datefmt:
            return ct.strftime(datefmt)
        return ct.strftime("%Y-%m-%d %H:%M:%S")


_handler = logging.StreamHandler()
_handler.setFormatter(_VNFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logging.basicConfig(
    level=logging.INFO,
    handlers=[_handler],
)
# Reduce noise from httpx (used by python-telegram-bot internally)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

TZ = ZoneInfo(TIMEZONE)


# ---------------------------------------------------------------------------
# Post-init callback
# ---------------------------------------------------------------------------


async def post_init(application: Application) -> None:
    """Called after Application is fully initialized. Sets up DB + syncs members."""
    await init_db()
    try:
        count = await sync_group_members()
        logger.info("Initial member sync complete: %d members.", count)
    except Exception:
        logger.exception("Initial member sync failed. Will retry on daily schedule.")
    logger.info("Bot initialized successfully.")


async def _sync_members_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Daily job wrapper for sync_group_members."""
    try:
        count = await sync_group_members()
        logger.info("Daily member sync complete: %d members.", count)
    except Exception:
        logger.exception("Daily member sync failed.")


# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Build and run the Telegram bot application."""
    # Ensure data directory exists
    Path(PERSISTENCE_PATH).parent.mkdir(parents=True, exist_ok=True)

    persistence = PicklePersistence(filepath=PERSISTENCE_PATH)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .persistence(persistence)
        .post_init(post_init)
        .build()
    )

    # --- Scheduled Jobs ---------------------------------------------------
    job_queue = app.job_queue

    # Friday 8:30 AM — Create weekly poll
    job_queue.run_daily(
        create_weekly_poll,
        time=datetime.time(hour=8, minute=30, tzinfo=TZ),
        days=(4,),  # Friday (Monday=0 in python-telegram-bot)
        name="create_weekly_poll",
    )

    # Monday 8:30 AM — Remind non-voters
    job_queue.run_daily(
        send_vote_reminder,
        time=datetime.time(hour=8, minute=30, tzinfo=TZ),
        days=(0,),  # Monday
        name="send_vote_reminder",
    )

    # Monday 12:00 PM — Close poll
    job_queue.run_daily(
        close_weekly_poll,
        time=datetime.time(hour=12, minute=0, tzinfo=TZ),
        days=(0,),  # Monday
        name="close_weekly_poll",
    )

    # Daily 3:00 AM — Sync group members via Pyrogram
    job_queue.run_daily(
        _sync_members_job,
        time=datetime.time(hour=3, minute=0, tzinfo=TZ),
        name="sync_group_members",
    )

    # --- Command Handlers -------------------------------------------------
    app.add_handler(CommandHandler(["list", "ds"], cmd_list))
    app.add_handler(CommandHandler(["inactive", "vang"], cmd_inactive))
    app.add_handler(CommandHandler("getallmember", cmd_getallmember))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("testpoll", cmd_testpoll))
    app.add_handler(CommandHandler("testreminder", cmd_testreminder))
    app.add_handler(CommandHandler("testclose", cmd_testclose))

    # --- Poll Answer Handler ----------------------------------------------
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    # --- Chat Member Handler (join/leave tracking) ------------------------
    app.add_handler(ChatMemberHandler(
        handle_chat_member_update, ChatMemberHandler.CHAT_MEMBER
    ))

    # --- Auto-registration (lowest priority group, fallback) --------------
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & ~filters.COMMAND,
            auto_register,
        ),
        group=1,
    )

    # --- Start Polling ----------------------------------------------------
    logger.info("Starting bot polling...")
    # Python 3.14 no longer auto-creates an event loop in get_event_loop().
    # Ensure one exists before run_polling() to support PyCharm debugger
    # and any other environment where no loop is pre-created.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
