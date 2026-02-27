"""Handler for PollAnswer updates — tracks votes in real-time."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.database import delete_vote, register_member, save_vote

logger = logging.getLogger(__name__)


async def handle_poll_answer(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Process PollAnswer events from non-anonymous polls.

    - Auto-registers the voter as a member.
    - Saves the vote choice to DB.
    - Handles vote retraction (empty option_ids).
    """
    answer = update.poll_answer
    user = answer.user

    if user is None:
        return  # Anonymous voter chat — skip

    # Auto-register member on vote interaction
    await register_member(user.id, user.username, user.full_name)

    if not answer.option_ids:
        # User retracted their vote
        await delete_vote(answer.poll_id, user.id)
        logger.info("Vote retracted: user=%d poll=%s", user.id, answer.poll_id)
        return

    await save_vote(
        poll_id=answer.poll_id,
        user_id=user.id,
        option_id=answer.option_ids[0],
    )
    logger.info(
        "Vote recorded: user=%d poll=%s option=%d",
        user.id,
        answer.poll_id,
        answer.option_ids[0],
    )
