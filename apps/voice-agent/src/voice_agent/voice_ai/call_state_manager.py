"""Call state manager for tracking conversation data during voice survey calls."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class CallStateManager:
    """
    Manages state for a single voice survey call, tracking conversation turns,
    timing information, and metadata for persistence.

    This class accumulates all conversation data in memory during the call,
    then provides serialization methods for background persistence without
    blocking the real-time conversation flow.
    """

    def __init__(
        self,
        response_id: UUID,
        call_sid: str,
        session_id: str,
        correlation_id: str,
    ):
        """
        Initialize call state manager for a new call.

        Args:
            response_id: UUID of the SurveyResponse record in database
            call_sid: Twilio call SID
            session_id: Internal session identifier
            correlation_id: Correlation ID for tracing
        """
        self.response_id = response_id
        self.call_sid = call_sid
        self.session_id = session_id
        self.correlation_id = correlation_id

        # Timing
        self.call_start_time = datetime.now(timezone.utc)
        self.call_end_time: Optional[datetime] = None

        # Question tracking
        self.current_question_data: Optional[Dict[str, Any]] = None
        self.completed_questions: List[Dict[str, Any]] = []

        # Session-level counters
        self.escalation_count = 0
        self.interruption_count = 0
        self.nodes_visited: List[str] = []

        logger.info(
            "Initialized CallStateManager",
            extra={
                "response_id": str(response_id),
                "call_sid": call_sid,
                "session_id": session_id,
                "correlation_id": correlation_id,
            },
        )

    def start_question(
        self,
        node_id: str,
        question_text: str,
        node_type: str,
    ) -> None:
        """
        Start tracking a new question.

        This should be called when the system moves to a new question node.
        If there's already an active question, it will be logged as a warning
        but the new question will still be started.

        Args:
            node_id: Unique identifier for the question node
            question_text: The text of the question being asked
            node_type: Type of question (yes_no, single_choice, etc.)
        """
        if self.current_question_data is not None:
            logger.warning(
                "Starting new question while previous question still active",
                extra={
                    "response_id": str(self.response_id),
                    "previous_question_id": self.current_question_data.get(
                        "question_id"
                    ),
                    "new_question_id": node_id,
                },
            )

        self.current_question_data = {
            "question_id": node_id,
            "question_text": question_text,
            "node_type": node_type,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "duration_ms": None,
            "turns": [],
            "final_answer": None,
            "attempts": 0,
        }

        # Track node visitation
        if node_id not in self.nodes_visited:
            self.nodes_visited.append(node_id)

        logger.debug(
            "Started tracking question",
            extra={
                "response_id": str(self.response_id),
                "question_id": node_id,
                "node_type": node_type,
                "question_text": question_text[:50],
            },
        )

    def add_turn(
        self,
        user_message: str,
        assistant_message: str,
        llm_interpretation: str,
        llm_confidence: Optional[float],
        validation_result: Optional[Dict[str, Any]],
        escalated: bool,
    ) -> None:
        """
        Add a conversation turn to the current question.

        This captures the complete exchange: what the user said, what the AI
        responded, and all the metadata about interpretation and validation.

        Args:
            user_message: What the user said (from STT)
            assistant_message: What the AI responded (TTS text)
            llm_interpretation: LLM's classification of user input
            llm_confidence: Confidence score from LLM (0.0-1.0), or None for system prompts
            validation_result: Result of deterministic validation
            escalated: Whether this turn triggered escalation
        """
        if self.current_question_data is None:
            logger.warning(
                "Attempted to add turn without active question",
                extra={
                    "response_id": str(self.response_id),
                    "user_message": (user_message[:50] if user_message else ""),
                },
            )
            return

        turn_number = len(self.current_question_data["turns"]) + 1

        turn_data = {
            "turn_number": turn_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "assistant_message": assistant_message,
            "user_message": user_message,
            "llm_interpretation": llm_interpretation,
            "llm_confidence": llm_confidence,
            "validation_result": validation_result,
            "escalated": escalated,
        }

        self.current_question_data["turns"].append(turn_data)
        self.current_question_data["attempts"] = turn_number

        # Track escalations at session level
        if escalated:
            self.escalation_count += 1

        logger.debug(
            "Added conversation turn",
            extra={
                "response_id": str(self.response_id),
                "question_id": self.current_question_data.get("question_id"),
                "turn_number": turn_number,
                "escalated": escalated,
            },
        )

    def complete_question(self, final_answer: Any) -> Optional[Dict[str, Any]]:
        """
        Mark the current question as completed and return its data.

        This should be called when the user provides a valid answer that
        is accepted by the system (after adapter.record()).

        Args:
            final_answer: The normalized/final answer value

        Returns:
            The completed question data dict, or None if no active question
        """
        if self.current_question_data is None:
            logger.warning(
                "Attempted to complete question without active question",
                extra={"response_id": str(self.response_id)},
            )
            return None

        # Calculate duration
        started_at = datetime.fromisoformat(self.current_question_data["started_at"])
        completed_at = datetime.now(timezone.utc)
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

        # Finalize question data
        self.current_question_data["completed_at"] = completed_at.isoformat()
        self.current_question_data["duration_ms"] = duration_ms
        self.current_question_data["final_answer"] = final_answer

        # Move to completed list
        completed_data = self.current_question_data.copy()
        self.completed_questions.append(completed_data)

        logger.info(
            "Completed question",
            extra={
                "response_id": str(self.response_id),
                "question_id": completed_data["question_id"],
                "attempts": completed_data["attempts"],
                "duration_ms": duration_ms,
            },
        )

        # Clear current question
        question_data = self.current_question_data
        self.current_question_data = None

        return question_data

    def record_interruption(self) -> None:
        """Record that an interruption (barge-in) occurred."""
        self.interruption_count += 1
        logger.debug(
            "Recorded interruption",
            extra={
                "response_id": str(self.response_id),
                "total_interruptions": self.interruption_count,
            },
        )

    def finalize_call(self, completion_reason: str) -> None:
        """
        Mark the call as ended and record completion reason.

        Args:
            completion_reason: Reason for call ending
                              (e.g., "all_questions_answered", "user_disconnect")
        """
        self.call_end_time = datetime.now(timezone.utc)

        logger.info(
            "Finalized call",
            extra={
                "response_id": str(self.response_id),
                "completion_reason": completion_reason,
                "questions_completed": len(self.completed_questions),
                "call_duration_ms": self.get_total_duration_ms(),
            },
        )

    def build_session_metadata(
        self, completion_reason: str = "unknown"
    ) -> Dict[str, Any]:
        """
        Build the session_metadata JSONB structure for persistence.

        Args:
            completion_reason: Reason the call ended

        Returns:
            Dict with call-level metadata including timing, counts, and identifiers
        """
        total_turns = sum(len(q["turns"]) for q in self.completed_questions)

        metadata = {
            "call_sid": self.call_sid,
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
            "total_duration_ms": self.get_total_duration_ms(),
            "total_questions": len(self.completed_questions),
            "total_turns": total_turns,
            "completion_reason": completion_reason,
            "nodes_visited": self.nodes_visited.copy(),
            "escalations_count": self.escalation_count,
            "interruptions_count": self.interruption_count,
        }

        return metadata

    def get_total_duration_ms(self) -> Optional[int]:
        """
        Calculate total call duration in milliseconds.

        Returns:
            Duration in milliseconds, or None if call not yet ended
        """
        if self.call_end_time is None:
            return None

        duration = (self.call_end_time - self.call_start_time).total_seconds()
        return int(duration * 1000)

    def get_current_question_id(self) -> Optional[str]:
        """
        Get the ID of the currently active question.

        Returns:
            Question ID string, or None if no active question
        """
        if self.current_question_data is None:
            return None
        return self.current_question_data.get("question_id")
