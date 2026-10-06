"""Survey session initialization — sets up survey engine and sends the first question."""

import logging
from typing import Dict, List, Optional

from fastapi import WebSocket

from ...config import settings
from ...voice_ai.survey_engine import SurveyEngine
from ...voice_ai.backend_adapter import SurveyBackendAdapter
from ...voice_ai.predefined_responses import PredefinedResponses
from ..websocket_helpers import send_and_log

logger = logging.getLogger(__name__)


async def initialize_survey_session(
    websocket: WebSocket,
    metrics_collector,
    conversation_log: List[Dict[str, str]],
) -> Optional[SurveyBackendAdapter]:
    """
    Initialise the survey engine + backend adapter and send the first question.

    Args:
        websocket: WebSocket connection
        metrics_collector: Metrics collector instance
        conversation_log: Conversation log list

    Returns:
        SurveyBackendAdapter instance if successful, otherwise None (and sends
        an appropriate failure message to the caller).
    """
    try:
        engine = SurveyEngine.from_file(
            settings.survey_json_path,
            settings.initial_node_id,
        )
        adapter = SurveyBackendAdapter(engine)
    except Exception:
        logger.exception("Init failure for survey engine")
        await send_and_log(
            websocket,
            PredefinedResponses.INIT_FAIL,
            last=True,
            conversation_log=conversation_log,
            metrics_collector=metrics_collector,
        )
        return None

    try:
        first = adapter.advance()
        logger.debug("advance() -> %s", first)
        spoken_intro = first.get("spoken_intro") or ""
        question_prompt = first.get("question_prompt") or ""

        if spoken_intro:
            await send_and_log(
                websocket,
                spoken_intro,
                last=True,
                conversation_log=conversation_log,
                metrics_collector=metrics_collector,
                interruptible=first.get("spoken_intro_interruptible"),
                preemptible=first.get("spoken_intro_preemptible"),
            )

        if question_prompt:
            await send_and_log(
                websocket,
                question_prompt,
                last=True,
                conversation_log=conversation_log,
                metrics_collector=metrics_collector,
                interruptible=first.get("interruptible"),
                preemptible=first.get("preemptible"),
            )
    except Exception:
        logger.exception("Failed in initial advance/prompt")
        await send_and_log(
            websocket,
            PredefinedResponses.START_FAIL,
            last=True,
            conversation_log=conversation_log,
            metrics_collector=metrics_collector,
        )
        return None

    return adapter
