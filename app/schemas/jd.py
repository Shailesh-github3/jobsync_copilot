from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ParsedJobDescription(BaseModel):
    """Schema for parsed job description output from LLM."""
    role: str = Field(..., min_length=1, max_length=200)
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    min_experience: Optional[int] = Field(default=None, ge=0)

    model_config = ConfigDict(from_attributes=True)