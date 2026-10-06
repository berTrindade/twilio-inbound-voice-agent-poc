"""Survey repository for database operations."""

from typing import Optional
from sqlalchemy.orm import Session

from ..models import Survey


class SurveyRepository:
    """Repository for Survey database operations."""

    def __init__(self, db: Session):
        """
        Initialize repository with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def get_latest_by_type(self, survey_type: str) -> Optional[Survey]:
        """
        Get the latest survey by type.

        Args:
            survey_type: The type of survey to retrieve

        Returns:
            The latest survey of the given type, or None if not found
        """
        return (
            self.db.query(Survey)
            .filter(Survey.type == survey_type)
            .order_by(Survey.created_at.desc())
            .first()
        )

    def create(
        self,
        title: str,
        survey_type: str,
        data: dict,
    ) -> Survey:
        """
        Create a new survey.

        Args:
            title: Survey title
            survey_type: Survey type
            data: Survey data as dictionary

        Returns:
            The created survey
        """
        survey = Survey(
            title=title,
            type=survey_type,
            data=data,
        )
        self.db.add(survey)
        self.db.commit()
        self.db.refresh(survey)
        return survey

    def get_by_id(self, survey_id) -> Optional[Survey]:
        """
        Get a survey by ID.

        Args:
            survey_id: Survey ID (UUID)

        Returns:
            The survey if found, None otherwise
        """
        return self.db.query(Survey).filter(Survey.id == survey_id).first()
