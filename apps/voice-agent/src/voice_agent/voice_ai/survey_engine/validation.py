# validation.py
import re
from typing import Any, Dict, List
from .types import ValidationResult
from .types import Node
from ..voice_utils import resolve_option_token, extract_number
from datetime import date, datetime
from dateutil import parser as date_parser


def apply_validation_meta(node: Node, normalized: Any) -> str | None:
    raw = node.get("validation") or None

    validations: List[Dict[str, Any]] = []
    if isinstance(raw, dict):
        validations = [raw]
    elif isinstance(raw, list):
        validations = list(raw)

    if not validations:
        return None

    for v in validations:
        kind = v.get("kind")
        if not kind:
            continue

        if kind == "regex":
            pattern = v.get("pattern")
            if not pattern:
                continue
            try:
                if isinstance(normalized, str) and re.match(pattern, normalized):
                    continue
                return "regex_failed"
            except re.error:
                continue

        elif kind == "range":
            lo = v.get("min")
            hi = v.get("max")
            try:
                x = float(normalized)
            except Exception:
                return "not_numeric"
            if lo is not None and x < lo:
                return "out_of_range"
            if hi is not None and x > hi:
                return "out_of_range"

        elif kind == "minlength":
            if len(normalized) < v.get("min", 0):
                return "too_short"

        elif kind == "maxlength":
            if len(normalized) > v.get("max", 999999):
                return "too_long"

        elif kind == "relative_date_range":
            # Enforce a relative window around "today",
            # e.g. last N days, next M days, or both.
            past_days = v.get("past_days")
            future_days = v.get("future_days")

            # Try to parse the normalized value as a date.
            # We use US-friendly parsing: month/day/year style by default.
            parsed_date: date | None = None

            if isinstance(normalized, datetime):
                # Convert datetime → date
                parsed_date = normalized.date()

            elif isinstance(normalized, date):
                # Already a date object
                parsed_date = normalized

            elif isinstance(normalized, str):
                raw_str = normalized.strip()
                if not raw_str:
                    return "invalid_date"
                try:
                    parsed_date = date_parser.parse(
                        raw_str,
                        dayfirst=False,  # US parsing
                        yearfirst=False,
                    ).date()
                except Exception:
                    return "invalid_date"

            else:
                # Unsupported type
                return "invalid_date"

            today = date.today()
            delta_days = (parsed_date - today).days

            # Interpret constraints:
            # - both past_days & future_days: within [-past_days, +future_days]
            # - only past_days: within last N days, not in the future
            # - only future_days: within next N days, not in the past
            try:
                if past_days is not None:
                    past_days = int(past_days)
                if future_days is not None:
                    future_days = int(future_days)
            except Exception:
                # If config is malformed, don't block the user
                continue

            out_of_range = False

            if past_days is not None and future_days is not None:
                if delta_days < -past_days or delta_days > future_days:
                    out_of_range = True
            elif past_days is not None:
                # "within the last N days" → not older than N days and not in the future
                if delta_days < -past_days or delta_days > 0:
                    out_of_range = True
            elif future_days is not None:
                # "within the next N days" → not in the past and not beyond N days ahead
                if delta_days < 0 or delta_days > future_days:
                    out_of_range = True
            else:
                # No usable constraints → skip
                out_of_range = False

            if out_of_range:
                return "relative_date_out_of_range"

    return None


def validate_single_choice(node: Node, user_text: str) -> ValidationResult:
    opts = node.get("options") or []
    choice_id = resolve_option_token(user_text, opts)

    if not choice_id:
        return ValidationResult(
            valid=False, normalized=None, reason="could_not_match_option"
        )

    reason = apply_validation_meta(node, choice_id)
    if reason is None:
        return ValidationResult(valid=True, normalized=choice_id, reason=None)

    return ValidationResult(valid=False, normalized=None, reason=reason)


_YES = {"yes", "y", "yeah", "yep", "yup", "true", "correct", "affirmative"}
_NO = {"no", "n", "nope", "nah", "false", "incorrect", "negative"}


def validate_yes_no(node: Node, user_text: str) -> ValidationResult:
    """Normalise an affirmative or negative to the literal "yes" / "no".

    The extra spellings here are tolerance for a model that answers in its own
    words, not an attempt to parse arbitrary speech: anything outside the two
    sets stays invalid so an ambiguous reply goes down the retry path instead of
    being guessed at.
    """
    val = (user_text or "").strip().lower().rstrip(".!")
    if val in _YES:
        return ValidationResult(valid=True, normalized="yes", reason=None)
    if val in _NO:
        return ValidationResult(valid=True, normalized="no", reason=None)
    return ValidationResult(valid=False, normalized=None, reason="not_yes_or_no")


def _normalize_multi_choice_selection(user_value: Any, opts: list) -> List[str]:
    """
    Normalize multi-choice input into a list of canonical option ids/values.

    - If user_value is a list (already normalized by LLM), we:
        * lower+strip each element
        * keep only values that match an option's value/id
    - If user_value is a string (raw STT), we:
        * split on commas / "and" / "&"
        * resolve each token via resolve_option_token(...)
    """
    import re

    selected: List[str] = []

    # Case 1: already-normalized list from LLM (e.g. ["white", "asian"])
    if isinstance(user_value, list):
        allowed = {
            str(o.get("value") or o.get("id") or "").strip().lower() for o in opts
        }

        for v in user_value:
            if v is None:
                continue
            key = str(v).strip().lower()
            if key in allowed and key not in selected:
                selected.append(key)

        return selected

    # Case 2: free-text answer (existing behaviour)
    user_text = str(user_value or "").strip()
    if not user_text:
        return []

    parts = re.split(r"[,\u200b]| and | & ", user_text, flags=re.I)
    for token in parts:
        token = token.strip()
        if not token:
            continue
        cid = resolve_option_token(token, opts)
        if cid and cid not in selected:
            selected.append(cid)

    return selected


def validate_multi_choice(node: Node, user_value: Any) -> ValidationResult:
    opts = node.get("options") or []

    if user_value is None:
        return ValidationResult(valid=False, normalized=None, reason="empty_text")

    selected = _normalize_multi_choice_selection(user_value, opts)

    if not selected:
        return ValidationResult(
            valid=False,
            normalized=None,
            reason="no_options_matched",
        )

    reason = apply_validation_meta(node, selected)
    if reason is None:
        return ValidationResult(valid=True, normalized=selected, reason=None)

    return ValidationResult(valid=False, normalized=None, reason=reason)


def validate_numeric(node: Node, user_text: str) -> ValidationResult:
    num = extract_number(user_text)
    if num is None:
        return ValidationResult(valid=False, normalized=None, reason="no_number_found")

    lo = node.get("min")
    hi = node.get("max")
    if lo is not None and num < lo:
        return ValidationResult(valid=False, normalized=None, reason="out_of_range")
    if hi is not None and num > hi:
        return ValidationResult(valid=False, normalized=None, reason="out_of_range")

    vr = apply_validation_meta(node, num)
    if vr is None:
        return ValidationResult(valid=True, normalized=num, reason=None)

    return ValidationResult(valid=False, normalized=None, reason=vr)


def validate_free_text(node: Node, user_text: str) -> ValidationResult:
    val = (user_text or "").strip()
    if not val:
        return ValidationResult(valid=False, normalized=None, reason="empty_text")

    vr = apply_validation_meta(node, val)
    if vr is None:
        return ValidationResult(valid=True, normalized=val, reason=None)

    return ValidationResult(valid=False, normalized=None, reason=vr)


def validate_answer(node: Node, user_text: Any) -> ValidationResult:
    t = node.get("type")

    # Skippable nodes may be recorded as real JSON null / Python None.
    # The LLM decides when to skip by returning answer.value = None.
    if bool(node.get("skippable")) and user_text is None:
        return ValidationResult(
            valid=True,
            normalized=None,
            reason=None,
        )

    if t == "multi_choice":
        return validate_multi_choice(node, user_text)

    # For all *other* types, normalize everything to string
    user_text = "" if user_text is None else str(user_text)

    if t == "single_choice":
        return validate_single_choice(node, user_text)

    if t == "yes_no":
        return validate_yes_no(node, user_text)

    if t == "numeric":
        return validate_numeric(node, user_text)

    if t in {"free_text", "date"}:
        return validate_free_text(node, user_text)

    return ValidationResult(valid=False, normalized=None, reason="not_interactive")
