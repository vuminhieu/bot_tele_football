"""Sync group members from Telegram using Pyrogram MTProto.

Uses Pyrogram with bot token + raw MTProto API to enumerate all group members
— something the Bot API cannot do.

Called on startup and on a daily schedule to keep the members table current.

NOTE: Pyrogram is imported lazily inside functions to avoid a Python 3.14
compatibility issue where `asyncio.get_event_loop()` fails at import time.

Strategy:
  1. Warm up Pyrogram's peer cache via `get_chat()` (resolves access_hash)
  2. Use high-level `get_chat_members()` which handles pagination internally
  3. Fall back to raw MTProto `GetParticipants` only if high-level API fails
"""

import logging

# Pyrogram 2.0.106 bug: MIN_CHANNEL_ID is capped at -1002147483647 (32-bit limit)
# but Telegram now creates channels with IDs beyond that. Monkey-patch the constant
# so resolve_peer() / get_chat() / get_chat_members() work with newer channel IDs.
import pyrogram.utils  # noqa: E402
pyrogram.utils.MIN_CHANNEL_ID = -1009999999999

from bot.config import API_HASH, API_ID, BOT_TOKEN, CHAT_ID
from bot.database import register_member

logger = logging.getLogger(__name__)

# In-memory session — bot token re-authenticates each time,
# no need to persist session file (avoids SQLite permission issues in Docker)
_SESSION_NAME = "football_vote_bot"


async def sync_group_members() -> int:
    """Fetch all members from the configured group and upsert into DB.

    Uses Pyrogram's high-level `get_chat_members()` which handles peer
    resolution and pagination internally. Falls back to raw MTProto
    `GetParticipants` if the high-level API fails.

    Returns:
        Number of members synced (excluding bots).
    """
    # Lazy imports for Python 3.14 compat
    from pyrogram import Client  # noqa: PLC0415

    seen_user_ids: set[int] = set()

    async with Client(
        name=_SESSION_NAME,
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        in_memory=True,
        no_updates=True,
    ) as app:
        # Step 1: Warm up peer cache — this makes Pyrogram learn the
        # channel's access_hash so all subsequent calls work correctly.
        try:
            chat = await app.get_chat(CHAT_ID)
            logger.info(
                "Resolved chat: '%s' (id=%d, type=%s)",
                chat.title, chat.id, chat.type,
            )
        except Exception:
            logger.exception(
                "Failed to resolve chat %d. Bot may not be a member of the group. "
                "Aborting sync.",
                CHAT_ID,
            )
            return 0

        # Step 2: Fetch members using high-level API
        try:
            count = await _sync_via_high_level_api(app, seen_user_ids)
            if count > 0:
                logger.info("Synced %d members via high-level API.", count)
                return count
            logger.warning("High-level API returned 0 members, trying raw MTProto...")
        except Exception:
            logger.warning(
                "High-level get_chat_members failed, falling back to raw MTProto.",
                exc_info=True,
            )

        # Step 3: Fallback — raw MTProto GetParticipants
        try:
            count = await _sync_via_raw_mtproto(app, seen_user_ids)
            logger.info("Synced %d members via raw MTProto.", count)
            return count
        except Exception:
            logger.exception("Raw MTProto sync also failed.")
            return len(seen_user_ids)


async def _sync_via_high_level_api(app, seen_user_ids: set[int]) -> int:
    """Sync using Pyrogram's high-level get_chat_members (handles pagination)."""

    async for member in app.get_chat_members(CHAT_ID):
        user = member.user

        # Skip bots and deleted accounts
        if user.is_bot or user.is_deleted:
            continue
        if user.id in seen_user_ids:
            continue

        full_name = _build_full_name(user)
        await register_member(user.id, user.username, full_name)
        seen_user_ids.add(user.id)

    return len(seen_user_ids)


async def _sync_via_raw_mtproto(app, seen_user_ids: set[int]) -> int:
    """Fallback: sync using raw MTProto GetParticipants with multiple filters."""
    from pyrogram.raw.functions.channels import GetParticipants  # noqa: PLC0415
    from pyrogram.raw.types import (  # noqa: PLC0415
        ChannelParticipantsRecent,
        ChannelParticipantsSearch,
    )

    # resolve_peer should work now because get_chat() already warmed the cache
    peer = await app.resolve_peer(CHAT_ID)

    async def _fetch(fltr, label: str) -> bool:
        """Paginate GetParticipants. Returns False if first page fails (early abort)."""
        offset = 0
        limit = 200
        first_page = True

        while True:
            try:
                result = await app.invoke(
                    GetParticipants(
                        channel=peer,
                        filter=fltr,
                        offset=offset,
                        limit=limit,
                        hash=0,
                    )
                )
            except Exception:
                logger.warning(
                    "GetParticipants failed for filter=%s", label,
                    exc_info=True,
                )
                return not first_page  # False if first page = abort all

            first_page = False

            if not result.participants:
                break

            users_map = {u.id: u for u in result.users}

            for participant in result.participants:
                user = users_map.get(participant.user_id)
                if not user:
                    continue
                if user.bot or user.deleted:
                    continue
                if user.id in seen_user_ids:
                    continue

                full_name = " ".join(
                    part for part in [user.first_name, user.last_name] if part
                )
                if not full_name:
                    full_name = user.username or f"User_{user.id}"

                await register_member(user.id, user.username, full_name)
                seen_user_ids.add(user.id)

            if len(result.participants) < limit:
                break
            offset += limit

        return True

    # Strategy 1: Recent participants
    success = await _fetch(ChannelParticipantsRecent(), "Recent")

    # Strategy 2: Search by letter (only if Recent worked)
    if success:
        import string  # noqa: PLC0415
        for letter in string.ascii_lowercase:
            await _fetch(
                ChannelParticipantsSearch(q=letter), f"Search({letter})"
            )

    return len(seen_user_ids)


def _build_full_name(user) -> str:
    """Build display name from a Pyrogram User object."""
    if user.first_name:
        parts = [user.first_name]
        if user.last_name:
            parts.append(user.last_name)
        return " ".join(parts)
    return user.username or f"User_{user.id}"
