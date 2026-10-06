"""HAPPY_PATH outcome strategy — valid answer, record and advance."""

import asyncio
import logging

from ...session_context import SessionContext
from ...websocket_types import PromptHandlingResult
from ...websocket_helpers import (
    send_and_log,
    speak_next_or_finish,
    _persist_coach_handoff,
    _persist_survey_completion,
    _emit_milestone_events,
    coalesce_whisper_text,
)
from ....config import settings
from ....voice_ai.conversation_trace import emit_survey_response_span
from ....voice_ai.predefined_responses import PredefinedResponses
from ....voice_ai.async_persistence import persist_question_async
from ....voice_ai.handoff_reasons import HandoffSource, reason_for_node
from .base import TurnContext
from ..handoff_initiation import initiate_coach_handoff

logger = logging.getLogger(__name__)


def _closing_text(nxt: dict) -> str:
    """The closing text spoken at natural completion, or GOODBYE if none."""
    parts = (nxt.get("spoken_intro") or "", nxt.get("question_prompt") or "")
    return " ".join(p for p in parts if p).strip() or PredefinedResponses.GOODBYE


async def handle_happy_path(
    ctx: SessionContext, turn: TurnContext
) -> PromptHandlingResult:
    # Phase C: Capture the successful turn before recording
    if ctx.call_state_manager:
        try:
            # Get the assistant's message that preceded this user response.
            # Note: This may be either:
            #   1. An LLM-generated clarification (if there was escalation)
            #   2. The original question prompt (first turn for this question)
            # In case 2, there's no real "confidence" for the system prompt,
            # but we record it as part of the conversation flow.
            assistant_msg = (
                ctx.conversation_log[-2]["text"]
                if len(ctx.conversation_log) >= 2
                else turn.cur["question_prompt"]
            )
            ctx.call_state_manager.add_turn(
                user_message=turn.combined_user_text,
                assistant_message=assistant_msg,
                llm_interpretation=turn.interpretation,
                llm_confidence=turn.small_conf,  # Confidence applies to interpretation, not assistant_msg
                validation_result=turn.val_res,
                escalated=False,
            )
        except Exception as e:
            logger.error(f"Error capturing turn: {e}", exc_info=True)

    try:
        ctx.adapter.record(turn.node_id, turn.val_res["normalized"])

        logger.debug("---------------- RECORDED VALUE ------------------")
        logger.debug(
            "Recorded value",
            extra={"normalized": turn.val_res["normalized"]},
        )
        logger.debug("--------------------------------------------------" + "\n" + "\n")
        logger.debug("---------------- ALL ANSWERS ------------------")
        logger.debug(
            "All answers",
            extra={"answers": ctx.adapter.engine.answers},
        )
        logger.debug("--------------------------------------------------" + "\n" + "\n")

        # Phase D: Complete question tracking and persist
        persist_task = None
        if ctx.call_state_manager:
            try:
                question_data = ctx.call_state_manager.complete_question(
                    turn.val_res["normalized"]
                )
                if question_data:
                    # Persist asynchronously
                    persist_task = asyncio.create_task(
                        persist_question_async(
                            ctx.call_state_manager.response_id, question_data
                        )
                    )
            except Exception as e:
                logger.error(f"Error completing question tracking: {e}", exc_info=True)

        nxt = ctx.adapter.advance()

        # Emit milestone events (fire-and-forget)
        await _emit_milestone_events(
            dispatcher=ctx.milestone_dispatcher,
            adapter=ctx.adapter,
            completed_node_id=turn.node_id,
            call_state_manager=ctx.call_state_manager,
            call_sid=ctx.call_sid,
            correlation_id=ctx.correlation_id,
        )

    except Exception:
        logger.exception("Record/advance failed")
        await send_and_log(
            ctx.websocket,
            PredefinedResponses.SAVE_ERROR,
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

    if nxt and nxt.get("handover_to_coach"):
        handover_text = (
            nxt.get("spoken_intro")
            or PredefinedResponses.COACH_HANDOVER_FALLBACK_MESSAGE
        )
        await send_and_log(
            ctx.websocket,
            handover_text,
            last=True,
            conversation_log=ctx.conversation_log,
            metrics_collector=ctx.metrics_collector,
            interruptible=nxt.get("interruptible"),
            preemptible=nxt.get("preemptible"),
        )

        if ctx.call_state_manager:
            if persist_task:
                await persist_task
            handover_ctx = nxt.get("handover_context")
            handover_node_id = handover_ctx.node_id if handover_ctx else "coach_handoff"
            await _persist_coach_handoff(
                ctx.call_state_manager,
                handover_text,
                handover_node_id,
                whisper_text=handover_ctx.whisper_text if handover_ctx else None,
            )

        if settings.coach_handoff_enabled:
            handover_ctx = nxt.get("handover_context")
            node_whisper = handover_ctx.whisper_text if handover_ctx else None
            # Reason comes from the handover NODE id (handover_ctx.node_id). The
            # engine nulls current_id when it reaches a handover node, so
            # nxt["node_id"] is "" here — using it would always yield SURVEY_ROUTED.
            handover_node_id = handover_ctx.node_id if handover_ctx else ""
            await initiate_coach_handoff(
                ctx,
                path="escalation",
                # the survey routed here based on the caller's answer, so the
                # handover node is the only thing that knows why
                trigger=reason_for_node(handover_node_id),
                handoff_source=HandoffSource.SURVEY,
                whisper_text=coalesce_whisper_text(node_whisper),
            )
            return PromptHandlingResult.coach_handoff_started(ctx.active_big_model_node)
        else:
            logger.info(
                "Coach handoff disabled via COACH_HANDOFF_ENABLED=false — skipping PSTN dial",
                extra={"call_sid": ctx.call_sid},
            )
            return PromptHandlingResult.continue_(None)

    if nxt:
        _survey_text = nxt.get("question_prompt") or nxt.get("spoken_intro") or ""
        if _survey_text:
            emit_survey_response_span(
                text=_survey_text,
                node_id=nxt.get("node_id", "") or "",
                call_sid=ctx.call_sid or "",
            )
        finished = await speak_next_or_finish(
            ctx.websocket,
            nxt,
            ctx.conversation_log,
            metrics_collector=ctx.metrics_collector,
        )
        if not finished:
            return PromptHandlingResult.continue_(ctx.active_big_model_node)

        if ctx.call_state_manager:
            if persist_task:
                await persist_task
            await _persist_survey_completion(ctx.call_state_manager, _closing_text(nxt))
        return PromptHandlingResult.survey_completed(ctx.active_big_model_node)

    return PromptHandlingResult.continue_(ctx.active_big_model_node)
