"""Tests for SurveyEngine module."""

import pytest
from voice_agent.voice_ai.survey_engine.engine import SurveyEngine


class TestSurveyEngineInitialization:
    """Tests for SurveyEngine initialization."""

    def test_init_with_list_format(self):
        """Should initialize with survey as list of nodes."""
        survey = [
            {"id": "q1", "type": "single_choice", "text": "Question 1"},
            {"id": "q2", "type": "free_text", "text": "Question 2"},
        ]
        engine = SurveyEngine(survey, "q1")
        assert engine.current_id == "q1"
        assert "q1" in engine.nodes
        assert "q2" in engine.nodes

    def test_init_with_dict_with_nodes_list(self):
        """Should initialize with survey as dict with nodes list."""
        survey = {
            "title": "Test Survey",
            "nodes": [
                {"id": "q1", "type": "single_choice", "text": "Question 1"},
                {"id": "q2", "type": "free_text", "text": "Question 2"},
            ],
        }
        engine = SurveyEngine(survey, "q1")
        assert engine.current_id == "q1"
        assert "q1" in engine.nodes

    def test_init_with_dict_with_nodes_dict(self):
        """Should initialize with survey as dict with nodes as dict."""
        survey = {
            "title": "Test Survey",
            "nodes": {
                "q1": {"id": "q1", "type": "single_choice", "text": "Question 1"},
                "q2": {"id": "q2", "type": "free_text", "text": "Question 2"},
            },
        }
        engine = SurveyEngine(survey, "q1")
        assert engine.current_id == "q1"
        assert "q1" in engine.nodes

    def test_init_sets_empty_answers(self):
        """Should initialize with empty answers dict."""
        survey = [{"id": "q1", "type": "single_choice"}]
        engine = SurveyEngine(survey, "q1")
        assert engine.answers == {}

    def test_init_sets_nudge_count_to_zero(self):
        """Should initialize nudge_count to zero."""
        survey = [{"id": "q1", "type": "single_choice"}]
        engine = SurveyEngine(survey, "q1")
        assert engine.nudge_count == 0

    def test_init_with_invalid_structure_raises(self):
        """Should raise error for unsupported survey structure."""
        with pytest.raises(ValueError, match="Unsupported survey structure"):
            SurveyEngine("invalid", "q1")


class TestSurveyEngineGetNode:
    """Tests for get_node and _get methods."""

    @pytest.fixture
    def engine(self):
        survey = [
            {"id": "q1", "type": "single_choice", "text": "Question 1"},
            {"id": "q2", "type": "free_text", "text": "Question 2"},
        ]
        return SurveyEngine(survey, "q1")

    def test_get_node_returns_node(self, engine):
        """Should return node by id."""
        node = engine.get_node("q1")
        assert node["id"] == "q1"
        assert node["type"] == "single_choice"

    def test_get_node_raises_for_missing(self, engine):
        """Should raise KeyError for missing node."""
        with pytest.raises(KeyError, match="Node not found: q999"):
            engine.get_node("q999")

    def test_private_get_returns_none_for_missing(self, engine):
        """_get should return None for missing node."""
        assert engine._get("q999") is None

    def test_private_get_returns_none_for_none_id(self, engine):
        """_get should return None when id is None."""
        assert engine._get(None) is None


class TestSurveyEngineAdvanceToInteractive:
    """Tests for advance_to_interactive method."""

    def test_stops_at_single_choice(self):
        """Should stop at single_choice node."""
        survey = [
            {
                "id": "q1",
                "type": "single_choice",
                "text": "Choose one",
                "next_id": "q2",
            },
        ]
        engine = SurveyEngine(survey, "q1")
        spoken, current, _, _ = engine.advance_to_interactive()
        assert current == "q1"
        assert spoken == ""

    def test_stops_at_multi_choice(self):
        """Should stop at multi_choice node."""
        survey = [{"id": "q1", "type": "multi_choice", "text": "Choose many"}]
        engine = SurveyEngine(survey, "q1")
        _, current, _, _ = engine.advance_to_interactive()
        assert current == "q1"

    def test_stops_at_yes_no(self):
        """Should stop at yes_no node."""
        survey = [{"id": "q1", "type": "yes_no", "text": "Yes or no?"}]
        engine = SurveyEngine(survey, "q1")
        _, current, _, _ = engine.advance_to_interactive()
        assert current == "q1"

    def test_stops_at_numeric(self):
        """Should stop at numeric node."""
        survey = [{"id": "q1", "type": "numeric", "text": "Enter a number"}]
        engine = SurveyEngine(survey, "q1")
        _, current, _, _ = engine.advance_to_interactive()
        assert current == "q1"

    def test_stops_at_free_text(self):
        """Should stop at free_text node."""
        survey = [{"id": "q1", "type": "free_text", "text": "Enter text"}]
        engine = SurveyEngine(survey, "q1")
        _, current, _, _ = engine.advance_to_interactive()
        assert current == "q1"

    def test_skips_narration_and_collects_text(self):
        """Should skip narration nodes and collect their text."""
        survey = [
            {"id": "intro", "type": "narration", "text": "Welcome!", "next_id": "q1"},
            {"id": "q1", "type": "single_choice", "text": "Choose"},
        ]
        engine = SurveyEngine(survey, "intro")
        spoken, current, _, _ = engine.advance_to_interactive()
        assert current == "q1"
        assert "Welcome!" in spoken

    def test_skips_interstitial_and_collects_text(self):
        """Should skip interstitial nodes and collect their text."""
        survey = [
            {
                "id": "wait",
                "type": "interstitial",
                "text": "Please wait",
                "next_id": "q1",
            },
            {"id": "q1", "type": "single_choice", "text": "Choose"},
        ]
        engine = SurveyEngine(survey, "wait")
        spoken, current, _, _ = engine.advance_to_interactive()
        assert current == "q1"
        assert "Please wait" in spoken

    def test_skips_api_call_and_stores_expected_response(self):
        """Should skip api_call nodes and store second expected response (safe fallback)."""
        survey = [
            {
                "id": "api_check",
                "type": "api_call",
                "text": "Checking...",
                "api": {"expected_responses": ["ELIGIBLE", "NOT_ELIGIBLE"]},
                "next_id": "q1",
            },
            {"id": "q1", "type": "single_choice", "text": "Choose"},
        ]
        engine = SurveyEngine(survey, "api_check")
        spoken, current, _, _ = engine.advance_to_interactive()
        assert current == "q1"
        assert "Checking..." in spoken
        assert engine.answers["api_check"] == "NOT_ELIGIBLE"

    def test_accumulates_multiple_narrations(self):
        """Should accumulate text from multiple narration nodes."""
        survey = [
            {"id": "n1", "type": "narration", "text": "First.", "next_id": "n2"},
            {"id": "n2", "type": "narration", "text": "Second.", "next_id": "q1"},
            {"id": "q1", "type": "single_choice", "text": "Choose"},
        ]
        engine = SurveyEngine(survey, "n1")
        spoken, current, _, _ = engine.advance_to_interactive()
        assert current == "q1"
        assert "First." in spoken
        assert "Second." in spoken

    def test_skips_node_when_ask_if_false(self):
        """Should skip node when ask_if evaluates to False."""
        survey = [
            {
                "id": "conditional",
                "type": "narration",
                "text": "Should skip",
                "ask_if": {"answered": {"question_id": "prev", "in": ["yes"]}},
                "next_id": "q1",
            },
            {"id": "q1", "type": "single_choice", "text": "Choose"},
        ]
        engine = SurveyEngine(survey, "conditional")
        engine.answers["prev"] = "no"  # ask_if will be False
        spoken, current, _, _ = engine.advance_to_interactive()
        assert current == "q1"
        assert "Should skip" not in spoken

    def test_shows_node_when_ask_if_true(self):
        """Should show node when ask_if evaluates to True."""
        survey = [
            {
                "id": "conditional",
                "type": "narration",
                "text": "Should show",
                "ask_if": {"answered": {"question_id": "prev", "in": ["yes"]}},
                "next_id": "q1",
            },
            {"id": "q1", "type": "single_choice", "text": "Choose"},
        ]
        engine = SurveyEngine(survey, "conditional")
        engine.answers["prev"] = "yes"  # ask_if will be True
        spoken, current, _, _ = engine.advance_to_interactive()
        assert current == "q1"
        assert "Should show" in spoken

    def test_unmet_ask_if_skips_handover_and_proceeds(self):
        """A handover node whose ask_if is not satisfied is skipped: the flow
        plays the reassurance interstitial and carries on to the next question
        instead of handing off to a coach."""
        survey = [
            {
                "id": "HANDOVER_V1",
                "type": "handover_to_coach",
                "text": "Handing you to a coach",
                "next_id": "PROCEED_V1",
                "ask_if": {
                    "api_in": {
                        "question_id": "CHECK_V1",
                        "values": ["BLOCKED"],
                    }
                },
            },
            {
                "id": "PROCEED_V1",
                "type": "interstitial",
                "text": "No problem. I've noted that and we can carry on.",
                "next_id": "Q_NEXT_V1",
                "ask_if": {
                    "api_in": {
                        "question_id": "CHECK_V1",
                        "values": ["UNVERIFIED"],
                    }
                },
            },
            {
                "id": "Q_NEXT_V1",
                "type": "single_choice",
                "text": "Which option suits you?",
            },
        ]
        engine = SurveyEngine(survey, "HANDOVER_V1")
        engine.answers["CHECK_V1"] = "UNVERIFIED"

        spoken, current, _, _ = engine.advance_to_interactive()

        assert current == "Q_NEXT_V1"
        assert "we can carry on" in spoken
        assert engine.pending_handover_context is None

    def test_resets_nudge_count_on_interactive(self):
        """Should reset nudge_count when reaching interactive node."""
        survey = [{"id": "q1", "type": "single_choice", "text": "Choose"}]
        engine = SurveyEngine(survey, "q1")
        engine.nudge_count = 5
        engine.advance_to_interactive()
        assert engine.nudge_count == 0

    def test_handles_missing_next_id(self):
        """Should handle node without next_id gracefully."""
        survey = [
            {"id": "narration", "type": "narration", "text": "End"},
        ]
        engine = SurveyEngine(survey, "narration")
        spoken, current, _, _ = engine.advance_to_interactive()
        assert spoken == "End"
        assert current == ""

    def test_detects_cycle_and_breaks(self):
        """Should detect cycles and break to prevent infinite loop."""
        survey = [
            {"id": "n1", "type": "narration", "text": "Loop", "next_id": "n1"},
        ]
        engine = SurveyEngine(survey, "n1")
        # This should not hang
        spoken, current, _, _ = engine.advance_to_interactive()
        assert "Loop" in spoken


class TestSurveyEngineValidate:
    """Tests for validate method."""

    def test_validates_single_choice(self):
        """Should validate single choice answer."""
        survey = [
            {
                "id": "q1",
                "type": "single_choice",
                "options": [{"id": "yes", "value": "yes"}, {"id": "no", "value": "no"}],
            }
        ]
        engine = SurveyEngine(survey, "q1")
        result = engine.validate("q1", "yes")
        assert result["valid"] is True
        assert result["normalized"] == "yes"

    def test_validates_free_text(self):
        """Should validate free text answer."""
        survey = [{"id": "q1", "type": "free_text"}]
        engine = SurveyEngine(survey, "q1")
        result = engine.validate("q1", "Hello World")
        assert result["valid"] is True
        assert result["normalized"] == "Hello World"

    def test_invalid_answer_returns_reason(self):
        """Should return reason for invalid answer."""
        survey = [{"id": "q1", "type": "free_text"}]
        engine = SurveyEngine(survey, "q1")
        result = engine.validate("q1", "")
        assert result["valid"] is False
        assert result["reason"] == "empty_text"

    def test_unknown_node_returns_error(self):
        """Should return error for unknown node."""
        survey = [{"id": "q1", "type": "free_text"}]
        engine = SurveyEngine(survey, "q1")
        with pytest.raises(KeyError):
            engine.validate("unknown", "text")


class TestSurveyEngineRecord:
    """Tests for record method."""

    @pytest.fixture
    def engine_with_routing(self):
        """Engine with single_choice routing based on options."""
        survey = [
            {
                "id": "q1",
                "type": "single_choice",
                "options": [
                    {"id": "yes", "value": "yes", "next_id": "q_yes"},
                    {"id": "no", "value": "no", "next_id": "q_no"},
                ],
                "next_id": "q_default",
            },
            {"id": "q_yes", "type": "free_text", "text": "Yes branch"},
            {"id": "q_no", "type": "free_text", "text": "No branch"},
            {"id": "q_default", "type": "free_text", "text": "Default branch"},
        ]
        return SurveyEngine(survey, "q1")

    def test_stores_answer(self):
        """Should store answer in answers dict."""
        survey = [{"id": "q1", "type": "free_text", "next_id": "q2"}]
        engine = SurveyEngine(survey, "q1")
        engine.record("q1", "My answer")
        assert engine.answers["q1"] == "My answer"

    def test_advances_to_next_id(self):
        """Should advance current_id to next_id."""
        survey = [
            {"id": "q1", "type": "free_text", "next_id": "q2"},
            {"id": "q2", "type": "free_text"},
        ]
        engine = SurveyEngine(survey, "q1")
        engine.record("q1", "answer")
        assert engine.current_id == "q2"

    def test_single_choice_routing_by_option(self, engine_with_routing):
        """Should route to option's next_id for single_choice."""
        engine_with_routing.record("q1", "yes")
        assert engine_with_routing.current_id == "q_yes"

    def test_single_choice_routing_different_option(self, engine_with_routing):
        """Should route correctly for different option."""
        engine_with_routing.record("q1", "no")
        assert engine_with_routing.current_id == "q_no"

    def test_single_choice_fallback_to_default(self):
        """Should fallback to node's next_id when option has no next_id."""
        survey = [
            {
                "id": "q1",
                "type": "single_choice",
                "options": [
                    {"id": "yes", "value": "yes"},  # no next_id
                    {"id": "no", "value": "no"},
                ],
                "next_id": "q_default",
            },
            {"id": "q_default", "type": "free_text"},
        ]
        engine = SurveyEngine(survey, "q1")
        engine.record("q1", "yes")
        assert engine.current_id == "q_default"

    def test_skipped_skippable_email_records_null_and_advances(self):
        """Skipped optional email should store None and advance."""
        survey = [
            {
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
                "next_id": "COACHING_ADDRESS_V1",
            },
            {
                "id": "COACHING_ADDRESS_V1",
                "type": "free_text",
                "text": "What's your address?",
            },
        ]
        engine = SurveyEngine(survey, "COACHING_EMAIL_V1")

        validation_result = engine.validate("COACHING_EMAIL_V1", None)
        assert validation_result["valid"] is True
        assert validation_result["normalized"] is None

        engine.record("COACHING_EMAIL_V1", validation_result["normalized"])

        assert engine.answers["COACHING_EMAIL_V1"] is None
        assert engine.current_id == "COACHING_ADDRESS_V1"

        spoken, current, _, _ = engine.advance_to_interactive()

        assert spoken == ""
        assert current == "COACHING_ADDRESS_V1"


class TestSurveyEngineMultiChoiceLogic:
    """Tests for _apply_multi_choice_logic method."""

    def test_when_contains_any_matches(self):
        """Should route when any selected value matches when_contains_any."""
        survey = [
            {
                "id": "q1",
                "type": "multi_choice",
                "options": [{"value": "a"}, {"value": "b"}, {"value": "c"}],
                "logic": [
                    {"when_contains_any": ["a", "b"], "next_id": "branch_ab"},
                ],
                "next_id": "default",
            }
        ]
        engine = SurveyEngine(survey, "q1")
        engine.record("q1", ["a", "c"])  # 'a' matches when_contains_any
        assert engine.current_id == "branch_ab"

    def test_when_contains_any_no_match(self):
        """Should use default when no when_contains_any matches."""
        survey = [
            {
                "id": "q1",
                "type": "multi_choice",
                "options": [{"value": "a"}, {"value": "b"}, {"value": "c"}],
                "logic": [
                    {"when_contains_any": ["x", "y"], "next_id": "branch_xy"},
                ],
                "next_id": "default",
            }
        ]
        engine = SurveyEngine(survey, "q1")
        engine.record("q1", ["a", "c"])
        assert engine.current_id == "default"

    def test_otherwise_next_id_fallback(self):
        """Should use otherwise_next_id as fallback."""
        survey = [
            {
                "id": "q1",
                "type": "multi_choice",
                "options": [{"value": "a"}, {"value": "b"}],
                "logic": [
                    {"when_contains_any": ["x"], "next_id": "branch_x"},
                    {"otherwise_next_id": "fallback"},
                ],
                "next_id": "default",
            }
        ]
        engine = SurveyEngine(survey, "q1")
        engine.record("q1", ["a"])  # no match for when_contains_any
        assert engine.current_id == "fallback"

    def test_when_contains_any_takes_precedence(self):
        """when_contains_any should take precedence over otherwise_next_id."""
        survey = [
            {
                "id": "q1",
                "type": "multi_choice",
                "options": [{"value": "a"}, {"value": "b"}],
                "logic": [
                    {"otherwise_next_id": "fallback"},
                    {"when_contains_any": ["a"], "next_id": "branch_a"},
                ],
                "next_id": "default",
            }
        ]
        engine = SurveyEngine(survey, "q1")
        engine.record("q1", ["a"])
        assert engine.current_id == "branch_a"


class TestSurveyEngineShouldEscalate:
    """Tests for should_escalate method."""

    @pytest.fixture
    def engine(self):
        survey = [{"id": "q1", "type": "free_text"}]
        return SurveyEngine(survey, "q1")

    def test_escalate_on_change_keyword(self, engine):
        """Should escalate when 'change' keyword detected."""
        assert engine.should_escalate("I want to change my answer", 0.9, True) is True

    def test_escalate_on_previous_keyword(self, engine):
        """Should escalate when 'previous' keyword detected."""
        assert engine.should_escalate("go to previous question", 0.9, True) is True

    def test_escalate_on_go_back_keyword(self, engine):
        """Should escalate when 'go back' keyword detected."""
        assert engine.should_escalate("can we go back", 0.9, True) is True

    def test_escalate_on_update_keyword(self, engine):
        """Should escalate when 'update' keyword detected."""
        assert engine.should_escalate("I need to update that", 0.9, True) is True

    def test_escalate_after_two_low_confidence(self, engine):
        """Should escalate after two consecutive low confidence responses."""
        # First low confidence
        assert engine.should_escalate("unclear", 0.3, True) is False
        # Second low confidence
        assert engine.should_escalate("still unclear", 0.4, True) is True

    def test_escalate_after_two_invalid(self, engine):
        """Should escalate after two consecutive invalid responses."""
        # First invalid
        assert engine.should_escalate("invalid", 0.8, False) is False
        # Second invalid
        assert engine.should_escalate("still invalid", 0.8, False) is True

    def test_resets_nudge_on_valid_high_confidence(self, engine):
        """Should reset nudge count on valid high confidence response."""
        engine.nudge_count = 1
        engine.should_escalate("good answer", 0.9, True)
        assert engine.nudge_count == 0

    def test_mixed_low_conf_then_invalid(self, engine):
        """Should count both low confidence and invalid toward escalation."""
        # Low confidence
        assert engine.should_escalate("unclear", 0.3, True) is False
        assert engine.nudge_count == 1
        # Invalid (but high confidence)
        assert engine.should_escalate("invalid", 0.8, False) is True

    def test_case_insensitive_keyword_detection(self, engine):
        """Should detect keywords case insensitively."""
        assert engine.should_escalate("CHANGE my answer", 0.9, True) is True
        assert engine.should_escalate("GO BACK please", 0.9, True) is True


class TestSurveyEngineSnapshot:
    """Tests for snapshot method."""

    def test_snapshot_includes_current_id(self):
        """Snapshot should include current_id."""
        survey = [{"id": "q1", "type": "free_text", "next_id": "q2"}]
        engine = SurveyEngine(survey, "q1")
        snapshot = engine.snapshot()
        assert snapshot["current_id"] == "q1"

    def test_snapshot_includes_answers(self):
        """Snapshot should include answers."""
        survey = [{"id": "q1", "type": "free_text", "next_id": "q2"}]
        engine = SurveyEngine(survey, "q1")
        engine.answers["q1"] = "test"
        snapshot = engine.snapshot()
        assert snapshot["answers"] == {"q1": "test"}

    def test_snapshot_includes_nudge_count(self):
        """Snapshot should include nudge_count."""
        survey = [{"id": "q1", "type": "free_text"}]
        engine = SurveyEngine(survey, "q1")
        engine.nudge_count = 3
        snapshot = engine.snapshot()
        assert snapshot["nudge_count"] == 3

    def test_snapshot_returns_copy_of_answers(self):
        """Snapshot answers should be a copy, not reference."""
        survey = [{"id": "q1", "type": "free_text"}]
        engine = SurveyEngine(survey, "q1")
        engine.answers["q1"] = "test"
        snapshot = engine.snapshot()
        snapshot["answers"]["q1"] = "modified"
        assert engine.answers["q1"] == "test"  # Original unchanged


class TestSurveyEngineIntegration:
    """Integration tests for full survey flows."""

    def test_complete_simple_flow(self):
        """Should complete a simple survey flow."""
        survey = [
            {"id": "welcome", "type": "narration", "text": "Welcome!", "next_id": "q1"},
            {
                "id": "q1",
                "type": "single_choice",
                "text": "Yes or no?",
                "options": [
                    {"id": "yes", "value": "yes", "next_id": "thanks_yes"},
                    {"id": "no", "value": "no", "next_id": "thanks_no"},
                ],
            },
            {"id": "thanks_yes", "type": "narration", "text": "Thanks for saying yes!"},
            {"id": "thanks_no", "type": "narration", "text": "Thanks for saying no!"},
        ]
        engine = SurveyEngine(survey, "welcome")

        # Advance to first question
        spoken, current, _, _ = engine.advance_to_interactive()
        assert "Welcome!" in spoken
        assert current == "q1"

        # Answer and advance
        result = engine.validate("q1", "yes")
        assert result["valid"] is True
        engine.record("q1", result["normalized"])

        # Advance to end
        spoken, current, _, _ = engine.advance_to_interactive()
        assert "Thanks for saying yes!" in spoken

    def test_conditional_branching_flow(self):
        """Should handle conditional branching based on answers."""
        survey = [
            {
                "id": "age_check",
                "type": "numeric",
                "text": "How old are you?",
                "next_id": "underage_msg",
            },
            {
                "id": "underage_msg",
                "type": "narration",
                "text": "Sorry, you must be 18+",
                "ask_if": {"lt": {"question_id": "age_check", "value": 18}},
                "next_id": "end",
            },
            {
                "id": "adult_msg",
                "type": "narration",
                "text": "Welcome adult!",
                "ask_if": {"not": {"lt": {"question_id": "age_check", "value": 18}}},
            },
            {"id": "end", "type": "narration", "text": "End"},
        ]
        engine = SurveyEngine(survey, "age_check")

        # Advance to age question
        engine.advance_to_interactive()
        assert engine.current_id == "age_check"

        # Answer with age 16 (underage)
        engine.record("age_check", 16)

        # Advance should show underage message
        spoken, _, _, _ = engine.advance_to_interactive()
        assert "Sorry, you must be 18+" in spoken


class TestApiCallToHandoverCoach:
    """Tests for the api_call → conditional handover_to_coach flow.

    Reproduces the real survey structure where ADDRESS_STATE_CHECK returns
    NOT_ELIGIBLE_STATE and the next node (TRANSFER_TO_COACH_OUT_OF_STATE)
    has an ask_if that triggers a coach handover.
    """

    @staticmethod
    def _address_flow_survey():
        """Mini survey mimicking the address → state check → handover flow."""
        return [
            {
                "id": "ADDRESS_Q",
                "type": "free_text",
                "text": "What's your address?",
                "next_id": "STATE_CHECK",
            },
            {
                "id": "STATE_CHECK",
                "type": "api_call",
                "text": "Checking eligibility...",
                "api": {
                    "endpoint": "address_state_check",
                    "expected_responses": [
                        "ELIGIBLE_STATE",
                        "NOT_ELIGIBLE_STATE",
                        "INVALID_ADDRESS",
                    ],
                },
                "next_id": "HANDOVER_OUT_OF_STATE",
            },
            {
                "id": "HANDOVER_OUT_OF_STATE",
                "type": "handover_to_coach",
                "text": "Sorry, not available in your state.",
                "whisper_text": "Out-of-state caller.",
                "next_id": "NEXT_Q",
                "ask_if": {
                    "api_in": {
                        "question_id": "STATE_CHECK",
                        "values": ["NOT_ELIGIBLE_STATE"],
                    }
                },
            },
            {
                "id": "NEXT_Q",
                "type": "single_choice",
                "text": "Next question",
            },
        ]

    def test_out_of_state_triggers_handover(self):
        """api_call returns NOT_ELIGIBLE_STATE → handover_to_coach fires."""

        def mock_handler(node_id, api_cfg, answers):
            return "NOT_ELIGIBLE_STATE"

        engine = SurveyEngine(self._address_flow_survey(), "ADDRESS_Q", mock_handler)

        # Advance to the address question
        engine.advance_to_interactive()
        assert engine.current_id == "ADDRESS_Q"

        # Record address answer and advance
        engine.record("ADDRESS_Q", "123 Main St, Los Angeles, CA 90001")
        spoken, node_id, _, _ = engine.advance_to_interactive()

        # Engine should have reached the handover node
        assert "Sorry, not available in your state" in spoken
        assert engine.pending_handover_context is not None
        assert engine.pending_handover_context.whisper_text == "Out-of-state caller."
        # current_id is set to None when handover fires
        assert engine.current_id is None
        # Answer stored correctly
        assert engine.answers["STATE_CHECK"] == "NOT_ELIGIBLE_STATE"

    def test_eligible_state_skips_handover(self):
        """api_call returns 'FL' → handover_to_coach ask_if is False → skipped."""

        def mock_handler(node_id, api_cfg, answers):
            return "FL"

        engine = SurveyEngine(self._address_flow_survey(), "ADDRESS_Q", mock_handler)

        engine.advance_to_interactive()
        engine.record("ADDRESS_Q", "3500 Main Street Anytown FL 00000")
        spoken, node_id, _, _ = engine.advance_to_interactive()

        # Handover should be skipped; engine advances to NEXT_Q
        assert engine.pending_handover_context is None
        assert node_id == "NEXT_Q"
        assert "Sorry, not available" not in spoken
        assert engine.answers["STATE_CHECK"] == "FL"

    def test_invalid_address_skips_handover(self):
        """api_call returns INVALID_ADDRESS → handover (checks NOT_ELIGIBLE_STATE) skipped."""

        def mock_handler(node_id, api_cfg, answers):
            return "INVALID_ADDRESS"

        engine = SurveyEngine(self._address_flow_survey(), "ADDRESS_Q", mock_handler)

        engine.advance_to_interactive()
        engine.record("ADDRESS_Q", "999 Fake Rd Nowhere XX 00000")
        spoken, node_id, _, _ = engine.advance_to_interactive()

        assert engine.pending_handover_context is None
        assert node_id == "NEXT_Q"
        assert engine.answers["STATE_CHECK"] == "INVALID_ADDRESS"

    def test_handler_none_falls_back_to_expected_response(self):
        """No api_call_handler → falls back to expected[1] = NOT_ELIGIBLE_STATE → handover."""
        engine = SurveyEngine(
            self._address_flow_survey(), "ADDRESS_Q", api_node_handler=None
        )

        engine.advance_to_interactive()
        engine.record("ADDRESS_Q", "any address")
        spoken, _, _, _ = engine.advance_to_interactive()

        # Fallback stores expected[1] = "NOT_ELIGIBLE_STATE"
        assert engine.answers["STATE_CHECK"] == "NOT_ELIGIBLE_STATE"
        assert engine.pending_handover_context is not None
        assert "Sorry, not available in your state" in spoken

    def test_handler_exception_falls_back_to_expected_response(self):
        """api_call_handler raises → falls back to expected[1] → handover fires."""

        def crashing_handler(node_id, api_cfg, answers):
            raise RuntimeError("USPS API down")

        engine = SurveyEngine(
            self._address_flow_survey(), "ADDRESS_Q", crashing_handler
        )

        engine.advance_to_interactive()
        engine.record("ADDRESS_Q", "any address")
        spoken, _, _, _ = engine.advance_to_interactive()

        assert engine.answers["STATE_CHECK"] == "NOT_ELIGIBLE_STATE"
        assert engine.pending_handover_context is not None

    def test_invalid_then_recheck_not_eligible_triggers_handover(self):
        """Regression: first check INVALID_ADDRESS, recheck NOT_ELIGIBLE_STATE → must handover.

        This reproduces the exact bug from the field: user gives address without
        state/zip → INVALID_ADDRESS → retry → user gives out-of-state address →
        NOT_ELIGIBLE_STATE. Previously the handover was skipped because the only
        out-of-state handover node sat before the retry loop.
        """
        survey = [
            {
                "id": "ADDRESS_Q",
                "type": "free_text",
                "text": "What's your address?",
                "next_id": "STATE_CHECK",
            },
            {
                "id": "STATE_CHECK",
                "type": "api_call",
                "text": "Checking...",
                "api": {
                    "endpoint": "address_state_check",
                    "expected_responses": [
                        "ELIGIBLE_STATE",
                        "NOT_ELIGIBLE_STATE",
                        "INVALID_ADDRESS",
                    ],
                    "params": {"address": {"from_question_id": "ADDRESS_Q"}},
                },
                "next_id": "HANDOVER_OUT_OF_STATE",
            },
            {
                "id": "HANDOVER_OUT_OF_STATE",
                "type": "handover_to_coach",
                "text": "Not available in your state.",
                "whisper_text": "Out-of-state.",
                "next_id": "RETRY_ADDRESS",
                "ask_if": {
                    "api_in": {
                        "question_id": "STATE_CHECK",
                        "values": ["NOT_ELIGIBLE_STATE"],
                    }
                },
            },
            {
                "id": "RETRY_ADDRESS",
                "type": "free_text",
                "text": "Please provide your address again.",
                "ask_if": {
                    "api_in": {
                        "question_id": "STATE_CHECK",
                        "values": ["INVALID_ADDRESS"],
                    }
                },
                "next_id": "STATE_RECHECK",
            },
            {
                "id": "STATE_RECHECK",
                "type": "api_call",
                "text": "",
                "ask_if": {
                    "api_in": {
                        "question_id": "STATE_CHECK",
                        "values": ["INVALID_ADDRESS"],
                    }
                },
                "api": {
                    "endpoint": "address_state_check",
                    "expected_responses": [
                        "ELIGIBLE_STATE",
                        "NOT_ELIGIBLE_STATE",
                        "INVALID_ADDRESS",
                    ],
                    "params": {"address": {"from_question_id": "RETRY_ADDRESS"}},
                },
                "next_id": "HANDOVER_RECHECK_OUT_OF_STATE",
            },
            {
                "id": "HANDOVER_RECHECK_OUT_OF_STATE",
                "type": "handover_to_coach",
                "text": "Not available in your state.",
                "whisper_text": "Out-of-state after recheck.",
                "next_id": "NEXT_Q",
                "ask_if": {
                    "api_in": {
                        "question_id": "STATE_RECHECK",
                        "values": ["NOT_ELIGIBLE_STATE"],
                    }
                },
            },
            {
                "id": "NEXT_Q",
                "type": "single_choice",
                "text": "Which plan?",
            },
        ]

        call_count = {"n": 0}

        def mock_handler(node_id, api_cfg, answers):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return "INVALID_ADDRESS"  # first attempt: no state found
            return "NOT_ELIGIBLE_STATE"  # recheck: California

        engine = SurveyEngine(survey, "ADDRESS_Q", mock_handler)

        # Advance to first address question
        engine.advance_to_interactive()
        assert engine.current_id == "ADDRESS_Q"

        # User gives address without state → INVALID_ADDRESS → retry shown
        engine.record("ADDRESS_Q", "123 Main Street, Los Angeles")
        spoken, node_id, _, _ = engine.advance_to_interactive()
        # Engine skips handover (STATE_CHECK != NOT_ELIGIBLE_STATE), lands on RETRY_ADDRESS
        assert node_id == "RETRY_ADDRESS"
        assert engine.pending_handover_context is None  # no handover yet
        assert engine.answers["STATE_CHECK"] == "INVALID_ADDRESS"

        # User gives full address with California → NOT_ELIGIBLE_STATE
        engine.record("RETRY_ADDRESS", "123 Main St, Los Angeles, CA 90001")
        spoken, node_id, _, _ = engine.advance_to_interactive()

        # MUST trigger handover — this was the bug!
        assert engine.answers["STATE_RECHECK"] == "NOT_ELIGIBLE_STATE"
        assert engine.pending_handover_context is not None
        assert "Not available in your state" in spoken
