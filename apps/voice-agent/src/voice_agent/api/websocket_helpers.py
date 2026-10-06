"""Shared helper functions for the WebSocket ConversationRelay endpoint."""

import asyncio
import logging
from typing import Any, Dict, List, Optional
import re

from fastapi import WebSocket

from ..config import settings
from ..voice_ai.async_persistence import persist_question_async
from ..voice_ai.backend_adapter import SurveyBackendAdapter
from ..voice_ai.call_state_manager import CallStateManager
from ..voice_ai.handoff_reasons import (
    DEFAULT_HANDOFF_WHISPER,
    COMPLETED_SURVEY_HANDOFF_WHISPER,
)
from ..voice_ai.predefined_responses import PredefinedResponses
from ..voice_ai.twilio_protocol import send_text_token
from ..survey_submission import MilestoneEvent, SurveyMilestoneDispatcher

logger = logging.getLogger(__name__)


def sanitize_for_log(value: Any) -> str:
    """Sanitize any value to prevent log injection attacks.

    Removes carriage returns, newlines, tabs, and unicode line/paragraph
    separators that could be used to inject fake log entries into log
    aggregation systems. Also handles None values safely.
    """
    if value is None:
        return "<null>"
    val_str = str(value)
    return (
        val_str.replace("\r", "")
        .replace("\n", "")
        .replace("\t", "")
        .replace("\u2028", "")
        .replace("\u2029", "")
    )


def default_coach_whisper() -> str:
    return DEFAULT_HANDOFF_WHISPER


def survey_completed_coach_whisper() -> str:
    return COMPLETED_SURVEY_HANDOFF_WHISPER


def coalesce_whisper_text(*candidates: Optional[str]) -> str:
    for c in candidates:
        if isinstance(c, str) and c.strip():
            return c.strip()
    return default_coach_whisper()


async def _persist_coach_handoff(
    call_state_manager: "CallStateManager",
    handover_text: str,
    handover_node_id: str = "coach_handoff",
    whisper_text: Optional[str] = None,
) -> None:
    """Persist the coach handoff event to the conversation log.

    If a question is currently active (the user's request was already captured
    via add_turn), it is completed and persisted as-is. Otherwise a synthetic
    question entry is created so the handoff message appears in the dashboard.

    whisper_text, when provided, is stored in final_answer so the dashboard
    shows what context was relayed to the coach.
    """
    try:
        if call_state_manager.get_current_question_id() is None:
            # Retrieve the last thing the caller said (from the most recently
            # completed question) so it appears in the handover entry as context.
            last_user_input = ""
            if call_state_manager.completed_questions:
                last_q = call_state_manager.completed_questions[-1]
                last_turns = last_q.get("turns", [])
                if last_turns:
                    last_user_input = last_turns[-1].get("user_message", "") or ""

            call_state_manager.start_question(
                handover_node_id, handover_text, "handover_to_coach"
            )
            call_state_manager.add_turn(
                user_message=last_user_input,
                assistant_message=handover_text,
                llm_interpretation="coach_handoff",
                llm_confidence=None,
                validation_result=None,
                escalated=False,
            )
        final_answer: Any = {"mode": "handover_to_coach", "whisper_text": whisper_text}
        question_data = call_state_manager.complete_question(final_answer)
        if question_data:
            await persist_question_async(call_state_manager.response_id, question_data)
    except Exception as e:
        logger.error(
            "Error persisting coach handoff turn",
            extra={"error": str(e)},
            exc_info=True,
        )


async def _persist_survey_completion(
    call_state_manager: "CallStateManager",
    completion_text: str,
) -> None:
    """Persist the final survey completion text as a synthetic entry.

    When the survey ends naturally (speak_next_or_finish returns finished=True),
    the closing interstitial text is spoken to the caller but never written to
    responses.questions.  This creates a synthetic entry so the dashboard
    shows the full conversation up to and including the goodbye/handover text.
    """
    try:
        last_user_input = ""
        if call_state_manager.completed_questions:
            last_q = call_state_manager.completed_questions[-1]
            last_turns = last_q.get("turns", [])
            if last_turns:
                last_user_input = last_turns[-1].get("user_message", "") or ""

        call_state_manager.start_question(
            "survey_completed_message", completion_text, "interstitial"
        )
        call_state_manager.add_turn(
            user_message=last_user_input,
            assistant_message=completion_text,
            llm_interpretation="survey_completed",
            llm_confidence=None,
            validation_result=None,
            escalated=False,
        )
        question_data = call_state_manager.complete_question(
            {"mode": "survey_completed"}
        )
        if question_data:
            await persist_question_async(call_state_manager.response_id, question_data)
    except Exception as e:
        logger.error(
            "Error persisting survey completion",
            extra={"error": str(e)},
            exc_info=True,
        )


async def _emit_milestone_events(
    dispatcher: Optional[SurveyMilestoneDispatcher],
    adapter: SurveyBackendAdapter,
    completed_node_id: str,
    call_state_manager: Optional[CallStateManager],
    call_sid: Optional[str],
    correlation_id: str,
) -> None:
    """
    Emit milestone events after a question is recorded and the engine advances.

    Emits up to two events:
    1. ``question_answered`` -- always emitted for the completed question.
    2. ``source_completed`` -- emitted when the completed question's source
       differs from the *current* node's source (i.e. a section boundary was
       crossed, such as screening -> profiling).

    Events are dispatched as fire-and-forget tasks so they never block the
    voice conversation.
    """
    if dispatcher is None:
        return

    engine = adapter.engine
    answered_source = engine.get_node_source(completed_node_id)
    current_source = engine.get_current_source()
    response_id = call_state_manager.response_id if call_state_manager else None

    # 1) question_answered -- always
    question_event = MilestoneEvent(
        event_type="question_answered",
        question_id=completed_node_id,
        source=answered_source,
        previous_source=None,
        all_answers=dict(engine.answers),
        response_id=response_id,
        call_sid=call_sid,
        correlation_id=correlation_id,
    )
    asyncio.create_task(dispatcher.on_milestone(question_event))

    # 2) source_completed -- on section transitions
    if answered_source and current_source and answered_source != current_source:
        transition_event = MilestoneEvent(
            event_type="source_completed",
            question_id=completed_node_id,
            source=current_source,
            previous_source=answered_source,
            all_answers=dict(engine.answers),
            response_id=response_id,
            call_sid=call_sid,
            correlation_id=correlation_id,
        )
        asyncio.create_task(dispatcher.on_milestone(transition_event))


# Small helper so we always log assistant speech into the conversation history
async def send_and_log(
    ws: WebSocket,
    text: str,
    last: bool,
    conversation_log: List[Dict[str, str]],
    metrics_collector=None,
    interruptible: Optional[bool] = None,
    preemptible: Optional[bool] = None,
    lang: Optional[str] = None,
):

    logger.debug("=" * 32 + " ASSISTANT SAYS " + "=" * 32)
    logger.debug(
        "Assistant says",
        extra={"assistant_text": sanitize_for_log(text), "last": last},
    )
    logger.debug("=" * 80 + "\n" + "\n")

    await send_text_token(
        ws,
        text,
        last=last,
        interruptible=interruptible,
        preemptible=preemptible,
        lang=lang,
    )
    conversation_log.append({"role": "assistant", "text": text})

    if metrics_collector is not None:
        metrics_collector.record_message_sent({"message_type": "response"})


async def speak_next_or_finish(
    ws: WebSocket,
    nxt: Dict[str, Any],
    conversation_log: List[Dict[str, str]],
    metrics_collector=None,
) -> bool:
    """
    Unified helper that:
      - Speaks the final narration + goodbye and ends the session
      - OR speaks the next question and continues the session

    Returns:
      True  -> conversation finished (caller should break)
      False -> continue asking questions
    """
    spoken = nxt.get("spoken_intro") or ""
    prompt = nxt.get("question_prompt") or ""
    spoken_intro_interruptible = nxt.get("spoken_intro_interruptible")
    spoken_intro_preemptible = nxt.get("spoken_intro_preemptible")
    interruptible = nxt.get("interruptible")
    preemptible = nxt.get("preemptible")

    # Speak accumulated narration/interstitial text
    if spoken:
        await send_and_log(
            ws,
            spoken,
            last=True,
            conversation_log=conversation_log,
            metrics_collector=metrics_collector,
            interruptible=spoken_intro_interruptible,
            preemptible=spoken_intro_preemptible,
        )

    # Speak the question prompt (if any)
    if prompt:
        await send_and_log(
            ws,
            prompt,
            last=True,
            conversation_log=conversation_log,
            metrics_collector=metrics_collector,
            interruptible=interruptible,
            preemptible=preemptible,
        )

    # If this was the final step, finish session
    if nxt.get("finished"):

        final_text = " ".join(part for part in (spoken, prompt) if part)

        if not final_text:
            final_text = PredefinedResponses.GOODBYE
            await send_and_log(
                ws,
                final_text,
                last=True,
                conversation_log=conversation_log,
                metrics_collector=metrics_collector,
            )

        final_wait_seconds = estimate_tts_duration_seconds(final_text)

        # Allow Twilio time to play final TTS before closing websocket
        await asyncio.sleep(final_wait_seconds)

        return True

    return False


def estimate_tts_duration_seconds(text: str) -> float:
    """
    Rough TTS duration estimate for speech.

    We prefer a simple heuristic:
    - based on word count
    - small minimum/floor
    - extra buffer for TTS startup and pauses
    """
    text = (text or "").strip()
    if not text:
        return 0.0

    # Split on words/numbers so long punctuation blocks do not distort too much
    words = re.findall(r"\b[\w']+\b", text)
    word_count = len(words)

    # ~150 wpm ~= 2.5 words/sec
    speech_seconds = word_count / 2.5 if word_count else 0.0

    # Safety buffer for startup / punctuation pauses
    buffer_seconds = 1.0

    # Avoid unrealistically small waits for short utterances
    return max(
        2.0, speech_seconds + buffer_seconds + settings.tts_estimate_adjustment_seconds
    )
