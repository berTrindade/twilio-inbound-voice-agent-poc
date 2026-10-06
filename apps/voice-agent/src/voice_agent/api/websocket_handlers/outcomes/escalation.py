"""ESCALATE outcome strategy — big model tool path, ownership may start here."""

import logging

from ...session_context import SessionContext
from ...websocket_types import PromptHandlingResult, PromptEndMode
from ...websocket_helpers import sanitize_for_log
from ....voice_ai.prompts import (
    build_big_model_user_prompt,
    build_big_escalation_system_prompt,
)
from .base import TurnContext
from .big_model_response import handle_big_model_response

logger = logging.getLogger(__name__)


async def handle_escalation(
    ctx: SessionContext, turn: TurnContext
) -> PromptHandlingResult:
    # Phase C: Capture the escalated turn
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
                escalated=True,
            )
        except Exception as e:
            logger.error(f"Error capturing escalation turn: {e}", exc_info=True)

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
        "Big model tool response",
        extra={"big_resp": sanitize_for_log(big_resp)},
    )

    action = big_resp.get("action", "say")
    result = await handle_big_model_response(
        ctx=ctx,
        cur=turn.cur,
        big_model_resp=big_resp,
    )

    # Start or end ownership based on action.
    if action == "say" and result.end_mode == PromptEndMode.CONTINUE:
        ctx.active_big_model_node = turn.node_id
    elif action in ("record", "complete") or result.end_mode != PromptEndMode.CONTINUE:
        ctx.active_big_model_node = None

    return PromptHandlingResult(
        end_mode=result.end_mode,
        active_big_model_node=ctx.active_big_model_node,
    )
