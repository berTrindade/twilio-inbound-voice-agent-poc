"""Survey model."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB

from ..database import Base


class Survey(Base):
    """Survey model representing a versioned survey."""

    __tablename__ = "surveys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    # Looked up by type, newest first, which idx_survey_type_created serves;
    # a single-column index on type would only duplicate its leading column.
    type = Column(String, nullable=False)
    data = Column(JSONB, nullable=False, default=dict)  # Survey content as JSONB
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Composite index for efficient querying latest survey by type
    __table_args__ = (Index("idx_survey_type_created", "type", "created_at"),)

    def __repr__(self):
        return f"<Survey(id={self.id}, title='{self.title}', type='{self.type}')>"
