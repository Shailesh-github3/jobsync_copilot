from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500))
    raw_description: Mapped[str] = mapped_column(Text)
    title: Mapped[Optional[str]] = mapped_column(String(200))
    company: Mapped[Optional[str]] = mapped_column(String(200))
    parse_status: Mapped[str] = mapped_column(
        String(20), default="PENDING"
    )  # PENDING, PARSED, FAILED
    
    # Parsed fields (populated by JD parser)
    parsed_role: Mapped[Optional[str]] = mapped_column(String(200))
    parsed_required_skills: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    parsed_preferred_skills: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    parsed_min_experience: Mapped[Optional[int]] = mapped_column(Integer)
    # Match results (populated by matching engine)
    match_score: Mapped[Optional[float]] = mapped_column(Float)
    match_explanation: Mapped[Optional[str]] = mapped_column(Text)
    match_status: Mapped[Optional[str]] = mapped_column(String(20))  # MATCHED, NOT_MATCHED
    match_details: Mapped[Optional[str]] = mapped_column(Text)  # JSON serialized MatchResult

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id} title={self.title!r} status={self.parse_status}>"