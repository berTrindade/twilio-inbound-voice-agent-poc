from dataclasses import dataclass
from enum import Enum


class PromptEndMode(str, Enum):
    CONTINUE = "continue"
    SURVEY_COMPLETED = "survey_completed"
    COACH_HANDOFF_STARTED = "coach_handoff_started"
    USER_ENDED_SESSION = "user_ended_session"
    ALREADY_TERMINAL = "already_terminal"

    @property
    def completion_reason(self) -> str | None:
        if self == PromptEndMode.SURVEY_COMPLETED:
            return "all_questions_answered"
        if self == PromptEndMode.COACH_HANDOFF_STARTED:
            return "coach_handoff"
        if self == PromptEndMode.USER_ENDED_SESSION:
            return "user_ended_session"
        if self == PromptEndMode.ALREADY_TERMINAL:
            return "already_terminal"
        return None


@dataclass(slots=True, frozen=True)
class PromptHandlingResult:
    end_mode: PromptEndMode
    active_big_model_node: str | None

    @staticmethod
    def continue_(node: str | None) -> "PromptHandlingResult":
        return PromptHandlingResult(PromptEndMode.CONTINUE, node)

    @staticmethod
    def survey_completed(node: str | None) -> "PromptHandlingResult":
        return PromptHandlingResult(PromptEndMode.SURVEY_COMPLETED, node)

    @staticmethod
    def coach_handoff_started(node: str | None) -> "PromptHandlingResult":
        return PromptHandlingResult(PromptEndMode.COACH_HANDOFF_STARTED, node)

    @staticmethod
    def user_ended_session(node: str | None) -> "PromptHandlingResult":
        return PromptHandlingResult(PromptEndMode.USER_ENDED_SESSION, node)

    @staticmethod
    def already_terminal(node: str | None) -> "PromptHandlingResult":
        return PromptHandlingResult(PromptEndMode.ALREADY_TERMINAL, node)
