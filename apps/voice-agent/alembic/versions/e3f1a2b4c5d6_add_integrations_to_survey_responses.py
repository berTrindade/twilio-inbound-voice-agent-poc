"""add_integrations_to_survey_responses

Revision ID: e3f1a2b4c5d6
Revises: 001_create_survey_responses
Create Date: 2026-02-25 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e3f1a2b4c5d6"
down_revision: Union[str, Sequence[str], None] = "001_create_survey_responses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add integrations JSONB column to survey_responses."""
    op.add_column(
        "survey_responses",
        sa.Column("integrations", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    """Remove integrations column from survey_responses."""
    op.drop_column("survey_responses", "integrations")
