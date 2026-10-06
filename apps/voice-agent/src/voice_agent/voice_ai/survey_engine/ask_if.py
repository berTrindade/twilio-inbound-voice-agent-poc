# ask_if.py
import logging
from datetime import date
from dateutil import parser as date_parser
from typing import Any, Dict, Optional, List

logger = logging.getLogger(__name__)


def compute_age_years(dob_raw: str) -> Optional[int]:
    if not dob_raw:
        return None

    raw = dob_raw.strip()
    try:
        dob = date_parser.parse(raw, dayfirst=False, yearfirst=False).date()
    except Exception:
        return None

    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def get_answer_values(answers: Dict[str, Any], question_id: str) -> List[Any]:
    val = answers.get(question_id)
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def eval_ask_if(expr: Optional[Dict[str, Any]], answers: Dict[str, Any]) -> bool:
    if not expr:
        return False

    # answered
    if "answered" in expr:
        spec = expr["answered"]
        qid = spec.get("question_id")
        allowed = set(spec.get("in", []))
        vals = get_answer_values(answers, qid)
        return any(v in allowed for v in vals)

    # api_in
    if "api_in" in expr:
        spec = expr["api_in"]
        qid = spec.get("question_id")
        allowed = set(spec.get("values", []))
        vals = get_answer_values(answers, qid)
        return any(v in allowed for v in vals)

    # lt
    if "lt" in expr:
        spec = expr["lt"]
        qid = spec.get("question_id")
        threshold = spec.get("value")
        try:
            v = float(answers.get(qid))
            return v < float(threshold)
        except Exception:
            return False

    # age_lt / age_gte
    if "age_lt" in expr or "age_gte" in expr:
        if "age_lt" in expr:
            spec = expr["age_lt"]
            op = "lt"
        else:
            spec = expr["age_gte"]
            op = "gte"

        qid = spec.get("question_id")
        years = spec.get("years")
        raw = str(answers.get(qid, "")).strip()

        if not qid or years is None:
            return False

        if not raw:
            logger.warning(f"[ask_if age] Missing DOB for {qid}. Skipping age branch.")
            return False

        age = compute_age_years(raw)
        if age is None:
            return False

        return age < years if op == "lt" else age >= years

    # and/or/not
    if "and" in expr:
        return all(eval_ask_if(e, answers) for e in expr["and"])
    if "or" in expr:
        return any(eval_ask_if(e, answers) for e in expr["or"])
    if "not" in expr:
        return not eval_ask_if(expr["not"], answers)

    # legacy
    if "equals" in expr:
        spec = expr["equals"]
        qid = spec.get("question_id")
        val = spec.get("value")
        return answers.get(qid) == val

    if "exists" in expr:
        qid = expr["exists"].get("question_id")
        return qid in answers

    return False
