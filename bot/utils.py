"""Utility helpers for formatting and date calculations."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bot.config import TIMEZONE

TZ = ZoneInfo(TIMEZONE)


def get_week_label() -> str:
    """Get the date of next Monday (football day).

    Called on Friday for next week's poll.
    Returns format like 'Thứ 2, 03/03/2026'.
    """
    now = datetime.now(TZ)
    # Calculate next Monday from current date
    days_until_monday = (7 - now.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = now + timedelta(days=days_until_monday)
    return f"Thứ 2, {next_monday.strftime('%d/%m/%Y')}"


def format_mention_html(user_id: int, full_name: str) -> str:
    """Format a single user mention as HTML link."""
    return f'<a href="tg://user?id={user_id}">{full_name}</a>'


def format_mention_list(members: list[dict]) -> str:
    """Format list of members as HTML mentions, one per line."""
    lines = []
    for m in members:
        lines.append(f'• {format_mention_html(m["user_id"], m["full_name"])}')
    return "\n".join(lines)


def format_vote_list(
    week_label: str,
    voters_play: list[dict],
    voters_skip: list[dict],
    non_voters: list[dict],
) -> str:
    """Format the full vote status message for /list command."""
    parts = [f"📊 <b>Vote tuần {week_label}:</b>\n"]

    # Players
    parts.append(f"⚽ <b>Đá ({len(voters_play)}):</b>")
    if voters_play:
        for v in voters_play:
            parts.append(f"• {v['full_name']}")
    else:
        parts.append("• (chưa có)")

    # Skippers
    parts.append(f"\n❌ <b>Không đá ({len(voters_skip)}):</b>")
    if voters_skip:
        for v in voters_skip:
            parts.append(f"• {v['full_name']}")
    else:
        parts.append("• (chưa có)")

    # Non-voters
    parts.append(f"\n❓ <b>Chưa vote ({len(non_voters)}):</b>")
    if non_voters:
        for v in non_voters:
            parts.append(f"• {v['full_name']}")
    else:
        parts.append("• (tất cả đã vote)")

    return "\n".join(parts)


def format_inactive_list(inactive_members: list[dict]) -> str:
    """Format the inactive members list for /inactive command.

    Each member has: user_id, full_name, history [(week_label, status)]
    where status is 'no' (voted khong da), '-' (didn't vote), 'yes' (voted da).
    """
    if not inactive_members:
        return "✅ Không có ai vote 'Không đá' 3 tuần liên tiếp."

    parts = ["⚠️ <b>Vote \"Không đá\" 3 tuần liên tiếp:</b>\n"]
    for i, member in enumerate(inactive_members, 1):
        history_str = ", ".join(
            f"{wl}: {'❌' if s == 'no' else '✅' if s == 'yes' else '➖'}"
            for wl, s in member["history"]
        )
        parts.append(
            f"{i}. {format_mention_html(member['user_id'], member['full_name'])} "
            f"({history_str})"
        )

    parts.append('\n("❌" = vote không đá)')
    return "\n".join(parts)
