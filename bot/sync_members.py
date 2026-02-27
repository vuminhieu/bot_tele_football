"""Sync group members from Telegram using Pyrogram MTProto.

Uses Pyrogram with bot token + raw MTProto API to enumerate all group members
— something the Bot API cannot do.

Called on startup and on a daily schedule to keep the members table current.

NOTE: Pyrogram is imported lazily inside functions to avoid a Python 3.14
compatibility issue where `asyncio.get_event_loop()` fails at import time.

NOTE: Uses raw MTProto `GetParticipants` instead of the high-level
`get_chat_members()` to work around a Pyrogram 2.0.x bug where channel IDs
exceeding int32 (>2147483647) are rejected by `resolve_peer()`.
"""

import logging

from bot.config import API_HASH, API_ID, BOT_TOKEN, CHAT_ID
from bot.database import register_member

logger = logging.getLogger(__name__)

# Pyrogram session name (stored as data/pyrogram_bot.session)
_SESSION_NAME = "data/pyrogram_bot"


def _bot_api_id_to_channel_id(chat_id: int) -> int:
    """Convert Bot API supergroup ID (-100XXXX) to raw MTProto channel ID."""
    return abs(chat_id) - 1000000000000


async def sync_group_members() -> int:
    """Fetch all members from the configured group and upsert into DB.

    Uses raw MTProto GetParticipants to bypass Pyrogram's resolve_peer bug.

    Returns:
        Number of members synced (excluding bots).
    """
    # Lazy imports for Python 3.14 compat
    from pyrogram import Client  # noqa: PLC0415
    from pyrogram.raw.functions.channels import GetParticipants  # noqa: PLC0415
    from pyrogram.raw.types import (  # noqa: PLC0415
        ChannelParticipantsRecent,
        InputChannel,
    )

    channel_id = _bot_api_id_to_channel_id(CHAT_ID)
    synced = 0

    async with Client(
        name=_SESSION_NAME,
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        no_updates=True,
    ) as app:
        logger.info(
            "Fetching members from channel %d (bot API: %d) via raw MTProto...",
            channel_id, CHAT_ID,
        )

        # Bots that are members of the channel can use access_hash=0
        input_channel = InputChannel(channel_id=channel_id, access_hash=0)
        offset = 0
        limit = 200  # Telegram returns max 200 per request

        while True:
            result = await app.invoke(
                GetParticipants(
                    channel=input_channel,
                    filter=ChannelParticipantsRecent(),
                    offset=offset,
                    limit=limit,
                    hash=0,
                )
            )

            if not result.participants:
                break

            # Build user lookup from the users list returned by Telegram
            users_map = {u.id: u for u in result.users}

            for participant in result.participants:
                user = users_map.get(participant.user_id)
                if not user:
                    continue

                # Skip bots and deleted accounts
                if user.bot or user.deleted:
                    continue

                full_name = " ".join(
                    part for part in [user.first_name, user.last_name] if part
                )
                if not full_name:
                    full_name = user.username or f"User_{user.id}"

                await register_member(user.id, user.username, full_name)
                synced += 1

            # If we got fewer than limit, we've fetched everyone
            if len(result.participants) < limit:
                break
            offset += limit

    logger.info("Synced %d members from group.", synced)
    return synced
