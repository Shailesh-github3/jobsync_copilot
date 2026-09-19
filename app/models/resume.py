from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    pipeline_id: Mapped[Optional[str]] = mapped_column(String(50))  # e.g., PIPE-2026-001
    
    tailored_summary: Mapped[Optional[str]] = mapped_column(Text)
    tailored_bullets: Mapped[Optional[str]] = mapped_column(Text)  # Stored as JSON string
    relevant_skills: Mapped[Optional[str]] = mapped_column(Text)   # Stored as JSON string
    
    validation_status: Mapped[str] = mapped_column(
        String(20), default="PENDING"
    )  # PENDING, PASSED, FAILED
    
    # Add this field to the Resume class in app/models/resume.py
    approval_status: Mapped[str] = mapped_column(
        String(20), default="PENDING"
    )  # PENDING, APPROVED, REJECTED
    
    processing_status: Mapped[Optional[str]] = mapped_column(
    String(20), default="IDLE"
)  # IDLE, RUNNING, PASSED, FAILED
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    candidate = relationship("CandidateProfile", backref="resumes")
    job = relationship("Job", backref="resumes")

    def __repr__(self) -> str:
        return f"<Resume id={self.id} candidate_id={self.candidate_id} status={self.validation_status}>"