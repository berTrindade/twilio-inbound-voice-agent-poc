from typing import Any, Dict, Optional
from .survey_engine import SurveyEngine
import time
import logging

logger = logging.getLogger(__name__)


class SurveyBackendAdapter:
    """
    Thin boundary the bridge + (escalation) tools use.
    Keeps your deterministic engine under the hood.
    """

    def __init__(self, engine: SurveyEngine):
        self.engine = engine
        # Per-question buffer for fragmented answers
        self._buffer_node_id: Optional[str] = None
        self._buffer_text: str = ""
        self._buffer_last_update: Optional[float] = None

    # ---- public API used by websocket / tests -----------------------------

    def advance(self) -> Dict[str, Any]:
        spoken, node_id, spoken_interruptible, spoken_preemptible = (
            self.engine.advance_to_interactive()
        )

        # consume one-shot handover event payload (context presence is the truth)
        handover_ctx = self.engine.consume_pending_handover()

        # reset buffer for the new active node
        self._reset_answer_buffer(node_id)

        finished = self._is_finished()
        question_prompt = (
            self._get_prompt_for(node_id) if node_id and not finished else ""
        )

        node = self.engine.get_node(node_id) if node_id else {}
        interruptible = node.get("interruptible")
        preemptible = node.get("preemptible")

        return {
            "spoken_intro": spoken,
            "spoken_intro_interruptible": spoken_interruptible,
            "spoken_intro_preemptible": spoken_preemptible,
            "node_id": node_id,
            "question_prompt": question_prompt,
            "finished": finished,
            "handover_to_coach": handover_ctx is not None,
            "handover_context": handover_ctx,
            "state": self.engine.snapshot(),
            "interruptible": interruptible,
            "preemptible": preemptible,
        }

    def validate(self, node_id: str, user_text: str) -> Dict[str, Any]:
        # New engine API uses `validate`, not `validate_answer`
        return self.engine.validate(node_id, user_text)

    def record(self, node_id: str, normalized_value: Any):
        # New engine API uses `record`, not `record_and_route`
        self.engine.record(node_id, normalized_value)

    def current(self) -> Dict[str, Any]:
        nid = self.engine.current_id
        node = self.engine.get_node(nid) if nid else {}
        return {
            "node_id": nid,
            "question_prompt": self._get_prompt_for(nid) if nid else "",
            "finished": self._is_finished(),
            "interruptible": node.get("interruptible"),
            "preemptible": node.get("preemptible"),
        }

    def should_escalate(self, user_text: str, llm_conf: float, is_valid: bool) -> bool:
        return self.engine.should_escalate(user_text, llm_conf, is_valid)

    def snapshot(self) -> Dict[str, Any]:
        return self.engine.snapshot()

    # ---- internal helpers -------------------------------------------------

    def _render_options_letters(self, options: list[dict[str, Any]]) -> str:
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        parts = []

        for i, o in enumerate(options):
            label = (o.get("label", "") or "").strip()
            suffix = "." if i < len(options) - 1 else ""
            parts.append(f"{letters[i]}: {label}{suffix}")

        return " ".join(parts)

    def _get_prompt_for(self, node_id: str) -> str:
        """
        Build the TTS prompt for a given node_id.

        This is a direct port of the original SurveyEngine.get_prompt_for logic,
        but lifted into the adapter so we keep the new engine focused on
        traversal/answers while preserving existing behaviour.
        """
        if not node_id:
            return ""

        node = self.engine.get_node(node_id)
        t = node.get("type")
        preface = node.get("tts_preface")
        base = node.get("text") or ""
        speak_options = node.get("speak_options", True)

        if t == "single_choice":
            opts = node.get("options") or []
            # Only render options if speak_options is True
            rendered = (
                self._render_options_letters(opts) if (opts and speak_options) else ""
            )
            prompt = f"{base} {rendered}.".strip() if rendered else base

        elif t == "multi_choice":
            opts = node.get("options") or []
            # Only render options if speak_options is True
            rendered = (
                self._render_options_letters(opts) if (opts and speak_options) else ""
            )
            prompt = f"{base} {rendered}.".strip() if rendered else base

        elif t == "yes_no":
            prompt = base or "Please answer yes or no."

        elif t == "numeric":
            prompt = base or "Please give a number."

        elif t == "free_text":
            prompt = base or "Please share briefly."

        else:
            prompt = base

        if preface:
            return f"{preface} {prompt}".strip()
        return prompt

    def _is_finished(self) -> bool:
        """
        Mirror the original SurveyEngine.is_finished behaviour using the
        new engine's public state (current_id) and internal node map.
        """
        cid = self.engine.current_id
        if cid in (None, "", "end"):
            return True

        # engine._get exists in the current implementation; if it ever disappears,
        # we conservatively treat an unknown id as finished.
        get_fn = getattr(self.engine, "_get", None)
        if callable(get_fn):
            return get_fn(cid) is None
        return False

    def _reset_answer_buffer(self, node_id: Optional[str] = None) -> None:
        """Reset the per-question answer buffer.

        - If node_id is None → clear buffer completely.
           - If node_id is a question id → start a fresh buffer for that node.
        """
        self._buffer_node_id = node_id
        self._buffer_text = ""
        self._buffer_last_update = None

    def merge_user_utterance(self, node_id: str, new_text: str) -> str:
        """
        Merge a new utterance fragment for the given node_id into a
        per-question buffer and return the combined text.

        - If this is the first fragment for the node, we just store it.
        - If it's the same node as before, we append with a space.
        - If the node has changed, we reset the buffer and start fresh.

        This keeps handling fully streaming and non-blocking — we still
        react on every `last=true` — but the small model always sees the
        accumulated text so far for that question.
        """
        new_text = (new_text or "").strip()
        if not new_text:
            # Nothing new; just return whatever we already have.
            return self._buffer_text

        now = time.monotonic()
        MERGE_WINDOW_SEC = 3.0  # tweak to taste (2–4 seconds is typical)

        same_node = self._buffer_node_id == node_id
        recent_enough = (
            self._buffer_last_update is not None
            and (now - self._buffer_last_update) <= MERGE_WINDOW_SEC
        )

        # New question OR stale buffer → start fresh
        if not same_node or not recent_enough:
            self._buffer_node_id = node_id
            self._buffer_text = new_text
            self._buffer_last_update = now
            return self._buffer_text

        # Same node and recent → append
        if not self._buffer_text:
            self._buffer_text = new_text
        else:
            combined = f"{self._buffer_text} {new_text}".strip()
            # Optional safety limit to avoid pathological growth
            MAX_LEN = 512
            if len(combined) > MAX_LEN:
                combined = combined[-MAX_LEN:]
            self._buffer_text = combined

        self._buffer_last_update = now
        return self._buffer_text
