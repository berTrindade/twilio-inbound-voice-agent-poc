# engine.py
from typing import Any, Dict, Optional, Tuple, Callable
from .types import ValidationResult
from .validation import validate_answer
from .ask_if import eval_ask_if
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PendingHandoverContext:
    node_id: str | None
    whisper_text: str | None


class SurveyEngine:

    def __init__(
        self,
        survey: Dict[str, Any],
        initial_node_id: str,
        api_node_handler: Optional[
            Callable[[str, Dict[str, Any], Dict[str, Any]], Optional[str]]
        ] = None,
    ):
        self.nodes: Dict[str, Dict[str, Any]] = self._to_nodes_map(survey)
        self.initial_node_id = initial_node_id
        self.answers: Dict[str, Any] = {}
        self.current_id: Optional[str] = initial_node_id
        self.nudge_count = 0
        self.api_node_handler = api_node_handler

        # Set when a handover_to_coach node is reached during traversal.
        # The adapter surfaces this to the websocket to trigger a real PSTN handover.
        self.pending_handover_context: Optional[PendingHandoverContext] = None

    # --- node helpers ---
    def consume_pending_handover(self) -> Optional[PendingHandoverContext]:
        ctx = self.pending_handover_context
        self.pending_handover_context = None
        return ctx

    def _get(self, nid) -> Optional[Dict[str, Any]]:
        if nid is None:
            return None

        return self.nodes.get(nid)

    def get_node(self, nid: str) -> Dict[str, Any]:
        node = self._get(nid)
        if node is None:
            raise KeyError(f"Node not found: {nid}")
        return node

    # --- interactive logic ---
    def _is_interactive(self, node: Dict[str, Any]) -> bool:
        return node.get("type") in {
            "single_choice",
            "multi_choice",
            "yes_no",
            "numeric",
            "free_text",
        }

    # --- main traversal ---
    def advance_to_interactive(self) -> Tuple[str, str, Optional[bool], Optional[bool]]:
        spoken_parts = []
        visited = set()
        spoken_interruptible = None
        spoken_preemptible = None

        while self.current_id:
            if self.current_id in visited:
                break
            visited.add(self.current_id)

            node = self._get(self.current_id)
            if not node:
                break

            ask_if = node.get("ask_if")
            if ask_if and not eval_ask_if(ask_if, self.answers):
                self.current_id = node.get("next_id")
                continue

            node_type = node.get("type")

            # narration / interstitial / api_call / handover_to_coach
            if node_type in (
                "narration",
                "interstitial",
                "api_call",
                "handover_to_coach",
            ):
                if node.get("text"):
                    spoken_parts.append(node["text"])
                    # Combine flags across spoken nodes using a most-restrictive-wins rule
                    # (if any node sets interruptible/preemptible to False, the intro stays False).
                    node_interruptible = node.get("interruptible")
                    node_preemptible = node.get("preemptible")

                    if node_interruptible is not None:
                        spoken_interruptible = (
                            node_interruptible
                            if spoken_interruptible is None
                            else spoken_interruptible and node_interruptible
                        )

                    if node_preemptible is not None:
                        spoken_preemptible = (
                            node_preemptible
                            if spoken_preemptible is None
                            else spoken_preemptible and node_preemptible
                        )

                if node_type == "handover_to_coach":
                    # Signal the adapter/websocket to trigger a real coach handover.
                    self.current_id = None
                    self.pending_handover_context = PendingHandoverContext(
                        node_id=node.get("id"),
                        whisper_text=node.get("whisper_text"),
                    )
                    break

                if node_type == "api_call":
                    api_cfg = node.get("api") or {}
                    expected = api_cfg.get("expected_responses") or []

                    # Try to call the API handler if provided
                    api_result = None
                    if self.api_node_handler:
                        try:
                            api_result = self.api_node_handler(
                                node["id"], api_cfg, self.answers
                            )
                        except Exception as e:
                            logger.error(
                                "API call handler failed",
                                extra={
                                    "node_id": node["id"],
                                    "error": str(e),
                                    "error_type": type(e).__name__,
                                },
                                exc_info=True,
                            )

                    # Use API result if available, otherwise fall back to mock
                    if api_result is not None:
                        self.answers[node["id"]] = api_result
                    elif expected:
                        self.answers[node["id"]] = expected[1]

                self.current_id = node.get("next_id")
                continue

            if self._is_interactive(node):
                self.nudge_count = 0
                break

            break

        return (
            " ".join(spoken_parts).strip(),
            self.current_id or "",
            spoken_interruptible,
            spoken_preemptible,
        )

    # --- validation wrapper ---
    def validate(self, node_id: str, user_text: Any) -> ValidationResult:
        node = self.get_node(node_id)
        if not node:
            return ValidationResult(
                valid=False,
                normalized=None,
                reason="unknown_node",
            )
        return validate_answer(node, user_text)

    # --- record + routing ---
    def record(self, node_id: str, normalized: Any):
        self.answers[node_id] = normalized
        node = self.get_node(node_id)

        nxt = node.get("next_id")

        if node.get("type") in {"single_choice"} and node.get("options"):
            for opt in node["options"]:
                if opt.get("id") == normalized or opt.get("value") == normalized:
                    nxt = opt.get("next_id") or nxt
                    break

        if node.get("type") == "multi_choice":
            nxt = self._apply_multi_choice_logic(node, normalized, nxt)

        self.current_id = nxt

    # escalate logic
    def should_escalate(self, user_text: str, llm_conf: float, is_valid: bool) -> bool:
        txt = (user_text or "").lower()

        if any(k in txt for k in ["change", "previous", "go back", "update"]):
            return True

        if llm_conf < 0.5:
            self.nudge_count += 1
        elif not is_valid:
            self.nudge_count += 1
        else:
            self.nudge_count = 0

        return self.nudge_count >= 2

    # --- source helpers (used by survey submission engine) ---

    def get_node_source(self, node_id: str) -> Optional[str]:
        """Return the ``source`` field of a node, or None if not found."""
        node = self._get(node_id)
        if node is None:
            return None
        return node.get("source")

    def get_current_source(self) -> Optional[str]:
        """Return the ``source`` of the current node, or None."""
        if self.current_id is None:
            return None
        return self.get_node_source(self.current_id)

    # simple utils
    def snapshot(self) -> Dict[str, Any]:
        return {
            "current_id": self.current_id,
            "answers": dict(self.answers),
            "nudge_count": self.nudge_count,
        }

    def _apply_multi_choice_logic(
        self,
        node: Dict[str, Any],
        selected: list[str],
        default_next: Optional[str],
    ) -> Optional[str]:
        """
        Apply multi_choice routing rules from node.logic.

        Keeps the same behaviour as the old _apply_multi_choice_logic helper:
        - when_contains_any → jump to specific next_id if any match
        - otherwise_next_id → used as a fallback if no other rule matches
        """
        logic = node.get("logic") or []
        if not logic:
            return default_next

        for cond in logic:
            if "when_contains_any" in cond:
                needed = set(cond["when_contains_any"] or [])
                if any(v in selected for v in needed):
                    return cond.get("next_id")

            if "otherwise_next_id" in cond:
                # keep as fallback; don't return immediately so earlier
                # when_contains_any rules still take precedence
                default_next = cond["otherwise_next_id"]

        return default_next

    @staticmethod
    def from_file(
        path: str,
        initial_node_id: str,
        api_node_handler: Optional[
            Callable[[str, Dict[str, Any], Dict[str, Any]], Optional[str]]
        ] = None,
    ):
        import json

        with open(path, "r", encoding="utf-8") as f:
            survey = json.load(f)
        return SurveyEngine(survey, initial_node_id, api_node_handler)

    @staticmethod
    def _to_nodes_map(maybe_list_or_dict: Any) -> Dict[str, Dict[str, Any]]:
        if isinstance(maybe_list_or_dict, dict) and "nodes" in maybe_list_or_dict:
            nodes = maybe_list_or_dict["nodes"]
            if isinstance(nodes, dict):
                return nodes
            if isinstance(nodes, list):
                return {n["id"]: n for n in nodes}

        if isinstance(maybe_list_or_dict, list):
            return {n["id"]: n for n in maybe_list_or_dict}

        raise ValueError("Unsupported survey structure")
