"""Per-turn context passed from handle_prompt_message to outcome strategies."""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class TurnContext:
    """Holds per-turn data assembled by handle_prompt_message before outcome dispatch."""

    cur: Dict[str, Any]
    node: Dict[str, Any]
    node_id: str
    combined_user_text: str
    user_text: str
    interpretation: str
    reply: Optional[str]
    small_conf: float
    val_res: Dict[str, Any]
    small_resp: Dict[str, Any]
