"""PREDEFINED_GUARDRAIL outcome strategy — speak canned guardrail response and continue."""

import logging

from ...session_context import SessionContext
from ...websocket_types import PromptHandlingResult
from ...websocket_helpers import send_and_log
from ....voice_ai.predefined_responses import PredefinedResponses
from ....voice_ai.guardrails.guardrails_response_manager import get_guardrail_response
from .base import TurnContext

logger = logging.getLogger(__name__)


async def handle_guardrail_topic(
    ctx: SessionContext,
    turn: TurnContext,
) -> PromptHandlingResult:
    topic = turn.small_resp.get("guardrail_topic")

    if not topic or topic == "none":
        logger.warning(
            "PREDEFINED_GUARDRAIL outcome invoked without a valid guardrail_topic",
            extra={"guardrail_topic": topic, "call_sid": ctx.call_sid},
        )
        spoken = PredefinedResponses.TRY_AGAIN
    else:
        spoken = get_guardrail_response(topic_name=topic)

    await send_and_log(
        ctx.websocket,
        spoken,
        last=True,
        conversation_log=ctx.conversation_log,
        metrics_collector=ctx.metrics_collector,
    )

    return PromptHandlingResult.continue_(ctx.active_big_model_node)
