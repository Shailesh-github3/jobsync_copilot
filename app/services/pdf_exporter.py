import io
import logging
from xhtml2pdf import pisa
from app.services.resume_exporter import render_resume_html, render_resume_pdf

logger = logging.getLogger(__name__)

def generate_resume_pdf(
    candidate_name: str,
    pipeline_id: str,
    summary: str,
    bullets: list,
    skills: list
) -> bytes:
    """Render the verified resume data into a PDF byte stream using xhtml2pdf."""
    try:
        from collections import namedtuple
        CandidateMock = namedtuple("CandidateMock", ["name", "email", "phone"])
        ResumeMock = namedtuple("ResumeMock", ["tailored_summary", "tailored_bullets", "relevant_skills", "pipeline_id"])
        
        cand = CandidateMock(name=candidate_name, email="", phone=None)
        res = ResumeMock(tailored_summary=summary, tailored_bullets=bullets, relevant_skills=skills, pipeline_id=pipeline_id)
        
        return render_resume_pdf(cand, res)
    except Exception as e:
        logger.error(f"Failed to generate PDF: {e}")
        raise RuntimeError(f"PDF generation failed: {e}")