"""Big model response handler — applies tool-style response from the big LLM."""

import asyncio
import logging
from typing import Any, Dict

from ...session_context import SessionContext
from ...websocket_types import PromptHandlingResult
from ...websocket_helpers import (
    send_and_log,
    speak_next_or_finish,
    _persist_coach_handoff,
    _emit_milestone_events,
    coalesce_whisper_text,
)
from ....config import settings
from ....voice_ai.conversation_trace import emit_survey_response_span
from ....voice_ai.predefined_responses import PredefinedResponses
from ....voice_ai.async_persistence import persist_question_async
from ....voice_ai.handoff_reasons import (
    HandoffSource,
    reason_for_handover_request,
    reason_for_node,
)
from ..handoff_initiation import initiate_coach_handoff

logger = logging.getLogger(__name__)


async def handle_big_model_response(
    ctx: SessionContext,
    cur: Dict[str, Any],
    big_model_resp: Dict[str, Any],
) -> PromptHandlingResult:
    """
    Apply the big model's tool-style response.

    Returns:
      PromptHandlingResult
    """
    action = big_model_resp.get("action", "say")

    if action == "record":
        try:
            qid = big_model_resp.get("question_id", cur["node_id"])
            raw_value = big_model_resp.get("value")

            # 1) Run deterministic validation on the big model's value (may be scalar or list for multi_choice)
            val_res = ctx.adapter.validate(qid, raw_value)
            logger.debug("Big model validation", extra={"val_res": val_res})

            if not val_res.get("valid"):
                logger.warning(
                    "Big model proposed invalid value",
                    extra={
                        "qid": qid,
                        "reason": val_res.get("reason"),
                        "big_model_raw_value": repr(raw_value),
                    },
                )
                # Fallback: treat like a failed attempt and stay on the same question
                await send_and_log(
                    ctx.websocket,
                    PredefinedResponses.RETRY_ON_TOOL_FAIL,
                    last=False,
                    conversation_log=ctx.conversation_log,
                    metrics_collector=ctx.metrics_collector,
                )
                await send_and_log(
                    ctx.websocket,
                    cur["question_prompt"],
                    last=True,
                    conversation_log=ctx.conversation_log,
                    metrics_collector=ctx.metrics_collector,
                    interruptible=cur.get("interruptible"),
                    preemptible=cur.get("preemptible"),
                )
                return PromptHandlingResult.continue_(None)
            else:
                # 2) Only record the normalized value
                ctx.adapter.record(qid, val_res["normalized"])

                logger.debug("---------------- RECORDED VALUE ------------------")
                logger.debug(
                    "Recorded value",
                    extra={"normalized": val_res["normalized"]},
                )
                logger.debug("--------------------------------------------------")
                logger.debug("---------------- ALL ANSWERS ------------------")
                logger.debug(
                    "All answers",
                    extra={"answers": ctx.adapter.engine.answers},
                )
                logger.debug(
                    "--------------------------------------------------" + "\n" + "\n"
                )

                # Phase D: Complete question tracking and persist (for big model path)
                persist_task = None
                if ctx.call_state_manager:
                    try:
                        question_data = ctx.call_state_manager.complete_question(
                            val_res["normalized"]
                        )
                        if question_data:
                            # Persist asynchronously
                            persist_task = asyncio.create_task(
                                persist_question_async(
                                    ctx.call_state_manager.response_id, question_data
                                )
                            )
                    except Exception as e:
                        logger.error(
                            f"Error completing question tracking (big model): {e}",
                            exc_info=True,
                        )

                nxt = ctx.adapter.advance()

                # Emit milestone events (fire-and-forget)
                await _emit_milestone_events(
                    dispatcher=ctx.milestone_dispatcher,
                    adapter=ctx.adapter,
                    completed_node_id=qid,
                    call_state_manager=ctx.call_state_manager,
                    call_sid=ctx.call_sid,
                    correlation_id=ctx.correlation_id,
                )

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

                    handover_ctx = nxt.get("handover_context")
                    raw_whisper = handover_ctx.whisper_text if handover_ctx else None

                    if ctx.call_state_manager:
                        if persist_task:
                            await persist_task
                        handover_node_id = (
                            handover_ctx.node_id if handover_ctx else "coach_handoff"
                        )
                        await _persist_coach_handoff(
                            ctx.call_state_manager,
                            handover_text,
                            handover_node_id,
                            whisper_text=raw_whisper,
                        )

                    if settings.coach_handoff_enabled:
                        await initiate_coach_handoff(
                            ctx,
                            path="escalation",
                            # survey-routed (the recorded answer advanced into a
                            # handover node) — same as the happy-path case. Reason
                            # comes from the handover NODE id; nxt["node_id"] is ""
                            # once the engine reaches a handover node.
                            trigger=reason_for_node(
                                (handover_ctx.node_id if handover_ctx else "") or ""
                            ),
                            handoff_source=HandoffSource.SURVEY,
                            whisper_text=coalesce_whisper_text(raw_whisper),
                        )
                        return PromptHandlingResult.coach_handoff_started(None)
                    else:
                        logger.info(
                            "Coach handoff disabled via COACH_HANDOFF_ENABLED=false — skipping PSTN dial",
                            extra={"call_sid": ctx.call_sid},
                        )
                        return PromptHandlingResult.continue_(None)

                _survey_text = (
                    nxt.get("question_prompt") or nxt.get("spoken_intro") or ""
                )
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
                return (
                    PromptHandlingResult.survey_completed(None)
                    if finished
                    else PromptHandlingResult.continue_(None)
                )

        except Exception:
            logger.exception("Tool record/advance failed")
            await send_and_log(
                ctx.websocket,
                PredefinedResponses.RETRY_ON_TOOL_FAIL,
                last=False,
                conversation_log=ctx.conversation_log,
                metrics_collector=ctx.metrics_collector,
            )
            await send_and_log(
                ctx.websocket,
                cur["question_prompt"],
                last=True,
                conversation_log=ctx.conversation_log,
                metrics_collector=ctx.metrics_collector,
                interruptible=cur.get("interruptible"),
                preemptible=cur.get("preemptible"),
            )
            return PromptHandlingResult.continue_(None)

    elif action == "say":
        # We ignore mode here for behaviour; it's useful for analytics later.
        spoken = big_model_resp.get("text")

        used_cur_prompt = False
        if not spoken:
            # Soft fallback to the current question prompt if text is missing
            if cur.get("question_prompt"):
                spoken = cur["question_prompt"]
                used_cur_prompt = True
            else:
                spoken = PredefinedResponses.CLARIFY

        await send_and_log(
            ctx.websocket,
            spoken,
            last=True,
            conversation_log=ctx.conversation_log,
            metrics_collector=ctx.metrics_collector,
            interruptible=cur.get("interruptible") if used_cur_prompt else None,
            preemptible=cur.get("preemptible") if used_cur_prompt else None,
        )
        return PromptHandlingResult.continue_(None)

    elif action == "complete":
        await send_and_log(
            ctx.websocket,
            big_model_resp.get("text") or PredefinedResponses.GOODBYE,
            last=True,
            conversation_log=ctx.conversation_log,
            metrics_collector=ctx.metrics_collector,
        )
        return PromptHandlingResult.user_ended_session(
            None
        )  # end session but no coach handoff required

    elif action == "handover_to_coach":
        # Big model has decided to hand off to a human coach
        spoken = (
            big_model_resp.get("text")
            or PredefinedResponses.COACH_HANDOVER_FALLBACK_MESSAGE
        )
        await send_and_log(
            ctx.websocket,
            spoken,
            last=True,
            conversation_log=ctx.conversation_log,
            metrics_collector=ctx.metrics_collector,
        )

        if ctx.call_state_manager:
            try:
                ctx.call_state_manager.add_turn(
                    user_message="",
                    assistant_message=spoken,
                    llm_interpretation="coach_handoff",
                    llm_confidence=None,
                    validation_result=None,
                    escalated=False,
                )
            except Exception as e:
                logger.error(
                    f"Error capturing big model handover turn: {e}", exc_info=True
                )
            await _persist_coach_handoff(
                ctx.call_state_manager,
                spoken,
                whisper_text=big_model_resp.get("whisper_text"),
            )

        # 2) PSTN handoff
        if settings.coach_handoff_enabled:
            whisper_from_model = big_model_resp.get("whisper_text")

            if not whisper_from_model or not whisper_from_model.strip():
                logger.warning(
                    "Big model handover did not return whisper_text; using default fallback.",
                    extra={"call_sid": ctx.call_sid},
                )

            whisper_text = coalesce_whisper_text(whisper_from_model)

            # Like the small interpreter, the big model lumps an explicit "I want
            # a human" request together with inferred frustration under one
            # handover action; its handover_reason disambiguates them so the
            # funnel can tell a caller-initiated handoff (COACH_REQUESTED/CALLER)
            # from an agent-inferred one. Missing -> agent decision.
            trigger, handoff_source = reason_for_handover_request(
                big_model_resp.get("handover_reason")
            )

            await initiate_coach_handoff(
                ctx,
                path="escalation",
                trigger=trigger,
                handoff_source=handoff_source,
                whisper_text=whisper_text,
            )
            return PromptHandlingResult.coach_handoff_started(None)
        else:
            logger.info(
                "Coach handoff disabled via COACH_HANDOFF_ENABLED=false — skipping PSTN dial",
                extra={"call_sid": ctx.call_sid},
            )
            return PromptHandlingResult.continue_(None)

    # Unknown action – soft fallback. The big model's own exception handler
    # returns action="clarify", which is not in the vocabulary above, so this
    # is the branch every big-model failure lands in. Prefer the text it set
    # (TRY_AGAIN_AFTER_LLM_EXCEPTION) over the generic line.
    await send_and_log(
        ctx.websocket,
        big_model_resp.get("text") or PredefinedResponses.TRY_AGAIN,
        last=False,
        conversation_log=ctx.conversation_log,
        metrics_collector=ctx.metrics_collector,
    )
    await send_and_log(
        ctx.websocket,
        cur["question_prompt"],
        last=True,
        conversation_log=ctx.conversation_log,
        metrics_collector=ctx.metrics_collector,
        interruptible=cur.get("interruptible"),
        preemptible=cur.get("preemptible"),
    )
    return PromptHandlingResult.continue_(None)
