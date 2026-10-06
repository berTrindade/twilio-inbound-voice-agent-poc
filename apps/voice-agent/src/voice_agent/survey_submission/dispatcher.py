"""
Milestone dispatcher -- the core of the survey submission engine.

Receives MilestoneEvents from the websocket handler and fans them out to every
registered SurveySubmissionHandler.  Handlers that return True from
should_trigger() are executed asynchronously so they never block the voice
conversation.
"""

import asyncio
import logging
from typing import Dict, List

from ..voice_ai.business_event_instrumentation import start_voice_business_span
from ..voice_ai.handoff_reasons import HandoffReason
from .handler import SurveySubmissionHandler
from .milestone_attrs import (
    milestone_outcome_from_result,
    milestone_type_from_survey_id,
)
from .types import FailureKind, MilestoneEvent, SubmissionResult
from ..voice_ai.pending_handoff_state import request_coach_handoff

logger = logging.getLogger(__name__)


class SurveyMilestoneDispatcher:
    """
    Central dispatcher that connects milestone events to survey submission handlers.

    Usage:
        dispatcher = SurveyMilestoneDispatcher()
        dispatcher.register(FirstSectionHandler(...))
        dispatcher.register(SecondSectionHandler(...))

        # Later, in the websocket loop:
        await dispatcher.on_milestone(event)

    Handlers are evaluated in registration order.  Each triggered handler runs
    as a fire-and-forget asyncio task so it does not block the caller.

    Results are stored internally and can be queried by other handlers that
    depend on earlier submissions, so a later section's handler can read the
    result an earlier section's handler produced.
    """

    def __init__(self) -> None:
        self._handlers: List[SurveySubmissionHandler] = []
        self._results: Dict[str, SubmissionResult] = {}
        self._submitted: set[str] = set()

    # -- registration ---------------------------------------------------------

    def register(self, handler: SurveySubmissionHandler) -> None:
        """Add a handler. Duplicate survey_id registrations are rejected."""
        sid = handler.survey_id()
        for existing in self._handlers:
            if existing.survey_id() == sid:
                logger.warning(
                    "Handler already registered, skipping",
                    extra={"survey_id": sid},
                )
                return
        self._handlers.append(handler)
        logger.info("Registered submission handler", extra={"survey_id": sid})

    # -- results access -------------------------------------------------------

    # -- event dispatch -------------------------------------------------------

    async def on_milestone(self, event: MilestoneEvent) -> List[SubmissionResult]:
        """
        Evaluate all handlers against the event and fire those that match.

        Each matching handler is executed concurrently via asyncio.  Results are
        collected, stored, and returned so callers can react if needed.

        Handlers that have already submitted successfully for this call are
        skipped to prevent duplicate submissions.

        Args:
            event: The milestone event to broadcast.

        Returns:
            List of SubmissionResults from handlers that fired (may be empty).
        """
        triggered: List[SurveySubmissionHandler] = []

        for handler in self._handlers:
            sid = handler.survey_id()

            if sid in self._submitted:
                continue

            try:
                if handler.should_trigger(event):
                    triggered.append(handler)
            except Exception:
                logger.error(
                    "Error in should_trigger",
                    extra={"survey_id": sid},
                    exc_info=True,
                )

        if not triggered:
            return []

        logger.info(
            "Dispatching milestone to handlers",
            extra={
                "event_type": event.event_type,
                "question_id": event.question_id,
                "source": event.source,
                "previous_source": event.previous_source,
                "triggered_count": len(triggered),
                "triggered_surveys": [h.survey_id() for h in triggered],
            },
        )

        tasks = [self._execute_handler(h, event) for h in triggered]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        return list(results)

    # -- internal helpers -----------------------------------------------------

    async def _execute_handler(
        self,
        handler: SurveySubmissionHandler,
        event: MilestoneEvent,
    ) -> SubmissionResult:
        """Run a single handler, store its result, and handle errors."""
        sid = handler.survey_id()
        with start_voice_business_span(
            event="milestone",
            call_sid=event.call_sid or "",
            correlation_id=event.correlation_id or "",
            response_id=str(event.response_id) if event.response_id else "",
        ) as span:
            span.set_attribute(
                "voice_survey.milestone_type", milestone_type_from_survey_id(sid)
            )
            try:
                result = await handler.submit(event)

                self._results[sid] = result
                if result.success:
                    self._submitted.add(sid)

                span.set_attribute(
                    "voice_survey.outcome", milestone_outcome_from_result(result)
                )
                logger.info(
                    "Handler submission completed",
                    extra={
                        "survey_id": sid,
                        "success": result.success,
                        "error": result.error,
                    },
                )
                self._record_failure(handler, result)
                self._maybe_request_handoff(result, event)
                return result

            except Exception as e:
                span.set_attribute("voice_survey.outcome", "failed")
                logger.error(
                    "Handler submission failed with exception",
                    extra={
                        "survey_id": sid,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )

                error_result = SubmissionResult(
                    success=False,
                    survey_id=sid,
                    error=f"{type(e).__name__}: {e}",
                    failure_kind=FailureKind.BLOCKING,
                )
                self._results[sid] = error_result
                self._record_failure(handler, error_result)
                self._maybe_request_handoff(error_result, event)
                return error_result

    def _record_failure(
        self, handler: SurveySubmissionHandler, result: SubmissionResult
    ) -> None:
        """Persist a failed submission as an integration event.

        Handlers write their own rich record on the happy path, so this runs
        only on failures: without it a failed submission leaves nothing behind
        and the dashboard cannot tell a webhook that never fired from one that
        fired and failed. A "Skipped:" result is a legitimate non-event, not a
        failure, so it is not recorded.
        """
        if milestone_outcome_from_result(result) != "failed":
            return
        repository = getattr(handler, "repository", None)
        response_id = getattr(handler, "response_id", None)
        integration_type = getattr(handler, "INTEGRATION_TYPE", "")
        if not (repository and response_id and integration_type):
            return
        # update_integration_event swallows and logs its own failures, so a
        # database problem here never turns into a second failure on the call.
        repository.update_integration_event(
            response_id=response_id,
            integration_type=integration_type,
            data={
                "response": {
                    "success": False,
                    "error": result.error,
                    "blocking": result.failure_kind == FailureKind.BLOCKING,
                    "status_code": result.status_code,
                }
            },
        )

    def _maybe_request_handoff(
        self, result: SubmissionResult, event: MilestoneEvent
    ) -> None:
        """Request a coach handoff if the result indicates a blocking failure.

        A background submission that fails technically is a system error, so the
        coach picks the call up rather than the caller hitting a dead end.
        """
        if result.failure_kind == FailureKind.BLOCKING:
            request_coach_handoff(
                event.call_sid,
                reason=f"{result.survey_id}_failed",
                whisper_text=(
                    f"Handoff from the voice agent: the {result.survey_id} step "
                    f"failed with a system error ({result.error or 'unknown'}). "
                    f"Please take over and finish the remaining steps manually."
                ),
                trigger=HandoffReason.SYSTEM_ERROR,
            )
