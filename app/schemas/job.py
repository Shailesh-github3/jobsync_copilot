from datetime import datetime
import json
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobCreate(BaseModel):
    """Schema for manually creating a job."""
    source_url: Optional[str] = Field(default=None, max_length=500)
    raw_description: str = Field(..., min_length=10)
    title: Optional[str] = Field(default=None, max_length=200)
    company: Optional[str] = Field(default=None, max_length=200)


class JobResponse(BaseModel):
    """Schema for returning a job in API responses."""
    id: int
    source_url: Optional[str] = None
    raw_description: str
    title: Optional[str] = None
    company: Optional[str] = None
    parse_status: str
    created_at: datetime
    parsed_role: Optional[str] = None
    parsed_required_skills: Optional[List[str]] = None
    parsed_preferred_skills: Optional[List[str]] = None
    parsed_min_experience: Optional[int] = None
    # Match fields
    match_score: Optional[float] = None
    match_explanation: Optional[str] = None
    match_status: Optional[str] = None

    @field_validator("parsed_required_skills", "parsed_preferred_skills", mode="before")
    @classmethod
    def parse_json_skills(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v

    model_config = ConfigDict(from_attributes=True)


class JobMatchResponse(BaseModel):
    """Schema for candidate-job matching result."""
    id: int
    title: Optional[str] = None
    parse_status: str
    match_score: float
    match_explanation: str
    match_status: str

    model_config = ConfigDict(from_attributes=True)


class MatchDetailsResponse(BaseModel):
    """Schema for structured match details (Mini Challenge)."""
    score: float
    matched_required: List[str]
    missing_required: List[str]
    matched_preferred: List[str]
    missing_preferred: List[str]
    explanation: str

    model_config = ConfigDict(from_attributes=True)