"""Tests for validation module."""

import pytest
from datetime import date, timedelta
from voice_agent.voice_ai.survey_engine.validation import (
    validate_single_choice,
    validate_multi_choice,
    validate_numeric,
    validate_free_text,
    validate_answer,
    validate_yes_no,
    apply_validation_meta,
    _normalize_multi_choice_selection,
)


class TestValidateSingleChoice:
    """Tests for validate_single_choice function."""

    @pytest.fixture
    def yes_no_node(self):
        """Node with yes/no options."""
        return {
            "id": "q1",
            "type": "single_choice",
            "options": [
                {"id": "opt_yes", "value": "yes", "label": "Yes"},
                {"id": "opt_no", "value": "no", "label": "No"},
            ],
        }

    @pytest.fixture
    def options_with_ids(self):
        """Node with options that have distinct ids."""
        return {
            "id": "q2",
            "type": "single_choice",
            "options": [
                {"id": "red", "value": "red", "label": "Red"},
                {"id": "blue", "value": "blue", "label": "Blue"},
                {"id": "green", "value": "green", "label": "Green"},
            ],
        }

    def test_valid_option_by_value(self, yes_no_node):
        """Should validate when user text matches option value."""
        result = validate_single_choice(yes_no_node, "yes")
        assert result["valid"] is True
        assert result["normalized"] == "opt_yes"
        assert result["reason"] is None

    def test_valid_option_by_id(self, yes_no_node):
        """Should validate when user text matches option id."""
        result = validate_single_choice(yes_no_node, "opt_no")
        assert result["valid"] is True
        assert result["normalized"] == "opt_no"

    def test_case_insensitive_match(self, yes_no_node):
        """Should match case insensitively."""
        result = validate_single_choice(yes_no_node, "YES")
        assert result["valid"] is True
        assert result["normalized"] == "opt_yes"

    def test_letter_selection(self, options_with_ids):
        """Should match by letter (a, b, c)."""
        result = validate_single_choice(options_with_ids, "b")
        assert result["valid"] is True
        assert result["normalized"] == "blue"

    def test_invalid_option(self, yes_no_node):
        """Should fail for non-matching text."""
        result = validate_single_choice(yes_no_node, "maybe")
        assert result["valid"] is False
        assert result["normalized"] is None
        assert result["reason"] == "could_not_match_option"

    def test_empty_text(self, yes_no_node):
        """Should fail for empty text."""
        result = validate_single_choice(yes_no_node, "")
        assert result["valid"] is False
        assert result["reason"] == "could_not_match_option"

    def test_with_validation_meta_regex_pass(self):
        """Should pass with validation meta regex on normalized value (option id)."""
        # Note: validation is applied to the normalized value (option id), not user input
        node = {
            "id": "q1",
            "type": "single_choice",
            "options": [{"id": "123", "value": "123"}],
            "validation": {"kind": "regex", "pattern": r"^\d+$"},
        }
        result = validate_single_choice(node, "123")
        assert result["valid"] is True

    def test_with_validation_meta_regex_fail(self):
        """Should fail when validation meta regex doesn't match normalized value."""
        # Note: validation is applied to the normalized value (option id), not user input
        node = {
            "id": "q1",
            "type": "single_choice",
            "options": [{"id": "abc", "value": "abc"}],
            "validation": {"kind": "regex", "pattern": r"^\d+$"},
        }
        result = validate_single_choice(node, "abc")
        assert result["valid"] is False
        assert result["reason"] == "regex_failed"


class TestValidateMultiChoice:
    """Tests for validate_multi_choice function."""

    @pytest.fixture
    def multi_choice_node(self):
        """Node with multiple choice options."""
        return {
            "id": "colors",
            "type": "multi_choice",
            "options": [
                {"id": "red", "value": "red"},
                {"id": "blue", "value": "blue"},
                {"id": "green", "value": "green"},
                {"id": "yellow", "value": "yellow"},
            ],
        }

    def test_single_selection_from_text(self, multi_choice_node):
        """Should accept single selection."""
        result = validate_multi_choice(multi_choice_node, "red")
        assert result["valid"] is True
        assert result["normalized"] == ["red"]

    def test_multiple_selections_comma_separated(self, multi_choice_node):
        """Should accept comma-separated selections."""
        result = validate_multi_choice(multi_choice_node, "red, blue")
        assert result["valid"] is True
        assert set(result["normalized"]) == {"red", "blue"}

    def test_multiple_selections_with_and(self, multi_choice_node):
        """Should accept 'and' separator."""
        result = validate_multi_choice(multi_choice_node, "red and green")
        assert result["valid"] is True
        assert set(result["normalized"]) == {"red", "green"}

    def test_multiple_selections_with_ampersand(self, multi_choice_node):
        """Should accept '&' separator."""
        result = validate_multi_choice(multi_choice_node, "blue & yellow")
        assert result["valid"] is True
        assert set(result["normalized"]) == {"blue", "yellow"}

    def test_list_input_from_llm(self, multi_choice_node):
        """Should accept list input (from LLM)."""
        result = validate_multi_choice(multi_choice_node, ["red", "blue"])
        assert result["valid"] is True
        assert result["normalized"] == ["red", "blue"]

    def test_list_input_filters_invalid(self, multi_choice_node):
        """Should filter out invalid options from list."""
        result = validate_multi_choice(multi_choice_node, ["red", "purple", "blue"])
        assert result["valid"] is True
        assert result["normalized"] == ["red", "blue"]

    def test_empty_text_fails(self, multi_choice_node):
        """Should fail for empty text."""
        result = validate_multi_choice(multi_choice_node, "")
        assert result["valid"] is False
        assert result["reason"] == "no_options_matched"

    def test_none_input_fails(self, multi_choice_node):
        """Should fail for None input."""
        result = validate_multi_choice(multi_choice_node, None)
        assert result["valid"] is False
        assert result["reason"] == "empty_text"

    def test_no_valid_options_matched(self, multi_choice_node):
        """Should fail when no valid options matched."""
        result = validate_multi_choice(multi_choice_node, "purple, orange")
        assert result["valid"] is False
        assert result["reason"] == "no_options_matched"

    def test_deduplicates_selections(self, multi_choice_node):
        """Should deduplicate repeated selections."""
        result = validate_multi_choice(multi_choice_node, "red, red, blue")
        assert result["valid"] is True
        assert result["normalized"] == ["red", "blue"]


class TestNormalizeMultiChoiceSelection:
    """Tests for _normalize_multi_choice_selection helper."""

    @pytest.fixture
    def options(self):
        return [{"value": "a"}, {"value": "b"}, {"value": "c"}]

    def test_list_input_lowercases(self, options):
        """Should lowercase list inputs."""
        result = _normalize_multi_choice_selection(["A", "B"], options)
        assert result == ["a", "b"]

    def test_list_input_strips_whitespace(self, options):
        """Should strip whitespace from list inputs."""
        result = _normalize_multi_choice_selection(["  a  ", " b"], options)
        assert result == ["a", "b"]

    def test_list_input_filters_none(self, options):
        """Should filter None values from list."""
        result = _normalize_multi_choice_selection(["a", None, "b"], options)
        assert result == ["a", "b"]

    def test_string_splits_on_comma(self, options):
        """Should split string on comma."""
        result = _normalize_multi_choice_selection("a, b", options)
        assert result == ["a", "b"]


class TestValidateNumeric:
    """Tests for validate_numeric function."""

    @pytest.fixture
    def numeric_node(self):
        """Basic numeric node."""
        return {"id": "age", "type": "numeric"}

    @pytest.fixture
    def numeric_node_with_range(self):
        """Numeric node with min/max range."""
        return {"id": "age", "type": "numeric", "min": 18, "max": 120}

    def test_valid_integer(self, numeric_node):
        """Should accept valid integer."""
        result = validate_numeric(numeric_node, "25")
        assert result["valid"] is True
        assert result["normalized"] == 25.0

    def test_valid_decimal(self, numeric_node):
        """Should accept valid decimal."""
        result = validate_numeric(numeric_node, "3.14")
        assert result["valid"] is True
        assert result["normalized"] == 3.14

    def test_number_in_text(self, numeric_node):
        """Should extract number from text."""
        result = validate_numeric(numeric_node, "I am 30 years old")
        assert result["valid"] is True
        assert result["normalized"] == 30.0

    def test_no_number_fails(self, numeric_node):
        """Should fail when no number found."""
        result = validate_numeric(numeric_node, "no numbers here")
        assert result["valid"] is False
        assert result["reason"] == "no_number_found"

    def test_within_range(self, numeric_node_with_range):
        """Should accept number within range."""
        result = validate_numeric(numeric_node_with_range, "25")
        assert result["valid"] is True
        assert result["normalized"] == 25.0

    def test_below_min_fails(self, numeric_node_with_range):
        """Should fail when below minimum."""
        result = validate_numeric(numeric_node_with_range, "10")
        assert result["valid"] is False
        assert result["reason"] == "out_of_range"

    def test_above_max_fails(self, numeric_node_with_range):
        """Should fail when above maximum."""
        result = validate_numeric(numeric_node_with_range, "150")
        assert result["valid"] is False
        assert result["reason"] == "out_of_range"

    def test_at_min_boundary(self, numeric_node_with_range):
        """Should accept number at minimum boundary."""
        result = validate_numeric(numeric_node_with_range, "18")
        assert result["valid"] is True

    def test_at_max_boundary(self, numeric_node_with_range):
        """Should accept number at maximum boundary."""
        result = validate_numeric(numeric_node_with_range, "120")
        assert result["valid"] is True

    def test_negative_number(self, numeric_node):
        """Should accept negative numbers."""
        result = validate_numeric(numeric_node, "-5")
        assert result["valid"] is True
        assert result["normalized"] == -5.0


class TestValidateFreeText:
    """Tests for validate_free_text function."""

    @pytest.fixture
    def free_text_node(self):
        """Basic free text node."""
        return {"id": "name", "type": "free_text"}

    @pytest.fixture
    def free_text_with_minlength(self):
        """Free text node with minimum length validation."""
        return {
            "id": "name",
            "type": "free_text",
            "validation": {"kind": "minlength", "min": 2},
        }

    def test_valid_text(self, free_text_node):
        """Should accept valid text."""
        result = validate_free_text(free_text_node, "John Doe")
        assert result["valid"] is True
        assert result["normalized"] == "John Doe"

    def test_strips_whitespace(self, free_text_node):
        """Should strip leading/trailing whitespace."""
        result = validate_free_text(free_text_node, "  Hello  ")
        assert result["valid"] is True
        assert result["normalized"] == "Hello"

    def test_empty_text_fails(self, free_text_node):
        """Should fail for empty text."""
        result = validate_free_text(free_text_node, "")
        assert result["valid"] is False
        assert result["reason"] == "empty_text"

    def test_whitespace_only_fails(self, free_text_node):
        """Should fail for whitespace-only text."""
        result = validate_free_text(free_text_node, "   ")
        assert result["valid"] is False
        assert result["reason"] == "empty_text"

    def test_none_input_fails(self, free_text_node):
        """Should fail for None input."""
        result = validate_free_text(free_text_node, None)
        assert result["valid"] is False
        assert result["reason"] == "empty_text"

    def test_minlength_pass(self, free_text_with_minlength):
        """Should pass when meeting minimum length."""
        result = validate_free_text(free_text_with_minlength, "Jo")
        assert result["valid"] is True

    def test_minlength_fail(self, free_text_with_minlength):
        """Should fail when below minimum length."""
        result = validate_free_text(free_text_with_minlength, "J")
        assert result["valid"] is False
        assert result["reason"] == "too_short"


class TestApplyValidationMeta:
    """Tests for apply_validation_meta function."""

    def test_no_validation_returns_none(self):
        """Should return None when no validation defined."""
        node = {"id": "q1", "type": "free_text"}
        assert apply_validation_meta(node, "any value") is None

    def test_regex_pass(self):
        """Should return None when regex matches."""
        node = {"id": "q1", "validation": {"kind": "regex", "pattern": r"^\d{10}$"}}
        assert apply_validation_meta(node, "1234567890") is None

    def test_regex_fail(self):
        """Should return 'regex_failed' when regex doesn't match."""
        node = {"id": "q1", "validation": {"kind": "regex", "pattern": r"^\d{10}$"}}
        assert apply_validation_meta(node, "123") == "regex_failed"

    def test_regex_invalid_pattern_continues(self):
        """Should continue when regex pattern is invalid."""
        node = {"id": "q1", "validation": {"kind": "regex", "pattern": r"[invalid"}}
        # Invalid regex should be skipped, returning None
        assert apply_validation_meta(node, "test") is None

    def test_range_within(self):
        """Should return None when value within range."""
        node = {"id": "q1", "validation": {"kind": "range", "min": 0, "max": 100}}
        assert apply_validation_meta(node, 50) is None

    def test_range_below_min(self):
        """Should return 'out_of_range' when below minimum."""
        node = {"id": "q1", "validation": {"kind": "range", "min": 10, "max": 100}}
        assert apply_validation_meta(node, 5) == "out_of_range"

    def test_range_above_max(self):
        """Should return 'out_of_range' when above maximum."""
        node = {"id": "q1", "validation": {"kind": "range", "min": 0, "max": 100}}
        assert apply_validation_meta(node, 150) == "out_of_range"

    def test_range_not_numeric(self):
        """Should return 'not_numeric' for non-numeric value."""
        node = {"id": "q1", "validation": {"kind": "range", "min": 0, "max": 100}}
        assert apply_validation_meta(node, "not a number") == "not_numeric"

    def test_minlength_pass(self):
        """Should return None when meeting minimum length."""
        node = {"id": "q1", "validation": {"kind": "minlength", "min": 5}}
        assert apply_validation_meta(node, "hello") is None

    def test_minlength_fail(self):
        """Should return 'too_short' when below minimum length."""
        node = {"id": "q1", "validation": {"kind": "minlength", "min": 5}}
        assert apply_validation_meta(node, "hi") == "too_short"

    def test_maxlength_pass(self):
        """Should return None when within maximum length."""
        node = {"id": "q1", "validation": {"kind": "maxlength", "max": 10}}
        assert apply_validation_meta(node, "hello") is None

    def test_maxlength_fail(self):
        """Should return 'too_long' when exceeding maximum length."""
        node = {"id": "q1", "validation": {"kind": "maxlength", "max": 5}}
        assert apply_validation_meta(node, "hello world") == "too_long"

    def test_validation_list(self):
        """Should process list of validations."""
        node = {
            "id": "q1",
            "validation": [
                {"kind": "minlength", "min": 2},
                {"kind": "maxlength", "max": 10},
            ],
        }
        assert apply_validation_meta(node, "hello") is None
        assert apply_validation_meta(node, "a") == "too_short"
        assert apply_validation_meta(node, "hello world!") == "too_long"

    def test_relative_date_range_within_past_days(self):
        """Should return None when date is within past N days."""
        node = {
            "id": "q1",
            "validation": {"kind": "relative_date_range", "past_days": 30},
        }
        yesterday = (date.today() - timedelta(days=1)).strftime("%m/%d/%Y")
        assert apply_validation_meta(node, yesterday) is None

    def test_relative_date_range_too_far_past(self):
        """Should return error when date is too far in the past."""
        node = {
            "id": "q1",
            "validation": {"kind": "relative_date_range", "past_days": 7},
        }
        long_ago = (date.today() - timedelta(days=30)).strftime("%m/%d/%Y")
        assert apply_validation_meta(node, long_ago) == "relative_date_out_of_range"

    def test_relative_date_range_future_not_allowed(self):
        """Should return error when future date not allowed."""
        node = {
            "id": "q1",
            "validation": {"kind": "relative_date_range", "past_days": 30},
        }
        tomorrow = (date.today() + timedelta(days=1)).strftime("%m/%d/%Y")
        assert apply_validation_meta(node, tomorrow) == "relative_date_out_of_range"

    def test_relative_date_range_with_future_allowed(self):
        """Should allow future dates when future_days specified."""
        node = {
            "id": "q1",
            "validation": {
                "kind": "relative_date_range",
                "past_days": 7,
                "future_days": 7,
            },
        }
        tomorrow = (date.today() + timedelta(days=1)).strftime("%m/%d/%Y")
        assert apply_validation_meta(node, tomorrow) is None

    def test_relative_date_range_invalid_date(self):
        """Should return 'invalid_date' for unparseable date."""
        node = {
            "id": "q1",
            "validation": {"kind": "relative_date_range", "past_days": 30},
        }
        assert apply_validation_meta(node, "not a date") == "invalid_date"

    def test_relative_date_range_empty_string(self):
        """Should return 'invalid_date' for empty string."""
        node = {
            "id": "q1",
            "validation": {"kind": "relative_date_range", "past_days": 30},
        }
        assert apply_validation_meta(node, "") == "invalid_date"

    def test_relative_date_range_accepts_date_object(self):
        """Should accept date object directly."""
        node = {
            "id": "q1",
            "validation": {"kind": "relative_date_range", "past_days": 30},
        }
        yesterday = date.today() - timedelta(days=1)
        assert apply_validation_meta(node, yesterday) is None


class TestValidateAnswer:
    """Tests for validate_answer dispatcher function."""

    def test_dispatches_to_single_choice(self):
        """Should dispatch to validate_single_choice for single_choice type."""
        node = {
            "id": "q1",
            "type": "single_choice",
            "options": [{"id": "yes", "value": "yes"}],
        }
        result = validate_answer(node, "yes")
        assert result["valid"] is True
        assert result["normalized"] == "yes"

    def test_dispatches_to_multi_choice(self):
        """Should dispatch to validate_multi_choice for multi_choice type."""
        node = {
            "id": "q1",
            "type": "multi_choice",
            "options": [{"value": "a"}, {"value": "b"}],
        }
        result = validate_answer(node, ["a", "b"])
        assert result["valid"] is True
        assert result["normalized"] == ["a", "b"]

    def test_dispatches_to_numeric(self):
        """Should dispatch to validate_numeric for numeric type."""
        node = {"id": "q1", "type": "numeric"}
        result = validate_answer(node, "42")
        assert result["valid"] is True
        assert result["normalized"] == 42.0

    def test_dispatches_to_free_text(self):
        """Should dispatch to validate_free_text for free_text type."""
        node = {"id": "q1", "type": "free_text"}
        result = validate_answer(node, "hello")
        assert result["valid"] is True
        assert result["normalized"] == "hello"

    def test_dispatches_to_free_text_for_date(self):
        """Should dispatch to validate_free_text for date type."""
        node = {"id": "q1", "type": "date"}
        result = validate_answer(node, "01/15/2000")
        assert result["valid"] is True
        assert result["normalized"] == "01/15/2000"

    def test_unknown_type_returns_not_interactive(self):
        """Should return not_interactive for unknown types."""
        node = {"id": "q1", "type": "unknown_type"}
        result = validate_answer(node, "anything")
        assert result["valid"] is False
        assert result["reason"] == "not_interactive"

    def test_handles_none_input_for_non_multi_choice(self):
        """Should convert None to empty string for non-multi_choice."""
        node = {"id": "q1", "type": "free_text"}
        result = validate_answer(node, None)
        assert result["valid"] is False
        assert result["reason"] == "empty_text"

    def test_skippable_free_text_accepts_none_as_null(self):
        """Skippable free-text nodes should accept None as a valid skipped answer."""
        node = {
            "id": "COACHING_EMAIL_V1",
            "type": "free_text",
            "skippable": True,
            "validation": [
                {
                    "kind": "regex",
                    "pattern": r"^[\w\.\-\+]+@[\w\.-]+\.\w{2,}$",
                }
            ],
        }

        result = validate_answer(node, None)

        assert result["valid"] is True
        assert result["normalized"] is None
        assert result["reason"] is None

    def test_non_skippable_free_text_still_rejects_none(self):
        """Non-skippable free-text nodes should still reject None."""
        node = {
            "id": "COACHING_FIRST_NAME_V1",
            "type": "free_text",
        }

        result = validate_answer(node, None)

        assert result["valid"] is False
        assert result["normalized"] is None
        assert result["reason"] == "empty_text"


class TestValidateYesNo:
    """A yes_no node is interactive and gets a spoken prompt, so it must also
    have a validator. Without one it fell through to "not_interactive" and
    every answer was rejected, sending the caller to the big model after two
    turns no matter what they said."""

    @pytest.fixture
    def node(self):
        return {"id": "q1", "type": "yes_no"}

    @pytest.mark.parametrize(
        "text", ["yes", "Yes", "  YES  ", "yeah", "yep", "y", "true", "correct"]
    )
    def test_affirmatives_normalise_to_yes(self, node, text):
        result = validate_yes_no(node, text)
        assert result["valid"] is True
        assert result["normalized"] == "yes"

    @pytest.mark.parametrize("text", ["no", "No", "nope", "nah", "n", "false"])
    def test_negatives_normalise_to_no(self, node, text):
        result = validate_yes_no(node, text)
        assert result["valid"] is True
        assert result["normalized"] == "no"

    def test_trailing_punctuation_is_tolerated(self, node):
        assert validate_yes_no(node, "Yes!")["normalized"] == "yes"

    @pytest.mark.parametrize("text", ["maybe", "", "   ", "I think so", "si"])
    def test_ambiguous_stays_invalid(self, node, text):
        """Ambiguity goes down the retry path rather than being guessed at.

        "si" is called out in the small-model prompt as something that must
        not be assumed to mean yes.
        """
        result = validate_yes_no(node, text)
        assert result["valid"] is False
        assert result["reason"] == "not_yes_or_no"

    def test_routed_from_validate_answer(self, node):
        """The bug was in the dispatch, not the validator, so cover the route."""
        result = validate_answer(node, "yes")
        assert result["valid"] is True
        assert result["normalized"] == "yes"

    def test_skippable_none_still_wins(self):
        result = validate_answer(
            {"id": "q1", "type": "yes_no", "skippable": True}, None
        )
        assert result["valid"] is True
        assert result["normalized"] is None
