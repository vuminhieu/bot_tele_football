"""Scheduled job callbacks for weekly poll lifecycle.

Jobs:
  - create_weekly_poll: Friday 8:30 AM — create poll + pin
  - send_vote_reminder: Monday 8:30 AM — remind non-voters
  - close_weekly_poll: Monday 12:00 PM — stop poll
"""

import logging

from telegram.ext import ContextTypes

from bot.config import CHAT_ID
from bot.database import (
    close_poll,
    get_current_poll,
    get_non_voters,
    get_voters_by_option,
    save_poll,
)
from bot.utils import format_mention_list, format_vote_list, get_week_label

logger = logging.getLogger(__name__)


async def create_weekly_poll(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Friday 8:30 AM — Create a non-anonymous poll and pin it."""
    week_label = get_week_label()
    question = f"⚽ Đá bóng tuần tới ({week_label})?"

    try:
        message = await context.bot.send_poll(
            chat_id=CHAT_ID,
            question=question,
            options=["⚽ Đá", "❌ Không đá"],
            is_anonymous=False,
            allows_multiple_answers=False,
        )

        # Pin the poll message
        try:
            await context.bot.pin_chat_message(
                chat_id=CHAT_ID,
                message_id=message.message_id,
            )
        except Exception:
            logger.warning(
                "Failed to pin poll message. Bot may not have pin permissions."
            )

        # Save to database
        await save_poll(
            poll_id=message.poll.id,
            message_id=message.message_id,
            chat_id=CHAT_ID,
            week_label=week_label,
        )
        logger.info("Created weekly poll for %s (msg_id=%d)", week_label, message.message_id)

    except Exception:
        logger.exception("Failed to create weekly poll")


async def send_vote_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Monday 8:30 AM — Send reminder tagging non-voters."""
    poll = await get_current_poll()
    if not poll:
        logger.info("No open poll found for reminder.")
        return

    non_voters = await get_non_voters(poll["poll_id"])
    if not non_voters:
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text="✅ Tất cả đã vote! Sắp đóng vote lúc 12:00 trưa nay.",
        )
        return

    mentions = format_mention_list(non_voters)
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text=(
            f"⏰ Sắp hết hạn vote lúc 12:00 trưa nay!\n\n"
            f"Chưa vote ({len(non_voters)} người):\n{mentions}"
        ),
        parse_mode="HTML",
    )
    logger.info("Sent vote reminder. %d non-voters tagged.", len(non_voters))


async def close_weekly_poll(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Monday 12:00 PM — Stop the poll and save final results."""
    poll = await get_current_poll()
    if not poll:
        logger.info("No open poll to close.")
        return

    try:
        await context.bot.stop_poll(
            chat_id=poll["chat_id"],
            message_id=poll["message_id"],
        )
    except Exception:
        logger.warning("Failed to stop poll via Telegram API (may already be closed).")

    await close_poll(poll["poll_id"])

    # Send summary
    voters_play = await get_voters_by_option(poll["poll_id"], 0)
    voters_skip = await get_voters_by_option(poll["poll_id"], 1)
    non_voters = await get_non_voters(poll["poll_id"])

    summary = format_vote_list(
        poll["week_label"], voters_play, voters_skip, non_voters
    )
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text=f"🔒 Vote đã đóng!\n\n{summary}",
        parse_mode="HTML",
    )
    logger.info("Closed poll for %s", poll["week_label"])
