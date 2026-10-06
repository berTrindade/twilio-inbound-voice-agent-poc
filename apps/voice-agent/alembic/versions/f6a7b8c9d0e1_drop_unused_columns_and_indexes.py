"""Drop the columns nothing reads and the indexes nothing scans.

Five columns were written on every call and read by nothing, in either the
voice agent or the dashboard:

  surveys.original_data          byte-identical to surveys.data in every row
  surveys.version                hardcoded to 1, echoed into one log line
  survey_responses.has_handover  written on handover, never queried
  survey_responses.updated_at    maintained by the ORM, selected by no query
  survey_responses.participant_phone_hash
                                 a blind index whose lookup was never written

Five indexes were never scanned. Measured over a full pass of the dashboard's
own queries at 200k rows, with the stats reset first: idx_sr_started_at took
three scans and the primary key one, and every index below took zero. The two
created_at composites alone were 28 MB. They trail on created_at, and not one
dashboard predicate references that column; they all use started_at or status.

What stays, and why: idx_sr_started_at carries every dashboard query,
ix_survey_responses_call_sid serves the recording-status callback (a voice
agent path, not a dashboard one, so its zero scans here are expected),
ix_survey_responses_survey_id keeps the foreign key indexed, and
idx_survey_type_created serves the survey lookup by type.

If repeat-caller lookups are ever wanted, add participant_phone_hash back
together with the query that reads it. An index with no query is not a
head start, it is 11 MB of write amplification.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEAD_INDEXES = (
    "idx_survey_responses_survey_id_created",
    "idx_survey_responses_status_created",
    "idx_sr_phone_hash_created",
    "ix_survey_responses_status",
)


def upgrade() -> None:
    # CONCURRENTLY so the table keeps taking writes; it cannot run inside a
    # transaction, hence the autocommit block. The column drops below are
    # catalog-only in Postgres and stay in the migration's own transaction.
    with op.get_context().autocommit_block():
        for name in _DEAD_INDEXES:
            op.drop_index(
                name,
                table_name="survey_responses",
                postgresql_concurrently=True,
                if_exists=True,
            )
        op.drop_index(
            "ix_surveys_type",
            table_name="surveys",
            postgresql_concurrently=True,
            if_exists=True,
        )

    op.drop_column("survey_responses", "participant_phone_hash")
    op.drop_column("survey_responses", "has_handover")
    op.drop_column("survey_responses", "updated_at")
    op.drop_column("surveys", "original_data")
    op.drop_column("surveys", "version")


def downgrade() -> None:
    # The dropped data is not recoverable; these come back empty. version and
    # updated_at are NOT NULL, so they need a server default to backfill
    # existing rows, which is then removed to match the original schema.
    op.add_column(
        "surveys",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("surveys", "version", server_default=None)
    op.add_column("surveys", sa.Column("original_data", JSONB(), nullable=True))
    op.add_column(
        "survey_responses",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.alter_column("survey_responses", "updated_at", server_default=None)
    op.add_column(
        "survey_responses", sa.Column("has_handover", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "survey_responses",
        sa.Column("participant_phone_hash", sa.String(), nullable=True),
    )

    op.create_index("ix_surveys_type", "surveys", ["type"])
    op.create_index("ix_survey_responses_status", "survey_responses", ["status"])
    op.create_index(
        "idx_sr_phone_hash_created",
        "survey_responses",
        ["participant_phone_hash", "created_at"],
    )
    op.create_index(
        "idx_survey_responses_status_created",
        "survey_responses",
        ["status", "created_at"],
    )
    op.create_index(
        "idx_survey_responses_survey_id_created",
        "survey_responses",
        ["survey_id", "created_at"],
    )
