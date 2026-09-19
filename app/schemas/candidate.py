from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ---------- SKILL SCHEMAS ----------

class CandidateSkillCreate(BaseModel):
    """Schema for creating a skill (used in POST requests)."""
    skill_name: str = Field(..., min_length=1, max_length=100)
    proficiency: str = Field(default="intermediate", max_length=50)
    years_experience: Optional[float] = Field(default=None, ge=0)
    status: str = Field(default="UNVERIFIED", max_length=20)

    @field_validator("skill_name")
    @classmethod
    def normalize_skill_name(cls, v: str) -> str:
        """Normalize skill names to lowercase, stripped, with single spaces."""
        return " ".join(v.strip().lower().split())

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"VERIFIED", "UNVERIFIED", "DO_NOT_CLAIM"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"status must be one of {allowed}, got {v!r}")
        return v_upper


class CandidateSkillResponse(BaseModel):
    """Schema for returning a skill in API responses."""
    id: int
    candidate_id: int
    skill_name: str
    proficiency: str
    years_experience: Optional[float]
    status: str

    # CRITICAL: allows Pydantic to read from SQLAlchemy ORM objects
    model_config = ConfigDict(from_attributes=True)


# ---------- PROJECT SCHEMAS ----------

class CandidateProjectCreate(BaseModel):
    """Schema for creating a project."""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    technologies: Optional[str] = Field(default=None, max_length=500)


class CandidateProjectResponse(BaseModel):
    """Schema for returning a project."""
    id: int
    candidate_id: int
    title: str
    description: str
    technologies: Optional[str]

    model_config = ConfigDict(from_attributes=True)


# ---------- CANDIDATE SCHEMAS ----------

class CandidateCreate(BaseModel):
    """Schema for creating a candidate (used in POST requests)."""
    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=50)
    summary: Optional[str] = None
    education: Optional[str] = None
    links: Optional[str] = None
    linkedin_url: Optional[str] = None
    skills: List[CandidateSkillCreate] = Field(default_factory=list)
    projects: List[CandidateProjectCreate] = Field(default_factory=list)


class CandidateResponse(BaseModel):
    """Schema for returning a candidate in API responses."""
    id: int
    name: str
    email: str
    phone: Optional[str]
    summary: Optional[str]
    education: Optional[str]
    links: Optional[str]
    linkedin_url: Optional[str] = None
    skills: List[CandidateSkillResponse] = Field(default_factory=list)
    projects: List[CandidateProjectResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)