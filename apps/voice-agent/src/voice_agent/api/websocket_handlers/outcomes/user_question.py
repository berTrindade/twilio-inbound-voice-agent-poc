"""USER_QUESTION outcome strategy — big model answers, then owns the node."""

import logging

from ...session_context import SessionContext
from ...websocket_types import PromptHandlingResult, PromptEndMode
from ...websocket_helpers import send_and_log, sanitize_for_log
from ....voice_ai.predefined_responses import PredefinedResponses
from ....voice_ai.prompts import (
    build_big_model_user_prompt,
    build_big_escalation_system_prompt,
)
from .base import TurnContext
from .big_model_response import handle_big_model_response

logger = logging.getLogger(__name__)


async def handle_user_question(
    ctx: SessionContext, turn: TurnContext
) -> PromptHandlingResult:
    # Phase C: Capture the user question turn
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
                validation_result=None,
                escalated=True,
            )
        except Exception as e:
            logger.error(f"Error capturing user question turn: {e}", exc_info=True)

    try:
        snapshot = ctx.adapter.snapshot()
        big_prompt = build_big_model_user_prompt(
            node=turn.node,
            question_id=turn.node_id,
            answers=snapshot["answers"],
            user_text=turn.user_text,
            conversation_history=ctx.conversation_log[-10:],
        )
        big_resp = ctx.llm_handler.call_big_model(
            system_prompt=build_big_escalation_system_prompt(),
            user_prompt=big_prompt,
        )

        logger.debug(
            "Big model (user_question) response",
            extra={"big_resp": sanitize_for_log(big_resp)},
        )

        result = await handle_big_model_response(
            ctx=ctx,
            cur=turn.cur,
            big_model_resp=big_resp,
        )

        # Let the big model own this node until it records/advances or completes.
        if result.end_mode == PromptEndMode.CONTINUE:
            ctx.active_big_model_node = turn.node_id

        return PromptHandlingResult(
            end_mode=result.end_mode,
            active_big_model_node=ctx.active_big_model_node,
        )

    except Exception:
        logger.exception("Big model failed for user_question")

        if turn.reply:
            await send_and_log(
                ctx.websocket,
                turn.reply,
                last=False,
                conversation_log=ctx.conversation_log,
                metrics_collector=ctx.metrics_collector,
            )
        else:
            await send_and_log(
                ctx.websocket,
                PredefinedResponses.CLARIFY,
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
