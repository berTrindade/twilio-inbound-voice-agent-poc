"""INVALID_RETRY outcome strategy — small model can still recover."""

import logging

from ...session_context import SessionContext
from ...websocket_types import PromptHandlingResult
from ...websocket_helpers import send_and_log
from ....voice_ai.predefined_responses import PredefinedResponses
from .base import TurnContext

logger = logging.getLogger(__name__)


async def handle_invalid_retry(
    ctx: SessionContext, turn: TurnContext
) -> PromptHandlingResult:
    # Phase C: Capture the invalid turn
    if ctx.call_state_manager:
        try:
            assistant_msg = (
                ctx.conversation_log[-2]["text"]
                if len(ctx.conversation_log) >= 2
                else turn.cur["question_prompt"]
            )
            ctx.call_state_manager.add_turn(
                user_message=turn.combined_user_text,
                assistant_message=assistant_msg,
                llm_interpretation=turn.interpretation,
                llm_confidence=turn.small_conf,
                validation_result=turn.val_res,
                escalated=False,
            )
        except Exception as e:
            logger.error(f"Error capturing invalid turn: {e}", exc_info=True)

    if turn.reply:
        # LLM provided a clarification. Treat it as a full, self-contained text to read to the user.
        await send_and_log(
            ctx.websocket,
            turn.reply,
            last=True,
            conversation_log=ctx.conversation_log,
            metrics_collector=ctx.metrics_collector,
        )
    else:
        # No LLM clarification text – use generic invalid message + re-ask question.
        await send_and_log(
            ctx.websocket,
            PredefinedResponses.INVALID_OPTION,
            last=False,
            conversation_log=ctx.conversation_log,
            metrics_collector=ctx.metrics_collector,
        )

        await send_and_log(
            ctx.websocket,
            turn.cur["question_prompt"],
            last=True,
            conversation_log=ctx.conversation_log,
            metrics_collector=ctx.metrics_collector,
            interruptible=turn.cur.get("interruptible"),
            preemptible=turn.cur.get("preemptible"),
        )
    return PromptHandlingResult.continue_(ctx.active_big_model_node)
