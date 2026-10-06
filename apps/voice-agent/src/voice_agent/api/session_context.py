"""Per-call session context for the WebSocket ConversationRelay endpoint."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from fastapi import WebSocket

from ..voice_ai.backend_adapter import SurveyBackendAdapter
from ..voice_ai.llm_handler_factory import LLMHandler
from ..voice_ai.call_state_manager import CallStateManager
from ..survey_submission import SurveyMilestoneDispatcher


@dataclass
class SessionContext:
    """Holds per-call session state for the duration of a WebSocket connection.

    Constructed after the survey engine is initialised and populated with
    call-specific data (call_sid, call_state_manager, etc.) once the Twilio
    setup message arrives.
    """

    # Always present at construction time
    websocket: WebSocket
    adapter: SurveyBackendAdapter
    llm_handler: LLMHandler
    conversation_log: List[Dict[str, str]]
    correlation_id: str
    session_id: str
    metrics_collector: Any

    # Populated after the Twilio setup message is processed
    call_sid: Optional[str] = None
    participant_phone: str = ""
    call_state_manager: Optional[CallStateManager] = None
    milestone_dispatcher: Optional[SurveyMilestoneDispatcher] = None
    # Mutable turn state — updated after each prompt/big-model round-trip
    active_big_model_node: Optional[str] = None
    turn_seq: int = 0

    def llm_call_kwargs(self) -> Dict[str, str]:
        """Identifiers passed to the LLM handler async methods so the resulting
        gen_ai.* spans carry call_sid / correlation_id / session_id.
        """
        return {
            "call_sid": self.call_sid or "",
            "correlation_id": self.correlation_id,
            "session_id": self.session_id,
        }
