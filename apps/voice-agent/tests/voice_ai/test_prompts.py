"""Tests for prompt builders."""

from voice_agent.voice_ai.prompts import (
    build_big_model_user_prompt,
    build_small_model_user_prompt,
)


def _skippable_email_node():
    return {
        "id": "COACHING_EMAIL_V1",
        "type": "free_text",
        "text": "If you have one, what's your email address? You can spell it, or say skip.",
        "skippable": True,
        "validation": [
            {
                "kind": "regex",
                "pattern": r"^[\w\.\-\+]+@[\w\.-]+\.\w{2,}$",
            }
        ],
    }


def _required_email_node():
    node = _skippable_email_node()
    node.pop("skippable")
    return node


def test_small_model_prompt_includes_skippable_block_for_skippable_node():
    """Small model prompt should emit skippable guidance for skippable nodes."""
    prompt = build_small_model_user_prompt(
        node=_skippable_email_node(),
        user_text="I don't have an email address.",
        answers={},
        conversation_history=[],
    )

    compact_prompt = prompt.replace(" ", "")

    assert "This question is optional/skippable." in prompt
    assert "answer.value=null" in compact_prompt
    assert "JSON null" in prompt
    assert "placeholder strings" in prompt


def test_small_model_prompt_does_not_include_generic_skippable_block_for_required_node():
    """Required nodes should not emit the generic skippable-question block."""
    prompt = build_small_model_user_prompt(
        node=_required_email_node(),
        user_text="john@example.com",
        answers={},
        conversation_history=[],
    )

    assert "This question is optional/skippable." not in prompt


def test_big_model_prompt_includes_skippable_block_for_skippable_node():
    """Big model prompt should emit skippable guidance for skippable nodes."""
    prompt = build_big_model_user_prompt(
        node=_skippable_email_node(),
        question_id="COACHING_EMAIL_V1",
        answers={},
        user_text="I don't have an email address.",
        conversation_history=[],
    )

    compact_prompt = prompt.replace(" ", "")

    assert "SKIPPABLE QUESTION RULE" in prompt
    assert "record JSON null" in prompt
    assert '"value":null' in compact_prompt
    assert "placeholder strings" in prompt


def test_big_model_prompt_does_not_include_skippable_block_for_required_node():
    """Required nodes should not emit the big-model skippable-question block."""
    prompt = build_big_model_user_prompt(
        node=_required_email_node(),
        question_id="COACHING_EMAIL_V1",
        answers={},
        user_text="john@example.com",
        conversation_history=[],
    )

    assert "SKIPPABLE QUESTION RULE" not in prompt
