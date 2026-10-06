"""create survey_responses table

Revision ID: 001_create_survey_responses
Revises: fa292681e507
Create Date: 2025-11-03 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_create_survey_responses"
down_revision: Union[str, Sequence[str], None] = "fa292681e507"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create survey_responses table
    op.create_table(
        "survey_responses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("survey_id", sa.UUID(), nullable=False),
        sa.Column("participant_phone", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("responses", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "session_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["survey_id"],
            ["surveys.id"],
            name="fk_survey_responses_survey_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for efficient querying
    op.create_index(
        "idx_survey_responses_survey_id_created",
        "survey_responses",
        ["survey_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_survey_responses_participant_created",
        "survey_responses",
        ["participant_phone", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_survey_responses_status_created",
        "survey_responses",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_survey_responses_survey_participant",
        "survey_responses",
        ["survey_id", "participant_phone", "created_at"],
        unique=False,
    )

    # Create individual indexes for foreign key and lookup fields
    op.create_index(
        op.f("ix_survey_responses_survey_id"),
        "survey_responses",
        ["survey_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_survey_responses_participant_phone"),
        "survey_responses",
        ["participant_phone"],
        unique=False,
    )
    op.create_index(
        op.f("ix_survey_responses_status"),
        "survey_responses",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index(op.f("ix_survey_responses_status"), table_name="survey_responses")
    op.drop_index(
        op.f("ix_survey_responses_participant_phone"), table_name="survey_responses"
    )
    op.drop_index(op.f("ix_survey_responses_survey_id"), table_name="survey_responses")
    op.drop_index(
        "idx_survey_responses_survey_participant", table_name="survey_responses"
    )
    op.drop_index("idx_survey_responses_status_created", table_name="survey_responses")
    op.drop_index(
        "idx_survey_responses_participant_created", table_name="survey_responses"
    )
    op.drop_index(
        "idx_survey_responses_survey_id_created", table_name="survey_responses"
    )

    # Drop table
    op.drop_table("survey_responses")
