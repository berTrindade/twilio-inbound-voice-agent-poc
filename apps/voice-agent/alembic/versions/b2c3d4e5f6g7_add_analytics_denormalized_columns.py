"""Add denormalized analytics columns for encrypted JSONB queries.

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-14

"""

import json
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6g7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Non-PII fields to extract per integration type (strict allowlist)
_OUTCOME_EXTRACTORS = {
    "local_submission": lambda d: {
        "success": (d.get("response") or {}).get("success"),
    },
}


def upgrade() -> None:
    """Add analytics columns and backfill from existing data."""

    # --- Part A: Schema changes ---

    op.add_column(
        "survey_responses",
        sa.Column("escalations_count", sa.Integer(), nullable=True, server_default="0"),
    )
    op.add_column(
        "survey_responses",
        sa.Column("has_handover", sa.Boolean(), nullable=True, server_default="false"),
    )
    op.add_column(
        "survey_responses",
        sa.Column("last_question_id", sa.String(), nullable=True),
    )
    op.add_column(
        "survey_responses",
        sa.Column("last_question_text", sa.String(), nullable=True),
    )
    op.add_column(
        "survey_responses",
        sa.Column(
            "integration_outcomes",
            sa.dialects.postgresql.JSONB(),
            nullable=True,
            server_default="{}",
        ),
    )

    # --- Part B: Backfill from existing data ---

    from voice_agent.utils.encryption import decrypt_json

    conn = op.get_bind()
    row_count = conn.execute(sa.text("SELECT COUNT(*) FROM survey_responses")).scalar()

    if row_count == 0:
        logger.info("No rows to backfill — empty table.")
        return

    logger.info("Backfilling analytics columns for %d rows...", row_count)

    BATCH_SIZE = 500
    offset = 0
    backfilled = 0

    while True:
        rows = conn.execute(
            sa.text(
                "SELECT id, responses, session_metadata, integrations "
                "FROM survey_responses "
                "ORDER BY id "
                "LIMIT :limit OFFSET :offset"
            ),
            {"limit": BATCH_SIZE, "offset": offset},
        ).fetchall()

        if not rows:
            break

        for row in rows:
            row_id = row[0]
            responses_raw = row[1]
            session_meta_raw = row[2]
            integrations_raw = row[3]

            # Decrypt JSONB columns
            responses_data = decrypt_json(responses_raw)
            session_meta = decrypt_json(session_meta_raw)
            integrations_data = decrypt_json(integrations_raw)

            questions = responses_data.get("questions", [])

            # Extract analytics values
            has_handover = any(
                q.get("node_type") == "handover_to_coach" for q in questions
            )
            last_q = questions[-1] if questions else None
            esc_count = session_meta.get("escalations_count", 0)
            if esc_count is None or esc_count == "null":
                esc_count = 0

            # Extract integration outcomes (non-PII only)
            outcomes = {}
            for key, val in integrations_data.items():
                extractor = _OUTCOME_EXTRACTORS.get(key)
                if extractor and isinstance(val, dict):
                    outcomes[key] = extractor(val)

            conn.execute(
                sa.text(
                    "UPDATE survey_responses SET "
                    "escalations_count = :esc, "
                    "has_handover = :handover, "
                    "last_question_id = :lqid, "
                    "last_question_text = :lqtext, "
                    "integration_outcomes = :outcomes "
                    "WHERE id = :row_id"
                ),
                {
                    "row_id": row_id,
                    "esc": int(esc_count) if esc_count else 0,
                    "handover": has_handover,
                    "lqid": last_q.get("question_id") if last_q else None,
                    "lqtext": last_q.get("question_text") if last_q else None,
                    "outcomes": json.dumps(outcomes),
                },
            )
            backfilled += 1

        offset += BATCH_SIZE

    logger.info("Backfilled %d rows out of %d total.", backfilled, row_count)


def downgrade() -> None:
    """Drop analytics columns."""
    op.drop_column("survey_responses", "integration_outcomes")
    op.drop_column("survey_responses", "last_question_text")
    op.drop_column("survey_responses", "last_question_id")
    op.drop_column("survey_responses", "has_handover")
    op.drop_column("survey_responses", "escalations_count")
