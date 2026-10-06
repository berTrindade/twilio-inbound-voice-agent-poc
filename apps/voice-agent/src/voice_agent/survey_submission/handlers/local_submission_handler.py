"""Self-contained submission handler: the default when nothing external is wired up.

Instead of calling any external API, it records the collected survey answers to
the local database as an integration event when the call ends, so the dashboard
has something to display and the milestone pipeline is exercised end-to-end with
zero external dependencies.
"""

import logging
from typing import Any, Optional
from uuid import UUID

from ..handler import SurveySubmissionHandler
from ..types import FailureKind, MilestoneEvent, SubmissionResult

logger = logging.getLogger(__name__)

SURVEY_ID = "local"


class LocalSubmissionHandler(SurveySubmissionHandler):
    """Persists final survey answers locally; never calls an external service."""

    INTEGRATION_TYPE = "local_submission"
    SURVEY_ID = SURVEY_ID

    def __init__(self, response_id: Optional[UUID], repository: Any):
        self.response_id = response_id
        self.repository = repository

    @classmethod
    def from_config(
        cls, settings: Any, *, response_id: Optional[UUID], repository: Any
    ) -> "LocalSubmissionHandler":
        return cls(response_id=response_id, repository=repository)

    def survey_id(self) -> str:
        return self.SURVEY_ID

    def should_trigger(self, event: MilestoneEvent) -> bool:
        return event.event_type == "call_ended"

    async def submit(self, event: MilestoneEvent) -> SubmissionResult:
        answer_count = len(event.all_answers or {})
        if self.repository and self.response_id:
            try:
                self.repository.update_integration_event(
                    response_id=self.response_id,
                    integration_type=self.INTEGRATION_TYPE,
                    data={
                        "response": {
                            "success": True,
                            "answer_count": answer_count,
                            "answers": event.all_answers or {},
                        }
                    },
                )
            except Exception:
                logger.warning(
                    "[local_submission] persist failed (non-fatal)", exc_info=True
                )
        logger.info(
            "Local submission recorded",
            extra={"response_id": str(self.response_id), "answer_count": answer_count},
        )
        return SubmissionResult(
            success=True,
            survey_id=self.SURVEY_ID,
            data={"answer_count": answer_count},
            failure_kind=FailureKind.NONE,
        )
