"""Write a set of example calls so the dashboard has something to show.

A fresh install has an empty database, so every panel reads zero and the
analytics charts have no shape at all. That is an accurate view of nothing, and
a useless first impression of what the dashboard is for.

These rows are written through the same encryption helpers and the same JSONB
shapes the live call path produces, so what the dashboard renders here is what
it renders for a real call. They are marked `demo: true` in session_metadata,
which is what the banner in the dashboard keys off and what makes this script
idempotent.

Runs inside the call runner container, which is the only thing with a route to
Postgres. `make seed` and `make unseed` are the front door:

    make seed
    make unseed
"""

import argparse
import json
import logging
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import settings
from ..database import SessionLocal
from ..models import SurveyResponse, SurveyResponseStatus
from ..repositories import SurveyRepository
from ..utils.encryption import encrypt, encrypt_json

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# +1 555 01xx is reserved for fiction, so these can never collide with a real
# number and are recognisable as invented at a glance.
_PHONES = [f"+1555010{n:04d}" for n in range(1, 180)]

# Enough calls, over a long enough window, for the drop-off and
# completion-rate charts to show a trend rather than noise. Still well
# under a megabyte on disk at roughly 1.5 kB a row.
TOTAL_CALLS = 400
WINDOW_DAYS = 45

# Deterministic, so re-running gives the same dashboard and screenshots of it
# stay honest.
_rng = random.Random(20260913)


def _load_survey_nodes() -> list[dict]:
    """The nodes the agent actually asks, so the demo answers match the demo."""
    path = Path(settings.survey_json_path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# Plausible answers per node type. free_text gets the widest spread of
# confidence, which is the point: it is the type the interpreter finds hardest.
_FREE_TEXT_ANSWERS = {
    "Q_NAME_V1": ["Bernardo", "Priya", "Tomás", "Ada", "Ines", "Marcus"],
    "Q_COMMENTS_V1": [
        "No, that was fine",
        "It was quicker than I expected",
        "The voice is a bit fast but it understood me",
        "No",
        "Maybe give a bit longer to answer",
    ],
}


def _answer_for(node: dict) -> tuple[str, float]:
    """(answer, llm_confidence) for one node."""
    node_type = node.get("type")
    if node_type == "single_choice":
        options = node.get("options") or []
        value = _rng.choice(options)
        if isinstance(value, dict):
            value = value.get("value") or value.get("label") or "yes"
        return str(value), round(_rng.uniform(0.86, 0.99), 4)

    pool = _FREE_TEXT_ANSWERS.get(node.get("id"), ["Yes", "No", "Not sure"])
    return _rng.choice(pool), round(_rng.uniform(0.54, 0.88), 4)


def _build_turns(question_text: str, answer: str, confidence: float) -> list[dict]:
    """One clean turn, or a retry first. Retries are what make the attempts and
    confidence numbers on the dashboard mean anything."""
    turns = []
    if _rng.random() < 0.22:
        turns.append(
            {
                "turn_number": 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "assistant_message": question_text,
                "user_message": _rng.choice(
                    ["Sorry, what?", "Hmm", "Can you say that again"]
                ),
                "llm_interpretation": "other",
                "llm_confidence": round(_rng.uniform(0.31, 0.58), 4),
                "validation_result": None,
                "escalated": False,
            }
        )

    turns.append(
        {
            "turn_number": len(turns) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "assistant_message": question_text,
            "user_message": answer,
            "llm_interpretation": "answer",
            "llm_confidence": confidence,
            "validation_result": {"valid": True},
            "escalated": False,
        }
    )
    return turns


def _build_question(node: dict, started: datetime) -> dict:
    answer, confidence = _answer_for(node)
    question_text = node.get("text", "")
    turns = _build_turns(question_text, answer, confidence)
    duration_ms = _rng.randint(4200, 17000)
    completed = started + timedelta(milliseconds=duration_ms)

    # Matches what add_question_response stores: the metadata dict is merged
    # into the question, so turns sit at the top level rather than nested.
    return {
        "question_id": node["id"],
        "question_text": question_text,
        "answer": answer,
        "answered_at": completed.isoformat(),
        "node_type": node.get("type"),
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "duration_ms": duration_ms,
        "turns": turns,
        "attempts": len(turns),
    }


def _build_call(nodes: list[dict], started_at: datetime, outcome: str) -> dict:
    """One row's worth of fields. `outcome` is completed | abandoned | in_progress."""
    askable = [n for n in nodes if n.get("type") in ("single_choice", "free_text")]

    if outcome == "completed":
        asked = askable
    elif outcome == "abandoned":
        # Stop partway, which is what gives the drop-off chart its shape.
        asked = askable[: _rng.randint(1, max(1, len(askable) - 1))]
    else:
        asked = askable[: _rng.randint(1, 2)]

    questions = []
    cursor = started_at
    for node in asked:
        question = _build_question(node, cursor)
        questions.append(question)
        cursor = datetime.fromisoformat(question["completed_at"]) + timedelta(
            seconds=_rng.uniform(0.6, 2.4)
        )

    escalations = 1 if outcome != "completed" and _rng.random() < 0.35 else 0

    row = {
        "responses": {"questions": questions},
        "started_at": started_at,
        "completed_at": cursor if outcome == "completed" else None,
        "status": {
            "completed": SurveyResponseStatus.COMPLETED.value,
            "abandoned": SurveyResponseStatus.ABANDONED.value,
            "in_progress": SurveyResponseStatus.IN_PROGRESS.value,
        }[outcome],
        "escalations_count": escalations,
        "last_question_id": questions[-1]["question_id"] if questions else None,
        "last_question_text": questions[-1]["question_text"] if questions else None,
    }

    # Only a finished call submits anything downstream. One in eight fails, so
    # integration health is a real number rather than a permanent 100%.
    if outcome == "completed":
        success = _rng.random() > 0.125
        row["integration_outcomes"] = {
            "local_submission": {
                "success": success,
                "attempted_at": cursor.isoformat(),
                "detail": None if success else "downstream returned 503",
            }
        }
    else:
        row["integration_outcomes"] = {}

    return row


def _outcome_sequence(total: int) -> list[str]:
    """Weighted so the completion rate lands somewhere believable rather than
    at 100%, which would say nothing."""
    outcomes = (
        ["completed"] * int(total * 0.68)
        + ["abandoned"] * int(total * 0.24)
        + ["in_progress"] * 2
    )
    outcomes += ["completed"] * (total - len(outcomes))
    _rng.shuffle(outcomes)
    return outcomes


def seed_demo_calls() -> int:
    db = SessionLocal()
    try:
        survey_type = Path(settings.survey_json_path).stem
        survey = SurveyRepository(db).get_latest_by_type(survey_type)
        if survey is None:
            logger.error(
                "No survey named %r in the database yet. The call runner creates "
                "it on startup, so bring the stack up first.",
                survey_type,
            )
            return 1

        existing = (
            db.query(SurveyResponse)
            .filter(SurveyResponse.call_sid.like("CAdemo%"))
            .count()
        )
        if existing:
            logger.info("%d example calls are already here, nothing to do.", existing)
            return 0

        nodes = _load_survey_nodes()
        now = datetime.now(timezone.utc)
        outcomes = _outcome_sequence(TOTAL_CALLS)

        for index, outcome in enumerate(outcomes):
            # Spread across the window and across the working day, so the
            # volume chart has more than one bar and none of them is midnight.
            day_offset = _rng.uniform(0, WINDOW_DAYS)
            started_at = now - timedelta(days=day_offset, hours=_rng.uniform(-4, 4))
            if started_at > now:
                started_at = now - timedelta(minutes=_rng.randint(3, 90))

            call = _build_call(nodes, started_at, outcome)
            phone = _PHONES[index % len(_PHONES)]

            db.add(
                SurveyResponse(
                    id=uuid.uuid4(),
                    survey_id=survey.id,
                    participant_phone=encrypt(phone),
                    status=call["status"],
                    responses=encrypt_json(call["responses"]),
                    session_metadata=encrypt_json(
                        {"demo": True, "channel": "example data"}
                    ),
                    # Shaped like a Twilio CallSid (34 chars) but prefixed so it
                    # can never collide with one, and so --clear can find them.
                    call_sid=f"CAdemo{index:028d}",
                    escalations_count=call["escalations_count"],
                    last_question_id=call["last_question_id"],
                    last_question_text=call["last_question_text"],
                    integration_outcomes=call["integration_outcomes"],
                    started_at=call["started_at"],
                    completed_at=call["completed_at"],
                    created_at=call["started_at"],
                )
            )

        db.commit()
        logger.info(
            "Wrote %d example calls across the last %d days.", TOTAL_CALLS, WINDOW_DAYS
        )
        return 0
    except Exception:
        db.rollback()
        logger.exception("Could not write the example calls")
        return 1
    finally:
        db.close()


def clear_demo_calls() -> int:
    db = SessionLocal()
    try:
        removed = (
            db.query(SurveyResponse)
            .filter(SurveyResponse.call_sid.like("CAdemo%"))
            .delete(synchronize_session=False)
        )
        db.commit()
        logger.info("Removed %d example calls.", removed)
        return 0
    except Exception:
        db.rollback()
        logger.exception("Could not remove the example calls")
        return 1
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clear", action="store_true", help="remove the example calls instead"
    )
    args = parser.parse_args()
    return clear_demo_calls() if args.clear else seed_demo_calls()


if __name__ == "__main__":
    sys.exit(main())
