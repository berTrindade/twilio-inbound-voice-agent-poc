"""Pluggable webhook submission handler.

Posts the collected survey answers as a generic JSON envelope to a configured
external webhook URL when the call ends. This is the extension
point for forwarding completed surveys to any HTTP endpoint (a workflow
automation tool, a data warehouse loader, an internal service, etc.).

Like every integration client in this codebase, it never raises: any network
error or non-2xx response is caught, logged, and surfaced as a
``SubmissionResult(success=False, ...)`` so it can never break the call.
"""

import logging
from typing import Any, Optional
from uuid import UUID

import requests

from ..handler import SurveySubmissionHandler
from ..types import FailureKind, MilestoneEvent, SubmissionResult

logger = logging.getLogger(__name__)

LOG_PREFIX = "[WebhookSubmission]"
SURVEY_ID = "webhook"


class WebhookSubmissionHandler(SurveySubmissionHandler):
    """Forwards final survey answers to a configured webhook URL when the call ends."""

    INTEGRATION_TYPE = "webhook_submission"
    SURVEY_ID = SURVEY_ID

    def __init__(
        self,
        webhook_url: str,
        *,
        response_id: Optional[UUID],
        repository: Any,
        token: str = "",
        timeout: float = 30.0,
    ):
        self.webhook_url = webhook_url
        self.response_id = response_id
        self.repository = repository
        self.token = token
        self.timeout = timeout

    @classmethod
    def from_config(
        cls, settings: Any, *, response_id: Optional[UUID], repository: Any
    ) -> "WebhookSubmissionHandler":
        return cls(
            webhook_url=settings.submission_webhook_url,
            response_id=response_id,
            repository=repository,
            token=settings.submission_webhook_token,
        )

    def survey_id(self) -> str:
        return self.SURVEY_ID

    def should_trigger(self, event: MilestoneEvent) -> bool:
        return event.event_type == "call_ended"

    async def submit(self, event: MilestoneEvent) -> SubmissionResult:
        answers = event.all_answers or {}
        answer_count = len(answers)
        payload = {
            "event_type": event.event_type,
            "response_id": str(self.response_id) if self.response_id else None,
            "survey_id": self.SURVEY_ID,
            "answers": answers,
            "answer_count": answer_count,
        }

        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            logger.warning(
                f"{LOG_PREFIX} Timeout posting to webhook",
                extra={"response_id": str(self.response_id)},
            )
            return SubmissionResult(
                success=False,
                survey_id=self.SURVEY_ID,
                error="timeout",
                failure_kind=FailureKind.BLOCKING,
            )
        except requests.exceptions.RequestException as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            logger.warning(
                f"{LOG_PREFIX} Failed to post to webhook",
                extra={
                    "response_id": str(self.response_id),
                    "error": str(e),
                    "status_code": status_code,
                },
            )
            return SubmissionResult(
                success=False,
                survey_id=self.SURVEY_ID,
                error=str(e),
                failure_kind=FailureKind.BLOCKING,
                status_code=status_code,
            )
        except Exception as e:
            logger.warning(
                f"{LOG_PREFIX} Unexpected error posting to webhook",
                extra={"response_id": str(self.response_id), "error": str(e)},
            )
            return SubmissionResult(
                success=False,
                survey_id=self.SURVEY_ID,
                error=str(e),
                failure_kind=FailureKind.BLOCKING,
            )

        logger.info(
            f"{LOG_PREFIX} Webhook submission delivered",
            extra={
                "response_id": str(self.response_id),
                "answer_count": answer_count,
                "status_code": response.status_code,
            },
        )
        return SubmissionResult(
            success=True,
            survey_id=self.SURVEY_ID,
            data={"answer_count": answer_count, "status_code": response.status_code},
            failure_kind=FailureKind.NONE,
        )
