# types.py
from typing import Any, Optional, TypedDict, Dict


class ValidationResult(TypedDict):
    valid: bool
    normalized: Any
    reason: Optional[str]


Node = Dict[str, Any]
