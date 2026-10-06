"""Abstract base class for survey submission handlers (Strategy pattern)."""

from abc import ABC, abstractmethod

from .types import MilestoneEvent, SubmissionResult


class SurveySubmissionHandler(ABC):
    """
    Contract that every survey submission plugin must implement.

    To add a new survey submission, create a class that inherits from this ABC
    and implement the three methods. Then register it with the
    SurveyMilestoneDispatcher.

    The handler is fully self-contained: it decides *when* to fire, *what* data
    to extract, and *how* to submit it.  The core dispatcher never needs to
    change when handlers are added or removed.
    """

    # Dashboard integration key for this handler's outcomes (e.g.
    # "local_submission"), written alongside the persisted integration event.
    INTEGRATION_TYPE: str = ""

    @abstractmethod
    def survey_id(self) -> str:
        """
        Unique identifier for this survey (e.g. the survey definition ID).

        Used by the dispatcher to store results and prevent duplicate submissions
        within the same call.
        """
        ...

    @abstractmethod
    def should_trigger(self, event: MilestoneEvent) -> bool:
        """
        Decide whether this handler should fire for the given milestone event.

        This is the extension point for any trigger strategy:
        - Question-based: trigger when a specific question is answered.
        - Source transition: trigger when moving from one survey section to another.
        - Time-based: trigger after N seconds of call time.
        - Composite: combine multiple conditions.

        Args:
            event: The milestone event to evaluate.

        Returns:
            True if the handler should submit now, False otherwise.
        """
        ...

    @abstractmethod
    async def submit(self, event: MilestoneEvent) -> SubmissionResult:
        """
        Execute the survey submission to the backend.

        Responsible for:
        1. Extracting relevant answers from event.all_answers
        2. Mapping Voice AI question IDs to backend question IDs
        3. Calling the backend API (typically 3-step: start -> answer -> complete)
        4. Returning the result

        This runs as an async task so it does not block the voice conversation.

        Args:
            event: The milestone event that triggered this submission.

        Returns:
            SubmissionResult with success/failure status and any backend data.
        """
        ...
