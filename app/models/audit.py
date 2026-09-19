from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PipelineLog(Base):
    __tablename__ = "pipeline_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_id: Mapped[str] = mapped_column(String(50), index=True)
    stage: Mapped[str] = mapped_column(String(50))  # e.g., "jd_parse", "resume_gen", "claim_verify"
    
    # LLM Metrics
    llm_model: Mapped[Optional[str]] = mapped_column(String(50))
    latency_ms: Mapped[Optional[float]] = mapped_column(Float)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Gate Results
    gate_passed: Mapped[Optional[bool]] = mapped_column(Boolean)
    final_verdict: Mapped[Optional[str]] = mapped_column(String(20))
    
    # Raw data for debugging (truncate if too large in production, but keep for MVP)
    input_summary: Mapped[Optional[str]] = mapped_column(Text)
    output_summary: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<PipelineLog id={self.id} pipeline_id={self.pipeline_id} stage={self.stage}>"