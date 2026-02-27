"""Entry point for the Telegram Football Vote Bot.

Sets up the Application with:
  - PicklePersistence for job state survival
  - Scheduled jobs (Friday poll, Monday reminder, Monday close)
  - Command handlers (/register, /list, /inactive, /help, /testpoll)
  - PollAnswer handler for real-time vote tracking
  - Auto-registration MessageHandler
"""

import datetime
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    PicklePersistence,
    PollAnswerHandler,
    filters,
)

from bot.config import BOT_TOKEN, PERSISTENCE_PATH, TIMEZONE
from bot.database import init_db
from bot.handlers.commands import (
    auto_register,
    cmd_help,
    cmd_inactive,
    cmd_list,
    cmd_register,
    cmd_testpoll,
)
from bot.handlers.poll_handler import handle_poll_answer
from bot.scheduler.jobs import (
    close_weekly_poll,
    create_weekly_poll,
    send_vote_reminder,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# Reduce noise from httpx (used by python-telegram-bot internally)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

TZ = ZoneInfo(TIMEZONE)


# ---------------------------------------------------------------------------
# Post-init callback
# ---------------------------------------------------------------------------


async def post_init(application: Application) -> None:
    """Called after Application is fully initialized. Sets up DB."""
    await init_db()
    logger.info("Bot initialized successfully.")


# ---------------------------------------------------------------------------
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

    # --- Command Handlers -------------------------------------------------
    app.add_handler(CommandHandler("register", cmd_register))
    app.add_handler(CommandHandler(["list", "ds"], cmd_list))
    app.add_handler(CommandHandler(["inactive", "vang"], cmd_inactive))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("testpoll", cmd_testpoll))

    # --- Poll Answer Handler ----------------------------------------------
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    # --- Auto-registration (lowest priority group) ------------------------
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & ~filters.COMMAND,
            auto_register,
        ),
        group=1,
    )

    # --- Start Polling ----------------------------------------------------
    logger.info("Starting bot polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
