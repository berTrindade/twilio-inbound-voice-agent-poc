"""Add indexed call_sid column to survey_responses.

The CallSid lives inside the encrypted session_metadata JSONB, so it cannot be
queried directly. The Twilio recording-status callback only knows the CallSid,
so we mirror it into a plaintext indexed column (it is a non-PII identifier,
like the other denormalized analytics columns) to look up the row.

Forward-only: recordings are a new feature, so no backfill of historical rows
is required.

Revision ID: d4e5f6a7b8c9
Revises: b2c3d4e5f6g7
Create Date: 2026-06-13

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6g7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "survey_responses",
        sa.Column("call_sid", sa.String(), nullable=True),
    )
    # CONCURRENTLY so an existing table keeps taking writes while this builds.
    # It cannot run inside a transaction, hence the autocommit block; that is
    # safe here because this migration has no backfill to be atomic with.
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_survey_responses_call_sid",
            "survey_responses",
            ["call_sid"],
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    op.drop_index("ix_survey_responses_call_sid", table_name="survey_responses")
    op.drop_column("survey_responses", "call_sid")
