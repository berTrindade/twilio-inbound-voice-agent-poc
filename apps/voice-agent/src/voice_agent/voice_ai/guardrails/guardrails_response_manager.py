"""Canned responses for guardrail topics.

The wording here is deliberately generic and jurisdiction-neutral. Any real
deployment must replace it with text reviewed for its own regulatory and
clinical context, including the correct emergency and crisis-line numbers
for the regions it serves. What this module demonstrates is the mechanism:
a topic classifier short-circuits normal survey handling and the agent reads
a fixed line instead of anything a model generated.
"""

from typing import Optional


GUARDRAIL_TOPIC_RESPONSES = {
    "self_harm": (
        "I'm sorry you're going through this, and I want to make sure you get proper support. "
        "I'm not able to help with this myself. If you're in immediate danger, please hang up and "
        "contact your local emergency services. Would you like me to put you through to a person now?"
    ),
    "harm_to_others": (
        "It sounds like you're feeling overwhelmed right now, and this isn't something I can help "
        "with. If anyone is in immediate danger, please hang up and contact your local emergency "
        "services. Would you like me to put you through to a person now?"
    ),
    "medical_dietary": (
        "I'm not able to give medical advice. For anything about diagnosis, treatment or "
        "medication, please speak to a qualified professional. Shall we carry on with the "
        "questions, or would you rather talk to a person?"
    ),
}


def get_guardrail_response(
    topic_name: str,
    first_name: Optional[str] = None,
) -> str:
    """
    Return the canned response for a guardrail topic.
    """
    msg = GUARDRAIL_TOPIC_RESPONSES.get(topic_name, "")

    # (Optional future hook for name personalization)
    if first_name and "{First Name}" in msg:
        return msg.replace("{First Name}", first_name)

    return msg


def build_guardrail_messages_for_prompt() -> str:
    """
    Build a formatted string of guardrail messages for LLM prompts.
    Ensures a single source of truth.
    """
    parts = ["Exact predefined responses:\n"]

    for topic, message in GUARDRAIL_TOPIC_RESPONSES.items():
        parts.append(f'- {topic}:\n"{message}"\n')

    return "\n".join(parts).strip()
