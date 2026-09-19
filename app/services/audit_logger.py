import logging
from typing import Optional
from sqlalchemy.orm import Session
from app.models.audit import PipelineLog

logger = logging.getLogger(__name__)

def log_pipeline_event(
    db: Session,
    pipeline_id: str,
    stage: str,
    llm_model: Optional[str] = None,
    latency_ms: Optional[float] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    gate_passed: Optional[bool] = None,
    final_verdict: Optional[str] = None,
    input_summary: Optional[str] = None,
    output_summary: Optional[str] = None,
    error_message: Optional[str] = None,
):
    """Persist a pipeline event to the database for audit and metrics."""
    try:
        # Truncate long strings to prevent DB bloat in MVP
        input_summary = (input_summary[:500] + "...") if input_summary and len(input_summary) > 500 else input_summary
        output_summary = (output_summary[:500] + "...") if output_summary and len(output_summary) > 500 else output_summary
        error_message = (error_message[:500] + "...") if error_message and len(error_message) > 500 else error_message

        log_entry = PipelineLog(
            pipeline_id=pipeline_id,
            stage=stage,
            llm_model=llm_model,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            gate_passed=gate_passed,
            final_verdict=final_verdict,
            input_summary=input_summary,
            output_summary=output_summary,
            error_message=error_message,
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log pipeline event: {e}")
        db.rollback()