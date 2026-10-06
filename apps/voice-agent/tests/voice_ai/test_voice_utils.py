"""Tests for voice_utils module."""

import pytest
from voice_agent.voice_ai.voice_utils import (
    safe_json_loads,
    extract_number,
    resolve_option_token,
)


class TestSafeJsonLoads:
    """Tests for safe_json_loads function."""

    def test_valid_json_object(self):
        """Should parse valid JSON object."""
        result = safe_json_loads('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_valid_json_array(self):
        """Should parse valid JSON array."""
        result = safe_json_loads("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_valid_json_with_nested_objects(self):
        """Should parse nested JSON structures."""
        result = safe_json_loads('{"outer": {"inner": "value"}}')
        assert result == {"outer": {"inner": "value"}}

    def test_invalid_json_returns_none(self):
        """Should return None for completely invalid JSON."""
        result = safe_json_loads("not json at all")
        assert result is None

    def test_extracts_json_from_mixed_text(self):
        """Should extract JSON object from text with surrounding content."""
        result = safe_json_loads('Some text before {"answer": "yes"} and after')
        assert result == {"answer": "yes"}

    def test_greedy_match_with_multiple_blocks_fails(self):
        """Greedy regex matches full span, so multiple blocks may fail."""
        # The regex is greedy, so it matches from first { to last }
        # which creates invalid JSON when there's text between blocks
        result = safe_json_loads('Text {"first": 1} more {"second": 2}')
        # This returns None because the greedy match creates invalid JSON
        assert result is None

    def test_handles_json_with_newlines(self):
        """Should handle JSON with newlines."""
        result = safe_json_loads('{\n  "key": "value"\n}')
        assert result == {"key": "value"}

    def test_empty_string_returns_none(self):
        """Should return None for empty string."""
        result = safe_json_loads("")
        assert result is None

    def test_malformed_extracted_json_returns_none(self):
        """Should return None if extracted block is not valid JSON."""
        result = safe_json_loads("Text {not: valid json} more")
        assert result is None


class TestExtractNumber:
    """Tests for extract_number function."""

    def test_extracts_integer(self):
        """Should extract positive integer."""
        assert extract_number("42") == 42.0

    def test_extracts_decimal(self):
        """Should extract decimal number."""
        assert extract_number("3.14") == 3.14

    def test_extracts_negative_integer(self):
        """Should extract negative integer."""
        assert extract_number("-10") == -10.0

    def test_extracts_negative_decimal(self):
        """Should extract negative decimal."""
        assert extract_number("-2.5") == -2.5

    def test_extracts_number_from_text(self):
        """Should extract number embedded in text."""
        assert extract_number("I am 25 years old") == 25.0

    def test_extracts_first_number(self):
        """Should extract first number when multiple exist."""
        assert extract_number("Between 10 and 20") == 10.0

    def test_returns_none_for_no_number(self):
        """Should return None when no number present."""
        assert extract_number("no numbers here") is None

    def test_returns_none_for_none_input(self):
        """Should return None for None input."""
        assert extract_number(None) is None

    def test_returns_none_for_empty_string(self):
        """Should return None for empty string."""
        assert extract_number("") is None

    def test_extracts_number_with_plus_sign(self):
        """Should extract number with plus sign."""
        assert extract_number("+5") == 5.0

    def test_extracts_zero(self):
        """Should extract zero."""
        assert extract_number("0") == 0.0


class TestResolveOptionToken:
    """Tests for resolve_option_token function."""

    @pytest.fixture
    def sample_options(self):
        """Sample options for testing."""
        return [
            {"id": "opt_yes", "value": "yes", "label": "Yes"},
            {"id": "opt_no", "value": "no", "label": "No"},
            {"id": "opt_maybe", "value": "maybe", "label": "Maybe"},
        ]

    def test_exact_match_by_value(self, sample_options):
        """Should match by exact value."""
        result = resolve_option_token("yes", sample_options)
        assert result == "opt_yes"

    def test_exact_match_by_id(self, sample_options):
        """Should match by exact id."""
        result = resolve_option_token("opt_no", sample_options)
        assert result == "opt_no"

    def test_case_insensitive_match(self, sample_options):
        """Should match case insensitively."""
        result = resolve_option_token("YES", sample_options)
        assert result == "opt_yes"

    def test_match_with_whitespace(self, sample_options):
        """Should handle whitespace."""
        result = resolve_option_token("  yes  ", sample_options)
        assert result == "opt_yes"

    def test_letter_a_matches_first_option(self, sample_options):
        """Letter 'a' should match first option."""
        result = resolve_option_token("a", sample_options)
        assert result == "opt_yes"

    def test_letter_b_matches_second_option(self, sample_options):
        """Letter 'b' should match second option."""
        result = resolve_option_token("b", sample_options)
        assert result == "opt_no"

    def test_letter_c_matches_third_option(self, sample_options):
        """Letter 'c' should match third option."""
        result = resolve_option_token("c", sample_options)
        assert result == "opt_maybe"

    def test_letter_uppercase_matches(self, sample_options):
        """Uppercase letter should match."""
        result = resolve_option_token("A", sample_options)
        assert result == "opt_yes"

    def test_letter_out_of_range_returns_none(self, sample_options):
        """Letter beyond options count should return None."""
        result = resolve_option_token("z", sample_options)
        assert result is None

    def test_no_match_returns_none(self, sample_options):
        """Should return None when no match found."""
        result = resolve_option_token("unknown", sample_options)
        assert result is None

    def test_empty_string_returns_none(self, sample_options):
        """Should return None for empty string."""
        result = resolve_option_token("", sample_options)
        assert result is None

    def test_none_input_returns_none(self, sample_options):
        """Should return None for None input."""
        result = resolve_option_token(None, sample_options)
        assert result is None

    def test_empty_options_returns_none(self):
        """Should return None when options list is empty."""
        result = resolve_option_token("yes", [])
        assert result is None

    def test_options_without_id_uses_value(self):
        """Should use value when id is missing."""
        options = [{"value": "apple"}, {"value": "banana"}]
        result = resolve_option_token("apple", options)
        assert result == "apple"

    def test_options_with_only_id(self):
        """Should match by id when value is missing."""
        options = [{"id": "first"}, {"id": "second"}]
        result = resolve_option_token("first", options)
        assert result == "first"

    def test_fallback_to_positional_id(self):
        """Should generate positional id when both id and value missing."""
        options = [{"label": "Option 1"}, {"label": "Option 2"}]
        result = resolve_option_token("a", options)
        assert result == "opt_0"
