"""Async persistence utilities for background database writes without blocking conversation flow."""

import logging
from typing import Any, Callable, Dict, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..repositories import SurveyResponseRepository
from ..utils.encryption import decrypt_json, encrypt_json

logger = logging.getLogger(__name__)


def persist_recording_metadata(call_sid: str, recording: Dict[str, Any]) -> None:
    """Save the recording block onto the call, found by CallSid.

    Runs as a background task and never raises into Twilio's callback.
    """
    db = None
    try:
        db = SessionLocal()
        repo = SurveyResponseRepository(db)
        row = repo.get_by_call_sid(call_sid)
        if row is None:
            logger.warning(
                "Recording metadata: no survey response found for call_sid",
                extra={"call_sid": call_sid},
            )
            return
        response_id = row.id
        repo.update_session_metadata(response_id, {"recording": recording})
        logger.info(
            "Persisted recording metadata",
            extra={
                "call_sid": call_sid,
                "response_id": str(response_id),
                "recording_status": recording.get("status"),
            },
        )
    except Exception:
        logger.error(
            "Failed to persist recording metadata (non-fatal)",
            extra={"call_sid": call_sid},
            exc_info=True,
        )
    finally:
        if db is not None:
            db.close()


class AsyncPersistence:
    """
    Handles asynchronous persistence of survey data with dependency injection.

    This class manages database sessions and provides methods for persisting
    survey responses, questions, and metadata without blocking the conversation flow.
    """

    def __init__(self, session_factory: Optional[Callable[[], Session]] = None):
        """
        Initialize the async persistence handler.

        Args:
            session_factory: Optional callable that creates database sessions.
                           If not provided, uses SessionLocal.
        """
        self.session_factory = session_factory or SessionLocal

    async def persist_question(
        self, response_id: UUID, question_data: Dict[str, Any]
    ) -> None:
        """
        Persist a completed question to the database in the background.

        This function creates its own database session and handles all errors
        gracefully. It will never raise exceptions to avoid impacting the
        conversation flow.

        Args:
            response_id: UUID of the SurveyResponse record
            question_data: Complete question data with turns, timing, etc.
        """
        db = None
        try:
            db = self.session_factory()
            repo = SurveyResponseRepository(db)

            # Extract fields from question_data
            question_id = question_data.get("question_id", "unknown")
            question_text = question_data.get("question_text", "")
            final_answer = question_data.get("final_answer")

            # Build metadata that includes all the rich conversation data
            metadata = {
                "node_type": question_data.get("node_type"),
                "started_at": question_data.get("started_at"),
                "completed_at": question_data.get("completed_at"),
                "duration_ms": question_data.get("duration_ms"),
                "turns": question_data.get("turns", []),
                "attempts": question_data.get("attempts", 0),
            }

            repo.add_question_response(
                response_id=response_id,
                question_id=question_id,
                question_text=question_text,
                answer=str(final_answer) if final_answer is not None else "",
                metadata=metadata,
            )

            logger.info(
                "Persisted question data",
                extra={
                    "response_id": str(response_id),
                    "question_id": question_id,
                    "attempts": metadata["attempts"],
                    "turns": len(metadata["turns"]),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to persist question data (non-fatal)",
                extra={
                    "response_id": str(response_id),
                    "question_id": question_data.get("question_id", "unknown"),
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
        finally:
            if db is not None:
                db.close()

    async def update_metadata(
        self, response_id: UUID, metadata: Dict[str, Any]
    ) -> None:
        """
        Update session metadata in the database in the background.

        This function creates its own database session and handles all errors
        gracefully. It will never raise exceptions to avoid impacting the
        conversation flow.

        Args:
            response_id: UUID of the SurveyResponse record
            metadata: Session-level metadata to merge/update
        """
        db = None
        try:
            db = self.session_factory()
            repo = SurveyResponseRepository(db)

            # Get current response
            survey_response = repo.get_by_id(response_id)
            if not survey_response:
                logger.error(
                    "Survey response not found for metadata update",
                    extra={"response_id": str(response_id)},
                )
                return

            # Decrypt, merge, re-encrypt
            current_metadata = decrypt_json(survey_response.session_metadata)
            updated_metadata = {**current_metadata, **metadata}

            survey_response.session_metadata = encrypt_json(updated_metadata)

            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(survey_response, "session_metadata")

            db.commit()

            logger.info(
                "Updated session metadata",
                extra={
                    "response_id": str(response_id),
                    "metadata_keys": list(metadata.keys()),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to update session metadata (non-fatal)",
                extra={
                    "response_id": str(response_id),
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            if db is not None:
                db.rollback()
        finally:
            if db is not None:
                db.close()

    async def complete_response(
        self, response_id: UUID, final_metadata: Dict[str, Any]
    ) -> None:
        """
        Mark a survey response as completed and update final metadata.

        This function creates its own database session and handles all errors
        gracefully. It will never raise exceptions to avoid impacting the
        conversation flow.

        Args:
            response_id: UUID of the SurveyResponse record
            final_metadata: Final session metadata before completion
        """
        db = None
        try:
            db = self.session_factory()
            repo = SurveyResponseRepository(db)

            # First update metadata
            await self.update_metadata(response_id, final_metadata)

            # Then mark as completed
            repo.complete_response(response_id)

            logger.info(
                "Marked response as completed",
                extra={
                    "response_id": str(response_id),
                    "completion_reason": final_metadata.get(
                        "completion_reason", "unknown"
                    ),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to complete survey response (non-fatal)",
                extra={
                    "response_id": str(response_id),
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            if db is not None:
                db.rollback()
        finally:
            if db is not None:
                db.close()

    async def abandon_response(
        self, response_id: UUID, final_metadata: Dict[str, Any]
    ) -> None:
        """
        Mark a survey response as abandoned and update final metadata.

        This function creates its own database session and handles all errors
        gracefully. It will never raise exceptions to avoid impacting the
        conversation flow.

        Args:
            response_id: UUID of the SurveyResponse record
            final_metadata: Final session metadata before abandonment
        """
        db = None
        try:
            db = self.session_factory()
            repo = SurveyResponseRepository(db)

            # First update metadata with abandonment info
            await self.update_metadata(response_id, final_metadata)

            # Then mark as abandoned
            repo.abandon_response(response_id)

            logger.info(
                "Marked response as abandoned",
                extra={
                    "response_id": str(response_id),
                    "completion_reason": final_metadata.get(
                        "completion_reason", "disconnect"
                    ),
                    "questions_completed": final_metadata.get("total_questions", 0),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to abandon survey response (non-fatal)",
                extra={
                    "response_id": str(response_id),
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            if db is not None:
                db.rollback()
        finally:
            if db is not None:
                db.close()


# Backward compatibility: module-level functions using default instance
_default_persistence = AsyncPersistence()


async def persist_question_async(
    response_id: UUID, question_data: Dict[str, Any]
) -> None:
    """
    Persist a completed question to the database.

    This is a convenience function that delegates to the default AsyncPersistence instance.
    For testing or custom session management, use AsyncPersistence directly.
    """
    await _default_persistence.persist_question(response_id, question_data)


async def complete_response_async(
    response_id: UUID, final_metadata: Dict[str, Any]
) -> None:
    """
    Mark a survey response as completed.

    This is a convenience function that delegates to the default AsyncPersistence instance.
    For testing or custom session management, use AsyncPersistence directly.
    """
    await _default_persistence.complete_response(response_id, final_metadata)


async def abandon_response_async(
    response_id: UUID, final_metadata: Dict[str, Any]
) -> None:
    """
    Mark a survey response as abandoned.

    This is a convenience function that delegates to the default AsyncPersistence instance.
    For testing or custom session management, use AsyncPersistence directly.
    """
    await _default_persistence.abandon_response(response_id, final_metadata)
