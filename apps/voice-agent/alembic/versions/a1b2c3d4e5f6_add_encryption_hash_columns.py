"""Add encryption hash columns and encrypt existing PII data.

Revision ID: a1b2c3d4e5f6
Revises: e3f1a2b4c5d6
Create Date: 2026-04-14

"""

import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "e3f1a2b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add hash columns, create indexes, and encrypt existing data."""

    # --- Part A: Schema changes (always run) ---

    op.add_column(
        "survey_responses",
        sa.Column("participant_phone_hash", sa.String(), nullable=True),
    )
    # Equality lookups on participant_phone_hash alone ride the leading column
    # of this composite, so there is no separate single-column index.
    #
    # Built inline rather than CONCURRENTLY: this migration also backfills row
    # by row in the same transaction, which holds locks far longer than the
    # index build does. Making only the index concurrent would give up the
    # migration's atomicity to save a fraction of its total lock time. The
    # backfill is what to fix first if this ever has to run on a live table.
    op.create_index(
        "idx_sr_phone_hash_created",
        "survey_responses",
        ["participant_phone_hash", "created_at"],
    )

    # --- Part B: Data encryption (only if ENCRYPTION_KEY is set) ---

    from voice_agent.utils.encryption import (
        encrypt,
        encrypt_json,
        hmac_hash,
        is_encryption_enabled,
    )

    if not is_encryption_enabled():
        logger.warning(
            "ENCRYPTION_KEY not set — skipping data encryption. "
            "Existing rows remain in plain text."
        )
        return

    conn = op.get_bind()

    # Count rows to process
    row_count = conn.execute(sa.text("SELECT COUNT(*) FROM survey_responses")).scalar()

    if row_count == 0:
        logger.info("No rows to encrypt — empty table.")
        return

    logger.info("Encrypting %d existing survey_responses rows...", row_count)

    BATCH_SIZE = 500
    offset = 0
    encrypted_count = 0

    while True:
        rows = conn.execute(
            sa.text(
                "SELECT id, participant_phone, responses, "
                "session_metadata, integrations "
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
            phone = row[1]
            responses = row[2]
            session_metadata = row[3]
            integrations = row[4]

            # Skip already-encrypted rows (idempotent)
            if phone and isinstance(phone, str) and phone.startswith("enc:v1:"):
                continue

            updates = {}
            params = {"row_id": row_id}

            # Encrypt participant_phone
            if phone:
                updates["participant_phone"] = ":enc_phone"
                updates["participant_phone_hash"] = ":phone_hash"
                params["enc_phone"] = encrypt(phone)
                params["phone_hash"] = hmac_hash(phone)

            # Encrypt JSONB columns (only if they're dicts, not already strings)
            if isinstance(responses, dict):
                updates["responses"] = ":enc_responses"
                params["enc_responses"] = encrypt_json(responses)

            if isinstance(session_metadata, dict):
                updates["session_metadata"] = ":enc_session_metadata"
                params["enc_session_metadata"] = encrypt_json(session_metadata)

            if isinstance(integrations, dict):
                updates["integrations"] = ":enc_integrations"
                params["enc_integrations"] = encrypt_json(integrations)

            if updates:
                set_clause = ", ".join(
                    f"{col} = {param}" for col, param in updates.items()
                )
                # For JSONB columns stored as encrypted strings, we need to
                # cast the string to jsonb so PostgreSQL accepts it.
                # A JSON string scalar like '"enc:v1:..."' is valid JSONB.
                set_clause = set_clause.replace(
                    "responses = :enc_responses",
                    "responses = to_jsonb(CAST(:enc_responses AS text))",
                )
                set_clause = set_clause.replace(
                    "session_metadata = :enc_session_metadata",
                    "session_metadata = to_jsonb(CAST(:enc_session_metadata AS text))",
                )
                set_clause = set_clause.replace(
                    "integrations = :enc_integrations",
                    "integrations = to_jsonb(CAST(:enc_integrations AS text))",
                )

                conn.execute(
                    sa.text(
                        f"UPDATE survey_responses SET {set_clause} WHERE id = :row_id"
                    ),
                    params,
                )
                encrypted_count += 1

        offset += BATCH_SIZE

    logger.info("Encrypted %d rows out of %d total.", encrypted_count, row_count)


def downgrade() -> None:
    """Drop the hash column and index.

    WARNING: This does NOT decrypt data. Encrypted values will remain
    encrypted in the original columns.
    """
    op.drop_index("idx_sr_phone_hash_created", table_name="survey_responses")
    op.drop_column("survey_responses", "participant_phone_hash")
