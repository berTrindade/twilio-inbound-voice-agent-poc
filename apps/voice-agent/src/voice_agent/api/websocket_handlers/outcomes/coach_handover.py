"""COACH_HANDOVER outcome strategy — use LLM coach handover text, then end survey."""

import logging
from typing import Optional

from ...session_context import SessionContext
from ...websocket_types import PromptHandlingResult
from ...websocket_helpers import (
    send_and_log,
    _persist_coach_handoff,
    coalesce_whisper_text,
)
from ....config import settings
from ....voice_ai.predefined_responses import PredefinedResponses
from ....voice_ai.handoff_reasons import reason_for_handover_request
from .base import TurnContext
from ..handoff_initiation import initiate_coach_handoff

logger = logging.getLogger(__name__)


async def handle_coach_handover(
    ctx: SessionContext,
    turn: TurnContext,
    *,
    trigger: Optional[str] = None,
    handoff_source: Optional[str] = None,
) -> PromptHandlingResult:
    # Two callers:
    #  - the signal-driven API-failure path passes an EXPLICIT
    #    trigger=system_error + handoff_source=system; respect it.
    #  - The normal LLM COACH_HANDOVER outcome passes neither, so we classify the
    #    sub-reason below from the model's handover_reason (see the trigger block).
    handover_text = turn.reply or PredefinedResponses.COACH_HANDOVER_FALLBACK_MESSAGE

    if ctx.call_state_manager:
        try:
            ctx.call_state_manager.add_turn(
                user_message=turn.combined_user_text,
                assistant_message=handover_text,
                llm_interpretation=turn.interpretation,
                llm_confidence=turn.small_conf,
                validation_result=None,
                escalated=False,
            )
        except Exception as e:
            logger.error(f"Error capturing coach handover turn: {e}", exc_info=True)
        await _persist_coach_handoff(
            ctx.call_state_manager,
            handover_text,
            whisper_text=turn.small_resp.get("whisper_text"),
        )

    await send_and_log(
        ctx.websocket,
        handover_text,
        last=True,
        conversation_log=ctx.conversation_log,
        metrics_collector=ctx.metrics_collector,
    )

    if not settings.coach_handoff_enabled:
        logger.info(
            "Coach handoff disabled via COACH_HANDOFF_ENABLED=false — skipping PSTN dial",
            extra={"call_sid": ctx.call_sid},
        )
        return PromptHandlingResult.continue_(ctx.active_big_model_node)

    # Build a brief, actionable whisper for the coach (played before bridging)
    whisper_from_small = turn.small_resp.get("whisper_text")

    if not whisper_from_small or not whisper_from_small.strip():
        logger.warning(
            "Small model missing whisper_text on coach handover; using fallback.",
            extra={"call_sid": ctx.call_sid},
        )

    whisper_text = coalesce_whisper_text(whisper_from_small)

    # For the LLM-driven handover (no explicit trigger from the caller), classify
    # the sub-reason from the model's handover_reason: the model lumps every coach
    # handover into one handover_to_coach action, and handover_reason disambiguates
    # a caller-initiated handoff (COACH_REQUESTED/CALLER) from the agent-inferred
    # ones. Missing/unknown -> agent decision. An explicit trigger (the
    # system-driven path) is preserved as-is.
    if trigger is None:
        trigger, handoff_source = reason_for_handover_request(
            turn.small_resp.get("handover_reason")
        )

    # Persist context, emit marker, and signal ConversationRelay to end
    await initiate_coach_handoff(
        ctx,
        path="escalation",
        trigger=trigger,
        handoff_source=handoff_source,
        whisper_text=whisper_text,
    )

    # Returning finished=True will cause the outer loop to end the survey
    return PromptHandlingResult.coach_handoff_started(ctx.active_big_model_node)
