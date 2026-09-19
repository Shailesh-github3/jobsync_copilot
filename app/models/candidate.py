from typing import List, Optional

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    education: Mapped[Optional[str]] = mapped_column(Text)
    links: Mapped[Optional[str]] = mapped_column(Text)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(255))

    # One candidate has many skills. Deleting a candidate deletes their skills.
    skills: Mapped[List["CandidateSkill"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    
    projects: Mapped[List["CandidateProject"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<CandidateProfile id={self.id} name={self.name!r}>"


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_profiles.id"),
        index=True,
    )
    skill_name: Mapped[str] = mapped_column(String(100), index=True)
    proficiency: Mapped[str] = mapped_column(
        String(50), default="intermediate"
    )
    years_experience: Mapped[Optional[float]] = mapped_column(Float)
    # Allowed values: VERIFIED, UNVERIFIED, DO_NOT_CLAIM
    status: Mapped[str] = mapped_column(String(20), default="UNVERIFIED")

    # Many skills belong to one candidate.
    candidate: Mapped["CandidateProfile"] = relationship(
        back_populates="skills",
    )

    def __repr__(self) -> str:
        return (
            f"<CandidateSkill id={self.id} "
            f"name={self.skill_name!r} status={self.status}>"
        )
        
class CandidateProject(Base):
    __tablename__ = "candidate_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text) # This is the actual evidence text
    technologies: Mapped[Optional[str]] = mapped_column(String(500)) # Comma-separated

    candidate: Mapped["CandidateProfile"] = relationship(back_populates="projects")
    
    def __repr__(self) -> str:
        return f"<CandidateProject id={self.id} title={self.title!r}>"