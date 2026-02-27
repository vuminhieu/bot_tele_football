"""Command handlers for the football vote bot.

Commands:
  /list, /ds — Show current poll vote status
  /inactive, /vang — Show 3-consecutive skip voters
  /getallmember — List all registered members in the group
  /help — Show all available commands
  /testpoll — (Dev) Manually trigger poll creation
  /testreminder — (Dev) Manually trigger vote reminder
  /testclose — (Dev) Manually trigger poll close
"""

import logging
import html
from telegram import Update
from telegram.ext import ContextTypes

from bot.config import ADMIN_USERNAMES, CHAT_ID
from bot.database import (
    deactivate_member,
    get_active_members,
    get_consecutive_inactive,
    get_current_poll,
    get_non_voters,
    get_voters_by_option,
    register_member,
)
from bot.scheduler.jobs import close_weekly_poll, create_weekly_poll, send_vote_reminder
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
# ChatMember handler (join/leave tracking)
# ---------------------------------------------------------------------------


async def handle_chat_member_update(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Track members joining or leaving the group in real-time.

    Triggered by ChatMemberHandler.CHAT_MEMBER updates.
    """
    member = update.chat_member
    if not member:
        return

    new = member.new_chat_member
    user = new.user

    if user.is_bot:
        return

    # Member joined or was added
    if new.status in ("member", "administrator", "creator"):
        full_name = user.full_name or user.username or f"User_{user.id}"
        await register_member(user.id, user.username, full_name)
        logger.info("Member joined/added: %s (%d)", full_name, user.id)

    # Member left or was kicked — mark inactive
    elif new.status in ("left", "kicked"):
        await deactivate_member(user.id)
        logger.info("Member left/kicked: %s (%d)", user.full_name, user.id)

# ---------------------------------------------------------------------------
# Admin guard
# ---------------------------------------------------------------------------


def _is_admin(update: Update) -> bool:
    """Check if the command sender is in the admin list."""
    user = update.effective_user
    return user is not None and user.username in ADMIN_USERNAMES


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
async def cmd_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show current poll vote status: who voted Đá / Không đá / Chưa vote."""
    if not _is_admin(update):
        return

    poll = await get_current_poll()
    if not poll:
        await update.effective_message.reply_text("📭 Chưa có vote nào đang mở.")
        return

    voters_play = await get_voters_by_option(poll["poll_id"], 0)
    voters_skip = await get_voters_by_option(poll["poll_id"], 1)
    non_voters = await get_non_voters(poll["poll_id"])

    text = format_vote_list(
        poll["week_label"], voters_play, voters_skip, non_voters
    )
    await update.effective_message.reply_text(text, parse_mode="HTML")


async def cmd_getallmember(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """List all registered (active) members in the group."""
    if not _is_admin(update):
        return

    members = await get_active_members()
    if not members:
        await update.effective_message.reply_text("📭 Chưa có thành viên nào được đăng ký.")
        return

    lines = [f"👥 <b>Danh sách thành viên ({len(members)}):</b>\n"]
    for i, m in enumerate(members, 1):
        name = html.escape(m["full_name"], quote=False)
        username = f' (@{m["username"]})' if m.get("username") else ""
        lines.append(f"{i}. {name}{username}")

    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_inactive(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show members who voted 'Không đá' 3 consecutive times."""
    if not _is_admin(update):
        return

    inactive = await get_consecutive_inactive(n=3)
    text = format_inactive_list(inactive)
    await update.effective_message.reply_text(text, parse_mode="HTML")


async def cmd_help(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show all available bot commands."""
    if not _is_admin(update):
        return

    text = (
        "📋 <b>Danh sách lệnh:</b>\n\n"
        "/list - Xem danh sách vote hiện tại\n"
        "/inactive - Xem người 3 tuần liên tiếp vote không đá\n"
        "/getallmember - Xem toàn bộ thành viên trong nhóm\n"
        "/help - Hiển thị trợ giúp\n\n"
        "<i>Bot tự động tạo vote thứ 6 8:30 sáng, "
        "nhắc thứ 2 8:30 sáng, đóng thứ 2 12:00 trưa.\n"
        "Thành viên được tự động đồng bộ từ nhóm.</i>"
    )
    await update.effective_message.reply_text(text, parse_mode="HTML")


async def cmd_testpoll(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Dev command: manually trigger poll creation for testing.

    Can be sent from any chat — the poll is created in the configured group.
    """
    if not _is_admin(update):
        return

    await create_weekly_poll(context)
    await update.effective_message.reply_text("🧪 Test poll created.")


async def cmd_testreminder(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Dev command: manually trigger vote reminder for testing."""
    if not _is_admin(update):
        return

    await send_vote_reminder(context)
    await update.effective_message.reply_text("🧪 Test reminder sent.")


async def cmd_testclose(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Dev command: manually trigger poll close for testing."""
    if not _is_admin(update):
        return

    await close_weekly_poll(context)
    await update.effective_message.reply_text("🧪 Test close done.")
