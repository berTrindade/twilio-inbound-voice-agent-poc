"""Survey response model for storing participant responses."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from ..database import Base


class SurveyResponseStatus(str, Enum):
    """Status of a survey response."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class SurveyResponse(Base):
    """
    Survey response model representing a participant's response to a survey.

    This model is designed to be resilient and flexible, storing responses
    in a JSONB format that can accommodate any survey structure changes
    without requiring schema migrations.
    """

    __tablename__ = "survey_responses"

    # Primary identifier
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Survey reference (foreign key to surveys table)
    survey_id = Column(
        UUID(as_uuid=True),
        ForeignKey("surveys.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Participant identifier (phone number or other unique identifier).
    # Encrypted with a random nonce per row, so the same phone never produces
    # the same ciphertext twice and no index here could ever serve a lookup.
    # Nothing looks a caller up by phone, so there is no blind-index column
    # either; add one alongside the query that needs it, not before.
    participant_phone = Column(String, nullable=False)

    # Response status
    status = Column(
        String,
        nullable=False,
        default=SurveyResponseStatus.IN_PROGRESS.value,
    )

    # Flexible response data stored as JSONB
    # Structure: {
    #   "questions": [
    #     {
    #       "question_id": "q1",
    #       "question_text": "How are you feeling?",
    #       "answer": "Great!",
    #       "answered_at": "2025-11-03T10:30:00Z",
    #       "metadata": {...}  # Optional: confidence scores, audio duration, etc.
    #     },
    #     ...
    #   ]
    # }
    responses = Column(JSONB, nullable=False, default=dict)

    # Optional metadata for the entire response session
    # Can include: device info, audio quality metrics, interruptions, etc.
    session_metadata = Column(JSONB, nullable=True, default=dict)

    # Integration event data, keyed by integration type.
    # Shape: { "local_submission": {...}, ... }
    integrations = Column(JSONB, nullable=True, default=dict)

    # Denormalized analytics columns (non-PII, unencrypted for SQL queries)
    escalations_count = Column(Integer, nullable=True, default=0)
    # Twilio CallSid, mirrored out of the encrypted session_metadata so the
    # recording-status callback (which only knows the CallSid) can find the row.
    call_sid = Column(String, nullable=True, index=True)
    last_question_id = Column(String, nullable=True)
    last_question_text = Column(String, nullable=True)
    integration_outcomes = Column(JSONB, nullable=True, default=dict)

    # Timestamps for tracking response lifecycle
    started_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Audit timestamp. started_at is what every query uses; this one exists
    # so a row can be traced back to when it was inserted.
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationship to survey (optional, for joins)
    survey = relationship("Survey", backref="responses")

    # Every dashboard query filters or sorts on started_at, so this one index
    # serves all of them. The composites that used to sit here trailed on
    # created_at, which nothing queries; measured over a full dashboard pass
    # at 200k rows they took 39 MB and were scanned zero times.
    __table_args__ = (Index("idx_sr_started_at", "started_at"),)

    def __repr__(self):
        return (
            f"<SurveyResponse(id={self.id}, survey_id={self.survey_id}, "
            f"participant={self.participant_phone[:4]}..., status={self.status})>"
        )
