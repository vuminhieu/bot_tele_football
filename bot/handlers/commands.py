"""Command handlers for the football vote bot.

Commands:
  /register — Register caller to the football group
  /list, /ds — Show current poll vote status
  /inactive, /vang — Show 3-consecutive skip voters
  /help — Show all available commands
  /testpoll — (Dev) Manually trigger poll creation
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import CHAT_ID
from bot.database import (
    get_consecutive_inactive,
    get_current_poll,
    get_non_voters,
    get_voters_by_option,
    register_member,
)
from bot.scheduler.jobs import create_weekly_poll
from bot.utils import format_inactive_list, format_vote_list

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auto-registration (MessageHandler callback, not a command)
# ---------------------------------------------------------------------------


async def auto_register(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Silently register any user who sends a message in the group."""
    user = update.effective_user
    if user and not user.is_bot:
        await register_member(user.id, user.username, user.full_name)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


async def cmd_register(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Explicitly register the caller to the football member list."""
    user = update.effective_user
    if not user:
        return
    await register_member(user.id, user.username, user.full_name)
    await update.message.reply_text(f"✅ Đăng ký thành công: {user.full_name}")


async def cmd_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show current poll vote status: who voted Đá / Không đá / Chưa vote."""
    poll = await get_current_poll()
    if not poll:
        await update.message.reply_text("📭 Chưa có vote nào đang mở.")
        return

    voters_play = await get_voters_by_option(poll["poll_id"], 0)
    voters_skip = await get_voters_by_option(poll["poll_id"], 1)
    non_voters = await get_non_voters(poll["poll_id"])

    text = format_vote_list(
        poll["week_label"], voters_play, voters_skip, non_voters
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_inactive(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show members who voted 'Không đá' 3 consecutive times."""
    inactive = await get_consecutive_inactive(n=3)
    text = format_inactive_list(inactive)
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_help(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show all available bot commands."""
    text = (
        "📋 <b>Danh sách lệnh:</b>\n\n"
        "/register - Đăng ký vào nhóm đá bóng\n"
        "/list - Xem danh sách vote hiện tại\n"
        "/inactive - Xem người 3 tuần liên tiếp vote không đá\n"
        "/help - Hiển thị trợ giúp\n\n"
        "<i>Bot tự động tạo vote thứ 6 8:30 sáng, "
        "nhắc thứ 2 8:30 sáng, đóng thứ 2 12:00 trưa.</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_testpoll(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Dev command: manually trigger poll creation for testing.

    Restricted to the configured CHAT_ID group only.
    """
    if update.effective_chat.id != CHAT_ID:
        await update.message.reply_text("This command only works in the configured group.")
        return
    await create_weekly_poll(context)
    await update.message.reply_text("\U0001f9ea Test poll created.")
