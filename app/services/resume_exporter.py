import json
from pathlib import Path
from typing import Any, Dict
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models import CandidateProfile, Resume

# Locate templates directory relative to project structure
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

def render_resume_html(candidate: CandidateProfile, resume: Resume) -> str:
    """Render a candidate's verified resume into formatted HTML using Jinja2."""
    template = env.get_template("resume.html")
    
    # Safely parse JSON strings to Python lists
    if isinstance(resume.tailored_bullets, str):
        try:
            bullets = json.loads(resume.tailored_bullets)
        except Exception:
            bullets = [resume.tailored_bullets]
    else:
        bullets = resume.tailored_bullets or []

    if isinstance(resume.relevant_skills, str):
        try:
            skills = json.loads(resume.relevant_skills)
        except Exception:
            skills = [resume.relevant_skills]
    else:
        skills = resume.relevant_skills or []

    return template.render(
        candidate=candidate,
        resume=resume,
        bullets=bullets,
        skills=skills,
    )

def render_resume_pdf(candidate: CandidateProfile, resume: Resume) -> bytes:
    """Convert a candidate's verified resume HTML into downloadable PDF bytes."""
    import io
    from xhtml2pdf import pisa

    html_content = render_resume_html(candidate=candidate, resume=resume)
    pdf_buffer = io.BytesIO()
    
    pisa_status = pisa.CreatePDF(
        src=html_content,
        dest=pdf_buffer,
        encoding="utf-8"
    )
    
    if pisa_status.err:
        raise RuntimeError("Failed to generate PDF from HTML template.")
        
    return pdf_buffer.getvalue()