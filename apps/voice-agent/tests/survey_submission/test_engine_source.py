"""Tests for SurveyEngine source-related methods (get_node_source, get_current_source)."""

from voice_agent.voice_ai.survey_engine.engine import SurveyEngine


SURVEY_WITH_SOURCES = [
    {
        "id": "Q_ONBOARD_1",
        "source": "onboarding",
        "type": "free_text",
        "text": "What is your name?",
        "next_id": "Q_MAIN_1",
    },
    {
        "id": "Q_MAIN_1",
        "source": "questions",
        "type": "single_choice",
        "text": "Which plan?",
        "options": [
            {"value": "provider_b", "label": "Provider B"},
            {"value": "other", "label": "Other"},
        ],
        "next_id": "Q_CLOSE_1",
    },
    {
        "id": "Q_CLOSE_1",
        "source": "closing",
        "type": "yes_no",
        "text": "Preferred contact method?",
        "next_id": None,
    },
]


class TestGetNodeSource:
    def test_returns_source_for_existing_node(self):
        engine = SurveyEngine(SURVEY_WITH_SOURCES, "Q_ONBOARD_1")
        assert engine.get_node_source("Q_ONBOARD_1") == "onboarding"
        assert engine.get_node_source("Q_MAIN_1") == "questions"
        assert engine.get_node_source("Q_CLOSE_1") == "closing"

    def test_returns_none_for_nonexistent_node(self):
        engine = SurveyEngine(SURVEY_WITH_SOURCES, "Q_ONBOARD_1")
        assert engine.get_node_source("DOES_NOT_EXIST") is None

    def test_returns_none_for_node_without_source(self):
        survey = [{"id": "Q1", "type": "free_text", "text": "Hi"}]
        engine = SurveyEngine(survey, "Q1")
        assert engine.get_node_source("Q1") is None


class TestGetCurrentSource:
    def test_returns_source_of_current_node(self):
        engine = SurveyEngine(SURVEY_WITH_SOURCES, "Q_ONBOARD_1")
        assert engine.get_current_source() == "onboarding"

    def test_changes_after_record_and_advance(self):
        engine = SurveyEngine(SURVEY_WITH_SOURCES, "Q_ONBOARD_1")
        assert engine.get_current_source() == "onboarding"

        engine.record("Q_ONBOARD_1", "John")
        # After record, current_id moves to next_id ("Q_MAIN_1")
        assert engine.get_current_source() == "questions"

    def test_returns_none_when_current_id_is_none(self):
        engine = SurveyEngine(SURVEY_WITH_SOURCES, "Q_ONBOARD_1")
        engine.current_id = None
        assert engine.get_current_source() is None

    def test_detects_source_transition(self):
        """Simulates a transition from one survey section to the next."""
        engine = SurveyEngine(SURVEY_WITH_SOURCES, "Q_MAIN_1")

        before_source = engine.get_current_source()
        assert before_source == "questions"

        engine.record("Q_MAIN_1", "provider_b")

        after_source = engine.get_current_source()
        assert after_source == "closing"

        # This is the transition the dispatcher detects
        assert before_source != after_source
