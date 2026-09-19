from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class GeneratedResume(BaseModel):
    """Schema for LLM-generated tailored resume."""
    tailored_summary: str = Field(..., min_length=50, description="A 2-3 sentence professional summary tailored to the job.")
    tailored_bullets: List[str] = Field(..., min_items=3, max_items=5, description="3-5 bullet points highlighting relevant experience.")
    relevant_skills: List[str] = Field(..., description="List of verified skills emphasized in this resume.")

    model_config = ConfigDict(from_attributes=True)