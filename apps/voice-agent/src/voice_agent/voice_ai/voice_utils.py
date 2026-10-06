import json
import re
from typing import Any, Dict, List, Optional


def safe_json_loads(text: str):
    try:
        return json.loads(text)
    except Exception:
        # attempt to extract the first {...} block
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None


def extract_number(text: str):
    if text is None:
        return None
    m = re.search(r"[-+]?\d+(\.\d+)?", str(text))
    return float(m.group(0)) if m else None


def resolve_option_token(text: str, options: List[Dict[str, Any]]) -> Optional[str]:
    """
    Deterministically resolve a single token to an option.

    Rules:
      1) Exact match on option.value (preferred) or option.id.
      2) Single-letter answers ('a', 'b', 'c', ...) map by position.
      3) Otherwise: no match.

    Returns:
      choice_id (string) if a match is found, otherwise None.
    """
    if not options:
        return None

    t = (text or "").strip().lower()
    if not t:
        return None

    letters = "abcdefghijklmnopqrstuvwxyz"

    # 1) Exact match on option.value or option.id
    for idx, opt in enumerate(options):
        value = str(opt.get("value") or "").strip().lower()
        oid = str(opt.get("id") or "").strip().lower()

        if t == value or (oid and t == oid):
            return opt.get("id") or opt.get("value") or f"opt_{idx}"

    # 2) Letter mapping: 'a' → first, 'b' → second, etc.
    if len(t) == 1 and t in letters:
        idx = letters.index(t)
        if idx < len(options):
            opt = options[idx]
            return opt.get("id") or opt.get("value") or f"opt_{idx}"

    # 3) No match
    return None
