"""Index started_at, and drop the indexes over the encrypted phone column.

Every dashboard query filters and sorts on started_at, but all five composite
indexes were built against created_at. The two columns are set microseconds
apart and never diverge, so they look interchangeable, but to the planner they
are unrelated and none of those indexes can serve a started_at range. Measured
on 200k rows: the volume-by-day query read 3704 buffers as a parallel
sequential scan and 31 as an index-only scan; the default list sort went from
3778 buffers and a top-N heapsort to 4.

One index on started_at covers the whole dashboard. A (status, started_at)
composite was measured too and the planner never chose it, so it is not here.

The three dropped indexes cover participant_phone, which is AES-256-GCM
ciphertext with a random nonce per row. The same phone encrypts to different
bytes every time, so no equality lookup against that column can ever match and
no index on it can ever be used. participant_phone_hash is the blind index
that makes those lookups possible, and its index stays.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-14

"""

from typing import Sequence, Union

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# CONCURRENTLY throughout, so an existing table keeps taking writes. It cannot
# run inside a transaction, hence the autocommit block; safe here because this
# migration only touches indexes and has no data to be atomic with.


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "idx_sr_started_at",
            "survey_responses",
            ["started_at"],
            postgresql_concurrently=True,
        )
        for name in (
            "idx_survey_responses_participant_created",
            "idx_survey_responses_survey_participant",
            "ix_survey_responses_participant_phone",
        ):
            op.drop_index(
                name,
                table_name="survey_responses",
                postgresql_concurrently=True,
                if_exists=True,
            )


def downgrade() -> None:
    op.create_index(
        "idx_survey_responses_participant_created",
        "survey_responses",
        ["participant_phone", "created_at"],
    )
    op.create_index(
        "idx_survey_responses_survey_participant",
        "survey_responses",
        ["survey_id", "participant_phone", "created_at"],
    )
    op.create_index(
        "ix_survey_responses_participant_phone",
        "survey_responses",
        ["participant_phone"],
    )
    op.drop_index("idx_sr_started_at", table_name="survey_responses")
