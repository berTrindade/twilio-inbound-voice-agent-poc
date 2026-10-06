"""Single source of truth for coach-handoff reason codes, sources, the
node->reason map, and the canonical coach-whisper text.

`voice_survey.handoff_started` carries three reason-related attributes:
  - trigger              the reason code (the "why") -> HandoffReason.*
  - handoff_source       the deterministic mechanism that initiated it
                         -> HandoffSource.*
  - handoff_whisper_text the coach whisper, always attached (may contain caller
                         content for big-model handoffs; tagged accordingly)

Splitting "why" from "how" is what makes the handoff funnel answerable: a
caller asking for a human and the survey routing to one both end in a warm
transfer, but only one of them is a failure of the agent.
"""

from typing import Final, Optional


class HandoffReason:
    """`voice_survey.trigger` values -- the "why" of a handoff."""

    COACH_REQUESTED: Final = "coach_requested"  # caller asked for a human
    SURVEY_ROUTED: Final = "survey_routed"  # survey rule routed (default)
    AGENT_DECISION: Final = "agent_decision"  # small or big model decided on its own
    USER_FRUSTRATION: Final = (
        "user_frustration"  # agent inferred frustration / the bot isn't working
    )
    AGENT_CONFUSION: Final = "agent_confusion"  # model could not make progress
    COMPLETED_SURVEY: Final = "completed_survey"  # survey finished, warm transfer
    SYSTEM_ERROR: Final = "system_error"  # a step failed technically
    OTHER: Final = "other"


class HandoffSource:
    """`voice_survey.handoff_source` values -- the deterministic mechanism."""

    CALLER: Final = "caller"  # caller explicitly asked for a human
    SURVEY: Final = "survey"  # the survey definition routed to a coach
    AGENT: Final = "agent"  # small or big model decided on its own
    SYSTEM: Final = "system"  # system / error driven


# Handover node id -> reason, for surveys that route to a coach from a named
# node. The shipped demo survey has no handover nodes, so this is empty and
# every survey-routed handoff reports SURVEY_ROUTED. A survey that does hand
# off maps its node ids here to get a specific code in the funnel, e.g.
# {"TRANSFER_TO_COACH_UNDERAGE_V1": HandoffReason.SURVEY_ROUTED}.
HANDOVER_NODE_REASONS: Final[dict[str, str]] = {}


def reason_for_node(node_id: str) -> str:
    """Reason code for a survey handover node, defaulting to SURVEY_ROUTED."""
    return HANDOVER_NODE_REASONS.get(node_id or "", HandoffReason.SURVEY_ROUTED)


# Model `handover_reason` -> (trigger, handoff_source). Both the small interpreter
# and the big model lump every coach handover into one ``handover_to_coach``
# action; the ``handover_reason`` field disambiguates the "why" across the full
# whisper-classification vocabulary so the funnel can tell a caller-initiated
# handoff from the various agent-inferred ones. Only an explicit request is
# attributed to the CALLER; the rest are AGENT-sourced.
HANDOVER_REQUEST_REASONS: Final = {
    "explicit_request": (HandoffReason.COACH_REQUESTED, HandoffSource.CALLER),
    "frustration": (HandoffReason.USER_FRUSTRATION, HandoffSource.AGENT),
    "agent_confusion": (HandoffReason.AGENT_CONFUSION, HandoffSource.AGENT),
    "agent_decision": (HandoffReason.AGENT_DECISION, HandoffSource.AGENT),
    "other": (HandoffReason.OTHER, HandoffSource.AGENT),
}

# Fallback when the model omits the field or returns "none"/an unknown value:
# it chose to hand off but didn't tell us why, so record it as an agent decision.
_DEFAULT_HANDOVER_REQUEST: Final = (HandoffReason.AGENT_DECISION, HandoffSource.AGENT)


def reason_for_handover_request(handover_reason: Optional[str]) -> tuple[str, str]:
    """(trigger, handoff_source) for a small-model coach handover, keyed by the
    interpreter's ``handover_reason``. Unknown/missing -> AGENT_DECISION/AGENT."""
    return HANDOVER_REQUEST_REASONS.get(
        handover_reason or "", _DEFAULT_HANDOVER_REQUEST
    )


# Canonical coach-whisper text for deterministic handoffs (single source; the
# websocket_helpers wrappers return these).
DEFAULT_HANDOFF_WHISPER: Final = "This is a handoff from the voice agent"
COMPLETED_SURVEY_HANDOFF_WHISPER: Final = (
    "This is a completed survey from the voice agent"
)
