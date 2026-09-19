from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class ProjectCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=10, description="Specific, verifiable accomplishments and actions.")
    technologies: Optional[str] = Field(default=None, max_length=500)

class ProjectResponse(BaseModel):
    id: int
    candidate_id: int
    title: str
    description: str
    technologies: Optional[str]

    model_config = ConfigDict(from_attributes=True)