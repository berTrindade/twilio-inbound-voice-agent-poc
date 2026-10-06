"""Tests for ask_if module."""

from freezegun import freeze_time
from voice_agent.voice_ai.survey_engine.ask_if import (
    compute_age_years,
    get_answer_values,
    eval_ask_if,
)


class TestComputeAgeYears:
    """Tests for compute_age_years function."""

    @freeze_time("2024-06-15")
    def test_computes_age_correctly(self):
        """Should compute age in years correctly."""
        # Born June 15, 1990 -> exactly 34 years old
        assert compute_age_years("06/15/1990") == 34

    @freeze_time("2024-06-15")
    def test_age_before_birthday_this_year(self):
        """Should compute age correctly before birthday has occurred."""
        # Born December 15, 1990 -> still 33 (birthday hasn't happened)
        assert compute_age_years("12/15/1990") == 33

    @freeze_time("2024-06-15")
    def test_age_after_birthday_this_year(self):
        """Should compute age correctly after birthday has occurred."""
        # Born January 15, 1990 -> already 34 (birthday has passed)
        assert compute_age_years("01/15/1990") == 34

    @freeze_time("2024-06-15")
    def test_various_date_formats(self):
        """Should parse various date formats."""
        # MM/DD/YYYY (US format)
        assert compute_age_years("01/15/2000") == 24
        # YYYY-MM-DD (ISO format)
        assert compute_age_years("2000-01-15") == 24
        # Month name
        assert compute_age_years("January 15, 2000") == 24

    def test_empty_string_returns_none(self):
        """Should return None for empty string."""
        assert compute_age_years("") is None

    def test_none_returns_none(self):
        """Should return None for None input."""
        assert compute_age_years(None) is None

    def test_whitespace_only_returns_none(self):
        """Should return None for whitespace-only string."""
        assert compute_age_years("   ") is None

    def test_invalid_date_returns_none(self):
        """Should return None for invalid date string."""
        assert compute_age_years("not a date") is None

    def test_strips_whitespace(self):
        """Should strip whitespace from input."""
        result = compute_age_years("  01/15/2000  ")
        assert result is not None


class TestGetAnswerValues:
    """Tests for get_answer_values helper function."""

    def test_returns_list_for_list_value(self):
        """Should return list as-is when value is a list."""
        answers = {"q1": ["a", "b", "c"]}
        assert get_answer_values(answers, "q1") == ["a", "b", "c"]

    def test_wraps_single_value_in_list(self):
        """Should wrap single value in list."""
        answers = {"q1": "yes"}
        assert get_answer_values(answers, "q1") == ["yes"]

    def test_returns_empty_list_for_none(self):
        """Should return empty list when value is None."""
        answers = {"q1": None}
        assert get_answer_values(answers, "q1") == []

    def test_returns_empty_list_for_missing_key(self):
        """Should return empty list for missing question."""
        answers = {"q1": "yes"}
        assert get_answer_values(answers, "q2") == []


class TestEvalAskIfAnswered:
    """Tests for eval_ask_if with 'answered' operator."""

    def test_answered_in_list_returns_true(self):
        """Should return True when answer is in allowed list."""
        expr = {"answered": {"question_id": "q1", "in": ["yes", "maybe"]}}
        answers = {"q1": "yes"}
        assert eval_ask_if(expr, answers) is True

    def test_answered_not_in_list_returns_false(self):
        """Should return False when answer is not in allowed list."""
        expr = {"answered": {"question_id": "q1", "in": ["yes", "maybe"]}}
        answers = {"q1": "no"}
        assert eval_ask_if(expr, answers) is False

    def test_answered_with_multi_choice(self):
        """Should work with multi-choice answers (list)."""
        expr = {"answered": {"question_id": "q1", "in": ["red", "blue"]}}
        answers = {"q1": ["red", "green"]}
        assert eval_ask_if(expr, answers) is True  # red is in the allowed list

    def test_answered_missing_question(self):
        """Should return False for missing question."""
        expr = {"answered": {"question_id": "q1", "in": ["yes"]}}
        answers = {}
        assert eval_ask_if(expr, answers) is False


class TestEvalAskIfApiIn:
    """Tests for eval_ask_if with 'api_in' operator."""

    def test_api_in_returns_true(self):
        """Should return True when API result is in values."""
        expr = {
            "api_in": {"question_id": "api_check", "values": ["ELIGIBLE", "PENDING"]}
        }
        answers = {"api_check": "ELIGIBLE"}
        assert eval_ask_if(expr, answers) is True

    def test_api_in_returns_false(self):
        """Should return False when API result is not in values."""
        expr = {"api_in": {"question_id": "api_check", "values": ["ELIGIBLE"]}}
        answers = {"api_check": "NOT_ELIGIBLE"}
        assert eval_ask_if(expr, answers) is False

    def test_api_in_with_list_value(self):
        """Should work with list values."""
        expr = {
            "api_in": {"question_id": "api_check", "values": ["SUCCESS", "PARTIAL"]}
        }
        answers = {"api_check": ["SUCCESS", "OTHER"]}
        assert eval_ask_if(expr, answers) is True


class TestEvalAskIfLt:
    """Tests for eval_ask_if with 'lt' (less than) operator."""

    def test_lt_returns_true_when_below(self):
        """Should return True when value is below threshold."""
        expr = {"lt": {"question_id": "score", "value": 50}}
        answers = {"score": 30}
        assert eval_ask_if(expr, answers) is True

    def test_lt_returns_false_when_equal(self):
        """Should return False when value equals threshold."""
        expr = {"lt": {"question_id": "score", "value": 50}}
        answers = {"score": 50}
        assert eval_ask_if(expr, answers) is False

    def test_lt_returns_false_when_above(self):
        """Should return False when value is above threshold."""
        expr = {"lt": {"question_id": "score", "value": 50}}
        answers = {"score": 75}
        assert eval_ask_if(expr, answers) is False

    def test_lt_with_string_value(self):
        """Should convert string to float for comparison."""
        expr = {"lt": {"question_id": "score", "value": 50}}
        answers = {"score": "30"}
        assert eval_ask_if(expr, answers) is True

    def test_lt_with_invalid_value_returns_false(self):
        """Should return False for non-numeric values."""
        expr = {"lt": {"question_id": "score", "value": 50}}
        answers = {"score": "not a number"}
        assert eval_ask_if(expr, answers) is False

    def test_lt_missing_question_returns_false(self):
        """Should return False for missing question."""
        expr = {"lt": {"question_id": "score", "value": 50}}
        answers = {}
        assert eval_ask_if(expr, answers) is False


class TestEvalAskIfAgeLt:
    """Tests for eval_ask_if with 'age_lt' operator."""

    @freeze_time("2024-06-15")
    def test_age_lt_returns_true_when_younger(self):
        """Should return True when age is below threshold."""
        expr = {"age_lt": {"question_id": "dob", "years": 18}}
        answers = {"dob": "06/15/2010"}  # 14 years old
        assert eval_ask_if(expr, answers) is True

    @freeze_time("2024-06-15")
    def test_age_lt_returns_false_when_equal(self):
        """Should return False when age equals threshold."""
        expr = {"age_lt": {"question_id": "dob", "years": 18}}
        answers = {"dob": "06/15/2006"}  # exactly 18
        assert eval_ask_if(expr, answers) is False

    @freeze_time("2024-06-15")
    def test_age_lt_returns_false_when_older(self):
        """Should return False when age is above threshold."""
        expr = {"age_lt": {"question_id": "dob", "years": 18}}
        answers = {"dob": "06/15/1990"}  # 34 years old
        assert eval_ask_if(expr, answers) is False

    def test_age_lt_missing_dob_returns_false(self):
        """Should return False when DOB is missing."""
        expr = {"age_lt": {"question_id": "dob", "years": 18}}
        answers = {}
        assert eval_ask_if(expr, answers) is False

    def test_age_lt_invalid_dob_returns_false(self):
        """Should return False for invalid DOB."""
        expr = {"age_lt": {"question_id": "dob", "years": 18}}
        answers = {"dob": "not a date"}
        assert eval_ask_if(expr, answers) is False

    def test_age_lt_missing_years_returns_false(self):
        """Should return False when years threshold is missing."""
        expr = {"age_lt": {"question_id": "dob"}}
        answers = {"dob": "06/15/2010"}
        assert eval_ask_if(expr, answers) is False


class TestEvalAskIfAgeGte:
    """Tests for eval_ask_if with 'age_gte' operator."""

    @freeze_time("2024-06-15")
    def test_age_gte_returns_true_when_older(self):
        """Should return True when age is at or above threshold."""
        expr = {"age_gte": {"question_id": "dob", "years": 18}}
        answers = {"dob": "06/15/1990"}  # 34 years old
        assert eval_ask_if(expr, answers) is True

    @freeze_time("2024-06-15")
    def test_age_gte_returns_true_when_equal(self):
        """Should return True when age equals threshold."""
        expr = {"age_gte": {"question_id": "dob", "years": 18}}
        answers = {"dob": "06/15/2006"}  # exactly 18
        assert eval_ask_if(expr, answers) is True

    @freeze_time("2024-06-15")
    def test_age_gte_returns_false_when_younger(self):
        """Should return False when age is below threshold."""
        expr = {"age_gte": {"question_id": "dob", "years": 18}}
        answers = {"dob": "06/15/2010"}  # 14 years old
        assert eval_ask_if(expr, answers) is False


class TestEvalAskIfLogicalOperators:
    """Tests for eval_ask_if with logical operators (and, or, not)."""

    def test_and_all_true(self):
        """Should return True when all conditions are true."""
        expr = {
            "and": [
                {"answered": {"question_id": "q1", "in": ["yes"]}},
                {"answered": {"question_id": "q2", "in": ["yes"]}},
            ]
        }
        answers = {"q1": "yes", "q2": "yes"}
        assert eval_ask_if(expr, answers) is True

    def test_and_one_false(self):
        """Should return False when any condition is false."""
        expr = {
            "and": [
                {"answered": {"question_id": "q1", "in": ["yes"]}},
                {"answered": {"question_id": "q2", "in": ["yes"]}},
            ]
        }
        answers = {"q1": "yes", "q2": "no"}
        assert eval_ask_if(expr, answers) is False

    def test_or_one_true(self):
        """Should return True when any condition is true."""
        expr = {
            "or": [
                {"answered": {"question_id": "q1", "in": ["yes"]}},
                {"answered": {"question_id": "q2", "in": ["yes"]}},
            ]
        }
        answers = {"q1": "no", "q2": "yes"}
        assert eval_ask_if(expr, answers) is True

    def test_or_all_false(self):
        """Should return False when all conditions are false."""
        expr = {
            "or": [
                {"answered": {"question_id": "q1", "in": ["yes"]}},
                {"answered": {"question_id": "q2", "in": ["yes"]}},
            ]
        }
        answers = {"q1": "no", "q2": "no"}
        assert eval_ask_if(expr, answers) is False

    def test_not_negates_true(self):
        """Should negate True to False."""
        expr = {"not": {"answered": {"question_id": "q1", "in": ["yes"]}}}
        answers = {"q1": "yes"}
        assert eval_ask_if(expr, answers) is False

    def test_not_negates_false(self):
        """Should negate False to True."""
        expr = {"not": {"answered": {"question_id": "q1", "in": ["yes"]}}}
        answers = {"q1": "no"}
        assert eval_ask_if(expr, answers) is True

    def test_nested_logical_operators(self):
        """Should handle nested logical operators."""
        # (q1 = yes) AND (q2 = yes OR q3 = yes)
        expr = {
            "and": [
                {"answered": {"question_id": "q1", "in": ["yes"]}},
                {
                    "or": [
                        {"answered": {"question_id": "q2", "in": ["yes"]}},
                        {"answered": {"question_id": "q3", "in": ["yes"]}},
                    ]
                },
            ]
        }
        answers = {"q1": "yes", "q2": "no", "q3": "yes"}
        assert eval_ask_if(expr, answers) is True


class TestEvalAskIfLegacyOperators:
    """Tests for eval_ask_if with legacy operators (equals, exists)."""

    def test_equals_returns_true(self):
        """Should return True when values are equal."""
        expr = {"equals": {"question_id": "q1", "value": "yes"}}
        answers = {"q1": "yes"}
        assert eval_ask_if(expr, answers) is True

    def test_equals_returns_false(self):
        """Should return False when values differ."""
        expr = {"equals": {"question_id": "q1", "value": "yes"}}
        answers = {"q1": "no"}
        assert eval_ask_if(expr, answers) is False

    def test_exists_returns_true(self):
        """Should return True when question exists."""
        expr = {"exists": {"question_id": "q1"}}
        answers = {"q1": "any value"}
        assert eval_ask_if(expr, answers) is True

    def test_exists_returns_false(self):
        """Should return False when question doesn't exist."""
        expr = {"exists": {"question_id": "q1"}}
        answers = {"q2": "other"}
        assert eval_ask_if(expr, answers) is False


class TestEvalAskIfEdgeCases:
    """Tests for eval_ask_if edge cases."""

    def test_none_expr_returns_false(self):
        """Should return False for None expression."""
        assert eval_ask_if(None, {}) is False

    def test_empty_expr_returns_false(self):
        """Should return False for empty expression."""
        assert eval_ask_if({}, {}) is False

    def test_unknown_operator_returns_false(self):
        """Should return False for unknown operator."""
        expr = {"unknown_op": {"question_id": "q1"}}
        assert eval_ask_if(expr, {}) is False
