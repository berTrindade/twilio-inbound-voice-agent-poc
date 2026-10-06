"""Tests for SurveyBackendAdapter module."""

import pytest
import time
from voice_agent.voice_ai.backend_adapter import SurveyBackendAdapter
from voice_agent.voice_ai.survey_engine import SurveyEngine


class TestSurveyBackendAdapterInit:
    """Tests for SurveyBackendAdapter initialization."""

    def test_init_stores_engine(self):
        """Should store the engine reference."""
        survey = [{"id": "q1", "type": "single_choice"}]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        assert adapter.engine is engine

    def test_init_clears_answer_buffer(self):
        """Should initialize with empty answer buffer."""
        survey = [{"id": "q1", "type": "single_choice"}]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        assert adapter._buffer_node_id is None
        assert adapter._buffer_text == ""
        assert adapter._buffer_last_update is None


class TestSurveyBackendAdapterAdvance:
    """Tests for advance method."""

    @pytest.fixture
    def simple_survey_adapter(self):
        """Create adapter with simple survey."""
        survey = [
            {"id": "intro", "type": "narration", "text": "Welcome!", "next_id": "q1"},
            {
                "id": "q1",
                "type": "single_choice",
                "text": "Choose one",
                "options": [{"id": "a", "value": "a", "label": "Option A"}],
            },
        ]
        engine = SurveyEngine(survey, "intro")
        return SurveyBackendAdapter(engine)

    def test_advance_returns_spoken_intro(self, simple_survey_adapter):
        """Should return spoken intro text from narration nodes."""
        result = simple_survey_adapter.advance()

        assert "Welcome!" in result["spoken_intro"]

    def test_advance_returns_current_node_id(self, simple_survey_adapter):
        """Should return the current interactive node ID."""
        result = simple_survey_adapter.advance()

        assert result["node_id"] == "q1"

    def test_advance_returns_question_prompt(self, simple_survey_adapter):
        """Should return the question prompt."""
        result = simple_survey_adapter.advance()

        assert "Choose one" in result["question_prompt"]

    def test_advance_returns_finished_false(self, simple_survey_adapter):
        """Should return finished=False when not at end."""
        result = simple_survey_adapter.advance()

        assert result["finished"] is False

    def test_advance_returns_state_snapshot(self, simple_survey_adapter):
        """Should return state snapshot."""
        result = simple_survey_adapter.advance()

        assert "current_id" in result["state"]
        assert "answers" in result["state"]

    def test_advance_resets_answer_buffer(self, simple_survey_adapter):
        """Should reset answer buffer for new node."""
        simple_survey_adapter._buffer_text = "old text"
        simple_survey_adapter._buffer_node_id = "old_node"

        simple_survey_adapter.advance()

        assert simple_survey_adapter._buffer_node_id == "q1"
        assert simple_survey_adapter._buffer_text == ""


class TestSurveyBackendAdapterValidate:
    """Tests for validate method."""

    @pytest.fixture
    def adapter(self):
        """Create adapter with survey."""
        survey = [
            {
                "id": "q1",
                "type": "single_choice",
                "options": [
                    {"id": "yes", "value": "yes"},
                    {"id": "no", "value": "no"},
                ],
            }
        ]
        engine = SurveyEngine(survey, "q1")
        return SurveyBackendAdapter(engine)

    def test_validate_delegates_to_engine(self, adapter):
        """Should delegate to engine's validate method."""
        result = adapter.validate("q1", "yes")

        assert result["valid"] is True
        assert result["normalized"] == "yes"

    def test_validate_returns_invalid_for_bad_input(self, adapter):
        """Should return invalid for non-matching input."""
        result = adapter.validate("q1", "maybe")

        assert result["valid"] is False


class TestSurveyBackendAdapterRecord:
    """Tests for record method."""

    @pytest.fixture
    def adapter(self):
        """Create adapter with survey."""
        survey = [
            {"id": "q1", "type": "free_text", "next_id": "q2"},
            {"id": "q2", "type": "free_text"},
        ]
        engine = SurveyEngine(survey, "q1")
        return SurveyBackendAdapter(engine)

    def test_record_delegates_to_engine(self, adapter):
        """Should delegate to engine's record method."""
        adapter.record("q1", "my answer")

        assert adapter.engine.answers["q1"] == "my answer"

    def test_record_advances_to_next_node(self, adapter):
        """Should advance to next node after recording."""
        adapter.record("q1", "my answer")

        assert adapter.engine.current_id == "q2"


class TestSurveyBackendAdapterCurrent:
    """Tests for current method."""

    @pytest.fixture
    def adapter(self):
        """Create adapter with survey."""
        survey = [{"id": "q1", "type": "free_text", "text": "Enter something"}]
        engine = SurveyEngine(survey, "q1")
        return SurveyBackendAdapter(engine)

    def test_current_returns_node_id(self, adapter):
        """Should return current node ID."""
        result = adapter.current()

        assert result["node_id"] == "q1"

    def test_current_returns_question_prompt(self, adapter):
        """Should return question prompt."""
        result = adapter.current()

        assert "Enter something" in result["question_prompt"]

    def test_current_returns_finished_status(self, adapter):
        """Should return finished status."""
        result = adapter.current()

        assert result["finished"] is False


class TestSurveyBackendAdapterShouldEscalate:
    """Tests for should_escalate method."""

    @pytest.fixture
    def adapter(self):
        """Create adapter with survey."""
        survey = [{"id": "q1", "type": "free_text"}]
        engine = SurveyEngine(survey, "q1")
        return SurveyBackendAdapter(engine)

    def test_should_escalate_delegates_to_engine(self, adapter):
        """Should delegate to engine's should_escalate."""
        # First call - increments nudge
        result1 = adapter.should_escalate("unclear", 0.3, True)
        assert result1 is False

        # Second call - should escalate
        result2 = adapter.should_escalate("still unclear", 0.3, True)
        assert result2 is True


class TestSurveyBackendAdapterSnapshot:
    """Tests for snapshot method."""

    def test_snapshot_delegates_to_engine(self):
        """Should delegate to engine's snapshot."""
        survey = [{"id": "q1", "type": "free_text"}]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)
        engine.answers["q1"] = "test"

        result = adapter.snapshot()

        assert result["current_id"] == "q1"
        assert result["answers"]["q1"] == "test"


class TestGetPromptFor:
    """Tests for _get_prompt_for method."""

    def test_prompt_for_single_choice_with_options(self):
        """Should render single choice prompt with options."""
        survey = [
            {
                "id": "q1",
                "type": "single_choice",
                "text": "Choose color",
                "options": [
                    {"label": "Red"},
                    {"label": "Blue"},
                ],
            }
        ]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        prompt = adapter._get_prompt_for("q1")

        assert "Choose color" in prompt
        assert "A: Red" in prompt
        assert "B: Blue" in prompt

    def test_prompt_for_single_choice_speak_options_false(self):
        """Should not render options when speak_options is False."""
        survey = [
            {
                "id": "q1",
                "type": "single_choice",
                "text": "Choose color",
                "speak_options": False,
                "options": [{"label": "Red"}, {"label": "Blue"}],
            }
        ]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        prompt = adapter._get_prompt_for("q1")

        assert "Choose color" in prompt
        assert "Red" not in prompt
        assert "Blue" not in prompt

    def test_prompt_for_multi_choice_with_options(self):
        """Should render multi choice prompt with options."""
        survey = [
            {
                "id": "q1",
                "type": "multi_choice",
                "text": "Select all that apply",
                "options": [{"label": "A"}, {"label": "B"}, {"label": "C"}],
            }
        ]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        prompt = adapter._get_prompt_for("q1")

        assert "Select all that apply" in prompt
        assert "A: A" in prompt
        assert "B: B" in prompt
        assert "C: C" in prompt

    def test_prompt_for_yes_no(self):
        """Should return yes_no prompt."""
        survey = [{"id": "q1", "type": "yes_no", "text": "Do you agree?"}]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        prompt = adapter._get_prompt_for("q1")

        assert prompt == "Do you agree?"

    def test_prompt_for_yes_no_default(self):
        """Should use default prompt for yes_no without text."""
        survey = [{"id": "q1", "type": "yes_no"}]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        prompt = adapter._get_prompt_for("q1")

        assert prompt == "Please answer yes or no."

    def test_prompt_for_numeric(self):
        """Should return numeric prompt."""
        survey = [{"id": "q1", "type": "numeric", "text": "How many?"}]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        prompt = adapter._get_prompt_for("q1")

        assert prompt == "How many?"

    def test_prompt_for_numeric_default(self):
        """Should use default prompt for numeric without text."""
        survey = [{"id": "q1", "type": "numeric"}]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        prompt = adapter._get_prompt_for("q1")

        assert prompt == "Please give a number."

    def test_prompt_for_free_text(self):
        """Should return free text prompt."""
        survey = [{"id": "q1", "type": "free_text", "text": "Tell me more"}]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        prompt = adapter._get_prompt_for("q1")

        assert prompt == "Tell me more"

    def test_prompt_for_free_text_default(self):
        """Should use default prompt for free_text without text."""
        survey = [{"id": "q1", "type": "free_text"}]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        prompt = adapter._get_prompt_for("q1")

        assert prompt == "Please share briefly."

    def test_prompt_with_tts_preface(self):
        """Should prepend tts_preface to prompt."""
        survey = [
            {
                "id": "q1",
                "type": "free_text",
                "text": "What's your name?",
                "tts_preface": "Great!",
            }
        ]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        prompt = adapter._get_prompt_for("q1")

        assert prompt == "Great! What's your name?"

    def test_prompt_for_empty_node_id(self):
        """Should return empty string for empty node_id."""
        survey = [{"id": "q1", "type": "free_text"}]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        prompt = adapter._get_prompt_for("")

        assert prompt == ""

    def test_prompt_for_unknown_type(self):
        """Should return base text for unknown type."""
        survey = [{"id": "q1", "type": "unknown_type", "text": "Some text"}]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        prompt = adapter._get_prompt_for("q1")

        assert prompt == "Some text"


class TestMergeUserUtterance:
    """Tests for merge_user_utterance method."""

    @pytest.fixture
    def adapter(self):
        """Create adapter with survey."""
        survey = [{"id": "q1", "type": "free_text"}]
        engine = SurveyEngine(survey, "q1")
        return SurveyBackendAdapter(engine)

    def test_first_utterance_stores_text(self, adapter):
        """Should store first utterance."""
        result = adapter.merge_user_utterance("q1", "hello")

        assert result == "hello"
        assert adapter._buffer_text == "hello"
        assert adapter._buffer_node_id == "q1"

    def test_subsequent_utterance_appends(self, adapter):
        """Should append subsequent utterances for same node."""
        adapter.merge_user_utterance("q1", "hello")
        result = adapter.merge_user_utterance("q1", "world")

        assert result == "hello world"

    def test_new_node_resets_buffer(self, adapter):
        """Should reset buffer for new node."""
        adapter.merge_user_utterance("q1", "hello")
        result = adapter.merge_user_utterance("q2", "new question")

        assert result == "new question"
        assert adapter._buffer_node_id == "q2"

    def test_empty_text_returns_existing_buffer(self, adapter):
        """Should return existing buffer for empty text."""
        adapter.merge_user_utterance("q1", "hello")
        result = adapter.merge_user_utterance("q1", "")

        assert result == "hello"

    def test_whitespace_only_returns_existing_buffer(self, adapter):
        """Should return existing buffer for whitespace-only text."""
        adapter.merge_user_utterance("q1", "hello")
        result = adapter.merge_user_utterance("q1", "   ")

        assert result == "hello"

    def test_strips_whitespace_from_input(self, adapter):
        """Should strip whitespace from input."""
        result = adapter.merge_user_utterance("q1", "  hello  ")

        assert result == "hello"

    def test_stale_buffer_starts_fresh(self, adapter):
        """Should start fresh if buffer is stale."""
        adapter.merge_user_utterance("q1", "old text")
        # Simulate time passing beyond merge window
        adapter._buffer_last_update = time.monotonic() - 10.0

        result = adapter.merge_user_utterance("q1", "new text")

        assert result == "new text"

    def test_max_length_truncation(self, adapter):
        """Should truncate combined text at max length."""
        # Fill buffer with long text
        long_text = "a" * 500
        adapter.merge_user_utterance("q1", long_text)

        # Add more text to exceed limit
        result = adapter.merge_user_utterance("q1", "b" * 100)

        assert len(result) <= 512

    def test_none_text_returns_existing_buffer(self, adapter):
        """Should handle None text gracefully."""
        adapter.merge_user_utterance("q1", "hello")
        result = adapter.merge_user_utterance("q1", None)

        assert result == "hello"


class TestRenderOptionsLetters:
    """Tests for _render_options_letters helper."""

    def test_renders_options_with_letters(self):
        """Should render options with letter prefixes."""
        survey = [{"id": "q1", "type": "single_choice"}]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        options = [
            {"label": "First"},
            {"label": "Second"},
            {"label": "Third"},
        ]

        result = adapter._render_options_letters(options)

        assert result == "A: First. B: Second. C: Third"

    def test_renders_empty_for_no_options(self):
        """Should return empty string for no options."""
        survey = [{"id": "q1", "type": "single_choice"}]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        result = adapter._render_options_letters([])

        assert result == ""

    def test_handles_missing_label(self):
        """Should handle options without label."""
        survey = [{"id": "q1", "type": "single_choice"}]
        engine = SurveyEngine(survey, "q1")
        adapter = SurveyBackendAdapter(engine)

        options = [{"value": "a"}, {"label": "Has Label"}]

        result = adapter._render_options_letters(options)

        assert "A: " in result
        assert "B: Has Label" in result
