"""Survey response repository for database operations."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session


from ..models import SurveyResponse, SurveyResponseStatus
from ..utils.encryption import (
    decrypt_json,
    encrypt,
    encrypt_json,
)

logger = logging.getLogger(__name__)


# Integration types whose outcome may be denormalised into the unencrypted
# integration_outcomes column. Only the success flag is copied out, so nothing
# on this list leaks participant data.
_OUTCOME_ALLOWLIST = {"local_submission", "webhook_submission"}


def _extract_integration_outcome(integration_type: str, data: dict) -> Optional[dict]:
    """Extract non-PII outcome fields from an integration event.

    Returns a small dict with only the success flag, or None if the
    integration type is not on the allowlist.
    """
    if not isinstance(data, dict) or integration_type not in _OUTCOME_ALLOWLIST:
        return None
    response = data.get("response") or {}
    return {"success": response.get("success")}


class SurveyResponseRepository:
    """Repository for SurveyResponse database operations."""

    def __init__(self, db: Session):
        """
        Initialize repository with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def create(
        self,
        survey_id: UUID,
        participant_phone: str,
        responses: Optional[dict] = None,
        session_metadata: Optional[dict] = None,
        call_sid: Optional[str] = None,
    ) -> SurveyResponse:
        """
        Create a new survey response.

        Args:
            survey_id: UUID of the survey being responded to
            participant_phone: Phone number or identifier of the participant
            responses: Optional initial responses data
            session_metadata: Optional metadata for the response session
            call_sid: Optional Twilio CallSid, mirrored into an indexed column so
                the recording-status callback can look up the row by CallSid

        Returns:
            The created survey response

        Raises:
            Exception: If there's an error creating the response
        """
        try:
            survey_response = SurveyResponse(
                survey_id=survey_id,
                participant_phone=encrypt(participant_phone),
                status=SurveyResponseStatus.IN_PROGRESS.value,
                responses=encrypt_json(responses or {"questions": []}),
                session_metadata=encrypt_json(session_metadata or {}),
                call_sid=call_sid,
                started_at=datetime.now(timezone.utc),
            )
            self.db.add(survey_response)
            self.db.commit()
            self.db.refresh(survey_response)

            logger.info(
                "Created survey response",
                extra={
                    "survey_response_id": str(survey_response.id),
                    "survey_id": str(survey_id),
                    "participant_phone": participant_phone[:4] + "***",
                    "status": survey_response.status,
                },
            )

            return survey_response

        except Exception as e:
            logger.error(
                "Error creating survey response",
                extra={
                    "survey_id": str(survey_id),
                    "participant_phone": participant_phone[:4] + "***",
                    "error": str(e),
                },
                exc_info=True,
            )
            self.db.rollback()
            raise

    def get_by_id(self, response_id: UUID) -> Optional[SurveyResponse]:
        """
        Get a survey response by ID.

        Args:
            response_id: UUID of the survey response

        Returns:
            The survey response if found, None otherwise
        """
        try:
            response = (
                self.db.query(SurveyResponse)
                .filter(SurveyResponse.id == response_id)
                .first()
            )

            if response:
                logger.debug(
                    "Retrieved survey response",
                    extra={
                        "survey_response_id": str(response_id),
                        "status": response.status,
                    },
                )

            return response

        except Exception as e:
            logger.error(
                "Error retrieving survey response",
                extra={"survey_response_id": str(response_id), "error": str(e)},
                exc_info=True,
            )
            raise

    def _get_for_update(self, response_id: UUID) -> Optional[SurveyResponse]:
        """Load a response with a row lock held until the transaction ends.

        Every mutator below is a read-modify-write over an encrypted blob: it
        decrypts the whole column, changes one entry, and writes the whole
        column back. Question persistence is fired as an un-awaited task per
        answer, so two of them can overlap; without this lock the second reads
        a snapshot taken before the first committed and writes over it, and an
        answer disappears with no error anywhere.

        SQLite ignores FOR UPDATE, which is fine: the tests that run on it do
        not exercise concurrency.
        """
        return (
            self.db.query(SurveyResponse)
            .filter(SurveyResponse.id == response_id)
            .with_for_update()
            .first()
        )

    def get_by_call_sid(self, call_sid: str) -> Optional[SurveyResponse]:
        """
        Get the most recent survey response for a Twilio CallSid.

        Used by the recording-status callback, which only knows the CallSid, to
        find the row whose transcript export should carry the recording metadata.

        Args:
            call_sid: Twilio CallSid

        Returns:
            The matching survey response if found, None otherwise
        """
        try:
            return (
                self.db.query(SurveyResponse)
                .filter(SurveyResponse.call_sid == call_sid)
                .order_by(SurveyResponse.created_at.desc())
                .first()
            )
        except Exception as e:
            logger.error(
                "Error retrieving survey response by call_sid",
                extra={"call_sid": call_sid, "error": str(e)},
                exc_info=True,
            )
            raise

    def add_question_response(
        self,
        response_id: UUID,
        question_id: str,
        question_text: str,
        answer: str,
        metadata: Optional[dict] = None,
    ) -> SurveyResponse:
        """
        Add a single question response to an existing survey response.

        This method supports incremental saving of responses as the
        participant answers each question. The metadata can include rich
        conversation data like turn history, timing, and LLM interpretations.

        Args:
            response_id: UUID of the survey response
            question_id: Identifier for the question
            question_text: The text of the question
            answer: The participant's answer
            metadata: Optional metadata for this specific answer, can include:
                     - node_type: Type of question node
                     - started_at: ISO timestamp when question started
                     - completed_at: ISO timestamp when question completed
                     - duration_ms: Time taken to answer in milliseconds
                     - turns: Array of conversation turns
                     - attempts: Number of attempts to answer

        Returns:
            The updated survey response

        Raises:
            ValueError: If the response is not found or already completed
            Exception: If there's an error updating the response
        """
        try:
            survey_response = self._get_for_update(response_id)

            if not survey_response:
                raise ValueError(f"Survey response {response_id} not found")

            if survey_response.status == SurveyResponseStatus.COMPLETED.value:
                raise ValueError(f"Survey response {response_id} is already completed")

            # Build question response with rich metadata
            question_response = {
                "question_id": question_id,
                "question_text": question_text,
                "answer": answer,
                "answered_at": datetime.now(timezone.utc).isoformat(),
            }

            # Merge in rich metadata if provided (includes turns, timing, etc.)
            if metadata:
                question_response.update(metadata)

            # Decrypt, modify, re-encrypt
            responses_data = decrypt_json(survey_response.responses)
            if "questions" not in responses_data:
                responses_data["questions"] = []

            responses_data["questions"].append(question_response)
            survey_response.responses = encrypt_json(responses_data)

            # Update denormalized analytics columns
            survey_response.last_question_id = question_id
            survey_response.last_question_text = question_text

            # Mark as modified for SQLAlchemy to detect JSONB change
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(survey_response, "responses")

            self.db.commit()
            self.db.refresh(survey_response)

            question_count = len(responses_data.get("questions", []))
            logger.info(
                "Added question response",
                extra={
                    "survey_response_id": str(response_id),
                    "question_id": question_id,
                    "question_count": question_count,
                    "turns": len(metadata.get("turns", [])) if metadata else 0,
                },
            )

            return survey_response

        except ValueError:
            raise
        except Exception as e:
            logger.error(
                "Error adding question response",
                extra={
                    "survey_response_id": str(response_id),
                    "question_id": question_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            self.db.rollback()
            raise

    def complete_response(self, response_id: UUID) -> SurveyResponse:
        """
        Mark a survey response as completed.

        Args:
            response_id: UUID of the survey response

        Returns:
            The updated survey response

        Raises:
            ValueError: If the response is not found
            Exception: If there's an error updating the response
        """
        try:
            survey_response = self._get_for_update(response_id)

            if not survey_response:
                raise ValueError(f"Survey response {response_id} not found")

            survey_response.status = SurveyResponseStatus.COMPLETED.value
            survey_response.completed_at = datetime.now(timezone.utc)

            self.db.commit()
            self.db.refresh(survey_response)

            responses_data = decrypt_json(survey_response.responses)
            logger.info(
                "Completed survey response",
                extra={
                    "survey_response_id": str(response_id),
                    "question_count": len(responses_data.get("questions", [])),
                },
            )

            return survey_response

        except ValueError:
            raise
        except Exception as e:
            logger.error(
                "Error completing survey response",
                extra={"survey_response_id": str(response_id), "error": str(e)},
                exc_info=True,
            )
            self.db.rollback()
            raise

    def abandon_response(self, response_id: UUID) -> SurveyResponse:
        """
        Mark a survey response as abandoned.

        Args:
            response_id: UUID of the survey response

        Returns:
            The updated survey response

        Raises:
            ValueError: If the response is not found
            Exception: If there's an error updating the response
        """
        try:
            survey_response = self._get_for_update(response_id)

            if not survey_response:
                raise ValueError(f"Survey response {response_id} not found")

            survey_response.status = SurveyResponseStatus.ABANDONED.value

            self.db.commit()
            self.db.refresh(survey_response)

            logger.info(
                "Abandoned survey response",
                extra={"survey_response_id": str(response_id)},
            )

            return survey_response

        except ValueError:
            raise
        except Exception as e:
            logger.error(
                "Error abandoning survey response",
                extra={"survey_response_id": str(response_id), "error": str(e)},
                exc_info=True,
            )
            self.db.rollback()
            raise

    _TERMINAL_STATUSES = [
        SurveyResponseStatus.COMPLETED.value,
        SurveyResponseStatus.ABANDONED.value,
    ]

    def update_session_metadata(
        self, response_id: UUID, metadata: dict
    ) -> SurveyResponse:
        """
        Update session metadata for a survey response.

        This method merges the provided metadata with existing metadata,
        useful for incrementally updating call-level information like
        timing, escalation counts, and completion reasons.

        Args:
            response_id: UUID of the survey response
            metadata: Metadata dict to merge with existing metadata

        Returns:
            The updated survey response

        Raises:
            ValueError: If the response is not found
            Exception: If there's an error updating the response
        """
        try:
            survey_response = self._get_for_update(response_id)

            if not survey_response:
                raise ValueError(f"Survey response {response_id} not found")

            # Decrypt, merge, re-encrypt
            current_metadata = decrypt_json(survey_response.session_metadata)
            updated_metadata = {**current_metadata, **metadata}

            survey_response.session_metadata = encrypt_json(updated_metadata)

            # Update denormalized escalations_count
            esc = updated_metadata.get("escalations_count")
            if esc is not None and esc != "null":
                survey_response.escalations_count = int(esc)

            # Mark as modified for SQLAlchemy to detect JSONB change
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(survey_response, "session_metadata")

            self.db.commit()
            self.db.refresh(survey_response)

            logger.info(
                "Updated session metadata",
                extra={
                    "survey_response_id": str(response_id),
                    "metadata_keys": list(metadata.keys()),
                },
            )

            return survey_response

        except ValueError:
            raise
        except Exception as e:
            logger.error(
                "Error updating session metadata",
                extra={
                    "survey_response_id": str(response_id),
                    "error": str(e),
                },
                exc_info=True,
            )
            self.db.rollback()
            raise

    def update_integration_event(
        self, response_id: UUID, integration_type: str, data: dict
    ) -> None:
        """
        Merge a single integration result into the integrations JSONB column.

        Args:
            response_id: UUID of the survey response
            integration_type: Key for the integration (e.g. "user_search")
            data: Dict with the integration event data to store
        """
        try:
            obj = self._get_for_update(response_id)
            if obj:
                from sqlalchemy.orm.attributes import flag_modified

                current = decrypt_json(obj.integrations)
                current[integration_type] = data
                obj.integrations = encrypt_json(current)
                flag_modified(obj, "integrations")

                # Update denormalized integration_outcomes (non-PII only)
                outcome = _extract_integration_outcome(integration_type, data)
                if outcome is not None:
                    current_outcomes = obj.integration_outcomes or {}
                    current_outcomes[integration_type] = outcome
                    obj.integration_outcomes = current_outcomes
                    flag_modified(obj, "integration_outcomes")

                self.db.commit()
                logger.debug(
                    "Updated integration event",
                    extra={
                        "survey_response_id": str(response_id),
                        "integration_type": integration_type,
                    },
                )
            else:
                logger.warning(
                    "update_integration_event: response not found",
                    extra={"survey_response_id": str(response_id)},
                )
        except Exception as e:
            self.db.rollback()
            logger.warning(
                "update_integration_event: failed to persist",
                extra={
                    "survey_response_id": str(response_id),
                    "integration_type": integration_type,
                    "error": str(e),
                },
            )
            raise
