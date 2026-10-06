"""Types for the survey submission engine."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID


class FailureKind(Enum):
    """Why a submission did not succeed — drives whether we hand off to a coach."""

    NONE = "none"  # success
    BLOCKING = "blocking"  # technical failure → coach handoff


@dataclass
class MilestoneEvent:
    """
    Event emitted when something relevant happens during the survey flow.

    The dispatcher broadcasts these to all registered handlers, which decide
    independently whether to trigger based on the event contents.

    Attributes:
        event_type: Kind of milestone that occurred.
            - "question_answered": A single interactive question was completed.
            - "source_completed": All questions in a source section finished
              (the transition from one section to the next).
            - "call_ended": The call finished (success or disconnect).
        question_id: ID of the question that was just answered (if applicable).
        source: Source section of the question that was just answered.
        previous_source: Previous source section (set on source transitions).
        all_answers: Snapshot of every answer collected so far (engine.answers).
        response_id: UUID of the SurveyResponse database record.
        call_sid: Twilio call SID for tracing.
        correlation_id: Request correlation ID for tracing.
    """

    event_type: str
    question_id: Optional[str]
    source: Optional[str]
    previous_source: Optional[str]
    all_answers: Dict[str, Any]
    response_id: Optional[UUID]
    call_sid: Optional[str] = None
    correlation_id: Optional[str] = None


@dataclass
class SubmissionResult:
    """
    Result returned by a handler after attempting to submit a survey.

    Attributes:
        success: Whether the submission completed successfully.
        survey_id: Identifier of the survey that was submitted.
        data: Arbitrary payload returned by the backend (e.g. affiliation,
              trackId, eligibility status).
        error: Human-readable error message when success is False.
        failure_kind: Categorization of why the submission failed, if it did.
        status_code: Upstream HTTP status code when the failure came from an
            HTTP call (None for non-HTTP failures such as missing answers).
    """

    success: bool
    survey_id: str
    data: Optional[Dict[str, Any]] = field(default=None)
    error: Optional[str] = None
    failure_kind: FailureKind = field(default=FailureKind.NONE)
    status_code: Optional[int] = None
