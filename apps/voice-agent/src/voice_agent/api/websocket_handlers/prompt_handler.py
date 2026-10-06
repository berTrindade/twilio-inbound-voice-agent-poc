"""Handler for Twilio 'prompt' messages (user utterances from STT)."""

import logging
import asyncio
from typing import Any, Dict

from ...config import settings
from ...voice_ai.conversation_trace import (
    start_conversation_turn_span,
    emit_user_message_span,
)
from ...voice_ai.prompts import (
    build_small_interpreter_system_prompt,
    build_big_escalation_system_prompt,
    build_small_model_user_prompt,
    build_big_model_user_prompt,
)
from ...voice_ai.predefined_responses import PredefinedResponses
from ..session_context import SessionContext
from ..websocket_helpers import sanitize_for_log, send_and_log
from ..websocket_types import PromptHandlingResult, PromptEndMode
from .outcomes import (
    OUTCOME_STRATEGIES,
    classify_prompt_outcome,
)
from .outcomes.base import TurnContext
from .outcomes.big_model_response import handle_big_model_response
from ...voice_ai.pending_handoff_state import pop_pending_handoff
from ...voice_ai.handoff_reasons import HandoffSource
from .outcomes.coach_handover import handle_coach_handover

logger = logging.getLogger(__name__)


async def handle_prompt_message(
    ctx: SessionContext,
    msg: Dict[str, Any],
    msg_span,
) -> PromptHandlingResult:
    """
    Handle a Twilio 'prompt' message (user utterance from STT).

    Ownership rules:
      - By default, the SMALL model interprets user input for each node.
      - When we escalate a node to the BIG model (non-FAQ path), that node
        becomes "owned" by the big model:
          * Follow-up utterances for that node bypass the small model.
          * Big model sees full conversation history and controls the turn.
      - Ownership ends when:
          * Big model successfully records and advances, or
          * Big model completes the survey, or
          * The session ends.

    Returns:
        PromptHandlingResult
    """
    user_text = msg.get("voicePrompt", "") or ""
    if not user_text:
        logger.info("No transcript returned from STT")
    last = bool(msg.get("last", True))

    logger.debug("=" * 32 + " USER PROMPT " + "=" * 32)
    logger.debug(
        "User prompt received",
        extra={"user_text": sanitize_for_log(user_text), "last": last},
    )
    logger.debug("=" * 77 + "\n" + "\n")

    msg_span.set_attribute("action", "prompt")
    msg_span.set_attribute("voice_prompt_length", len(user_text or ""))

    if not last:
        # Still partial STT — ignore until final segment.
        return PromptHandlingResult.continue_(ctx.active_big_model_node)

    # a background submission recorded a blocking failure for this call.
    # Consume the signal here (after the final STT segment, before normal routing)
    # and route to the existing coach-handoff outcome on this utterance.
    pending = pop_pending_handoff(ctx.call_sid)
    if pending is not None:
        # Observability-only branch: handle_coach_handover already checks
        # coach_handoff_enabled and (when disabled) still speaks the message then
        # returns continue_. This ERROR log does NOT alter control flow — it ensures
        # a blocking failure that cannot be dialed is never silently swallowed.
        if not settings.coach_handoff_enabled:
            logger.error(
                "Blocking API failure but coach handoff disabled — caller continues without escalation",
                extra={"call_sid": ctx.call_sid, "reason": pending.reason},
            )
        # Note: we intentionally skip ctx.conversation_log.append for this utterance —
        # handle_coach_handover captures the turn via call_state_manager.add_turn and the
        # call ends immediately, so LLM history is irrelevant past this point.
        handoff_turn = TurnContext(
            cur={},
            node={},
            node_id="",
            combined_user_text=user_text,
            user_text=user_text,
            interpretation="other",
            reply=PredefinedResponses.COACH_HANDOVER_FAILURE_MESSAGE,
            small_conf=0.0,
            val_res={},
            small_resp={"whisper_text": pending.whisper_text},
        )
        logger.info(
            "Routing to coach handoff from pending signal",
            extra={"call_sid": ctx.call_sid, "reason": pending.reason},
        )
        # This early return bypasses normal outcome routing (small/big model,
        # _route_small_model_result, happy_path, and any engine handover_to_coach
        # node) — so there is exactly one handoff trigger this turn and no double send_end.
        # Attribute the marker to the API failure (system-driven), not a caller request.
        return await handle_coach_handover(
            ctx,
            handoff_turn,
            trigger=pending.trigger,
            handoff_source=HandoffSource.SYSTEM,
        )

    # Track the current question early so the active turn can be persisted correctly.
    cur = ctx.adapter.current()
    node_id = cur.get("node_id")
    if ctx.call_state_manager and node_id and not cur.get("finished"):
        try:
            current_question_id = ctx.call_state_manager.get_current_question_id()
            if current_question_id != node_id:
                question_text = cur.get("question_prompt", "")
                node = ctx.adapter.engine.get_node(node_id) or {}
                node_type = node.get("type", "unknown")
                ctx.call_state_manager.start_question(node_id, question_text, node_type)
        except Exception as e:
            logger.error(f"Error starting question tracking: {e}", exc_info=True)

    # Log *this* user turn as-is (without merging utterences)
    ctx.conversation_log.append({"role": "user", "text": user_text})

    with start_conversation_turn_span(
        call_sid=ctx.call_sid or "",
        session_id=ctx.session_id or "",
        correlation_id=ctx.correlation_id or "",
        conversation_history=list(ctx.conversation_log),
    ):
        # node_id from the pre-append lookup (cur.get) — may be None if
        # cur["finished"] is True; the early-return below handles that case.
        # We pass it as-is (empty string fallback) because the re-assignment to
        # cur["node_id"] happens only after the finished-check below.
        emit_user_message_span(
            text=user_text,
            node_id=node_id or "",
            call_sid=ctx.call_sid or "",
        )

        # Refresh cur/node_id/node — they were set before language detection but
        # the adapter state hasn't changed so these are still valid.
        if cur["finished"] or not cur["node_id"]:
            await send_and_log(
                ctx.websocket,
                PredefinedResponses.ALREADY_DONE,
                last=True,
                conversation_log=ctx.conversation_log,
                metrics_collector=ctx.metrics_collector,
            )
            return PromptHandlingResult.already_terminal(ctx.active_big_model_node)

        node_id = cur["node_id"]
        node = ctx.adapter.engine.get_node(node_id) or {}

        # merge this utterance into the per-question buffer
        combined_user_text = ctx.adapter.merge_user_utterance(node_id, user_text)

        logger.debug(
            "Buffered user text for node",
            extra={
                "node_id": sanitize_for_log(node_id),
                "combined_user_text": sanitize_for_log(combined_user_text),
            },
        )

        # ------------------------------------------------------------------
        # CASE 0: This node is currently "owned" by the big model.
        #         Bypass the small interpreter and send directly to big model.
        # ------------------------------------------------------------------
        if ctx.active_big_model_node and ctx.active_big_model_node == node_id:
            if ctx.call_state_manager:
                try:
                    assistant_msg = (
                        ctx.conversation_log[-2]["text"]
                        if len(ctx.conversation_log) >= 2
                        else cur["question_prompt"]
                    )
                    ctx.call_state_manager.add_turn(
                        user_message=combined_user_text,
                        assistant_message=assistant_msg,
                        llm_interpretation="big_model_ownership",
                        llm_confidence=None,
                        validation_result=None,
                        escalated=True,
                    )
                except Exception as e:
                    logger.error(
                        f"Error capturing ownership mode turn: {e}", exc_info=True
                    )

            try:
                ctx.turn_seq += 1
                turn_seq = ctx.turn_seq

                snapshot = ctx.adapter.snapshot()
                big_prompt = build_big_model_user_prompt(
                    node=node,
                    question_id=node_id,
                    answers=snapshot["answers"],
                    user_text=user_text,
                    conversation_history=ctx.conversation_log[-10:],
                )

                big_task = asyncio.create_task(
                    ctx.llm_handler.call_big_model_async(
                        system_prompt=build_big_escalation_system_prompt(),
                        user_prompt=big_prompt,
                        **ctx.llm_call_kwargs(),
                    )
                )

                big_resp = await big_task
                logger.debug(
                    "Big model (ownership mode) response",
                    extra={"big_resp": sanitize_for_log(big_resp)},
                )

                # Drop stale async results if a newer turn has already started
                if turn_seq != ctx.turn_seq:
                    return PromptHandlingResult.continue_(ctx.active_big_model_node)

                action = big_resp.get("action", "say")
                result = await handle_big_model_response(
                    ctx=ctx,
                    cur=cur,
                    big_model_resp=big_resp,
                )

                if (
                    action in ("record", "complete")
                    or result.end_mode != PromptEndMode.CONTINUE
                ):
                    ctx.active_big_model_node = None

                return PromptHandlingResult(
                    end_mode=result.end_mode,
                    active_big_model_node=ctx.active_big_model_node,
                )

            except Exception:
                logger.exception("Big model failed in ownership mode")

                await send_and_log(
                    ctx.websocket,
                    PredefinedResponses.CLARIFY,
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
                return PromptHandlingResult.continue_(ctx.active_big_model_node)

        # ------------------------------------------------------------------
        # CASE 1: No owner → normal flow with SMALL model interpreter.
        # ------------------------------------------------------------------
        snapshot = ctx.adapter.snapshot()

        small_prompt = build_small_model_user_prompt(
            node,
            combined_user_text,
            answers=snapshot.get("answers") or {},
            conversation_history=ctx.conversation_log[-5:],
        )

        ctx.turn_seq += 1
        turn_seq = ctx.turn_seq

        small_resp = await ctx.llm_handler.call_small_model_async(
            system_prompt=build_small_interpreter_system_prompt(),
            user_prompt=small_prompt,
            **ctx.llm_call_kwargs(),
        )

        logger.debug(
            "Small model response",
            extra={"small_resp": sanitize_for_log(small_resp)},
        )

        # If a newer turn started while we were waiting, ignore this result
        if turn_seq != ctx.turn_seq:
            return PromptHandlingResult.continue_(ctx.active_big_model_node)

        return await _route_small_model_result(
            ctx=ctx,
            cur=cur,
            node=node,
            node_id=node_id,
            combined_user_text=combined_user_text,
            user_text=user_text,
            small_resp=small_resp,
        )


async def _route_small_model_result(
    ctx: SessionContext,
    cur: Dict[str, Any],
    node: Dict[str, Any],
    node_id: str,
    combined_user_text: str,
    user_text: str,
    small_resp: Dict[str, Any],
) -> PromptHandlingResult:

    interpretation = small_resp.get("interpretation", "other")
    reply = small_resp.get("reply")
    answer = small_resp.get("answer")
    small_conf = float(small_resp.get("confidence", 0.0))

    # Run deterministic validation
    val_res: Dict[str, Any] = {"valid": False, "normalized": None, "reason": ""}
    try:
        if interpretation in {"answer", "other"} and isinstance(answer, dict):
            val_res = ctx.adapter.validate(node_id, answer.get("value"))
    except Exception:
        logger.exception("Validation error")

    logger.debug("Validation result", extra={"val_res": val_res})

    try:
        escalate = ctx.adapter.should_escalate(
            user_text=combined_user_text,
            llm_conf=small_conf,
            is_valid=bool(val_res.get("valid")),
        )
    except Exception:
        logger.exception("Escalation decision failed")
        escalate = False

    logger.info("Escalate? %s", escalate)

    guardrail_topic = small_resp.get("guardrail_topic", "none")

    outcome = classify_prompt_outcome(
        interpretation=interpretation,
        val_res=val_res,
        escalate=escalate,
        guardrail_topic=guardrail_topic,
    )

    turn = TurnContext(
        cur=cur,
        node=node,
        node_id=node_id,
        combined_user_text=combined_user_text,
        user_text=user_text,
        interpretation=interpretation,
        reply=reply,
        small_conf=small_conf,
        val_res=val_res,
        small_resp=small_resp,
    )
    return await OUTCOME_STRATEGIES[outcome](ctx, turn)
