from contextlib import asynccontextmanager
from typing import List
import os
import json
import time
from dotenv import load_dotenv

from app.models.audit import PipelineLog

# Load environment variables
load_dotenv()



import logging
from fastapi import FastAPI, Depends, HTTPException, Response, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy import inspect, text, func 
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)

from app.db.database import Base, engine, get_db
from app.models import CandidateProfile, CandidateSkill, CandidateProject, Job, Resume
from app.schemas import (
    CandidateCreate,
    CandidateResponse,
    JobCreate,
    JobResponse,
    JobMatchResponse,
    MatchDetailsResponse,
    ProjectCreate,
    ProjectResponse,
)
from app.services.evaluation_loader import load_evaluation_cases, get_case_categories
from app.services.jd_parser import parse_job_description, JDParseError
from app.services.matcher import match_candidate_to_job
from app.services.normalizer import normalize_skill, normalize_skills
from app.services.scraper import scrape_sample_jobs
from app.services.resume_generator import generate_tailored_resume, ResumeGenerationError

from app.services.claim_extractor import extract_claims
from app.services.claim_verifier import verify_claim
from app.services.evidence_gate import run_deterministic_evidence_gate

from app.services.telegram_service import send_telegram_notification, answer_callback_query
from app.services.resume_exporter import render_resume_html, render_resume_pdf
from app.services.pdf_exporter import generate_resume_pdf
from app.services.audit_logger import log_pipeline_event
from app.services.background_tasks import run_self_healing_pipeline

limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="JobSync Copilot",
    description="Privacy-first AI job application copilot",
    version="0.1.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------- HEALTH + DB CHECK ----------

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/db-check")
def db_check(db: Session = Depends(get_db)):
    try:
        result = db.execute(text("SELECT 1"))
        result.fetchone()

        return {
            "status": "ok",
            "database": "connected",
        }

    except Exception as e:
        return {
            "status": "error",
            "detail": str(e),
        }


@app.get("/tables")
def list_tables(db: Session = Depends(get_db)):
    inspector = inspect(db.get_bind())

    return {
        "tables": inspector.get_table_names(),
    }
    

@app.get("/evaluation/status")
def evaluation_status():
    """Report how many evaluation cases are loaded and their categories."""
    try:
        suite = load_evaluation_cases()
        categories = get_case_categories(suite)
        return {
            "status": "loaded",
            "version": suite.version,
            "total_cases": len(suite.test_cases),
            "categories": categories,
        }
    except FileNotFoundError as e:
        return {"status": "error", "detail": str(e)}
    except ValueError as e:
        return {"status": "error", "detail": str(e)}


# ---------- CANDIDATE CRUD ----------

@app.post("/seed", response_model=CandidateResponse)
def seed_candidate(db: Session = Depends(get_db)):
    """Seed a sample candidate."""

    # Check if the seed candidate already exists
    existing = db.query(CandidateProfile).filter(CandidateProfile.email == "ada@example.com").first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Seed candidate already exists",
        )

    # Pydantic validates the seed data
    payload = CandidateCreate(
        name="Ada Lovelace",
        email="ada@example.com",
        phone="+1-555-0100",
        summary="Backend engineer specializing in Java and Spring Boot.",
        skills=[
            {
                "skill_name": "Java",
                "proficiency": "expert",
                "years_experience": 5.0,
                "status": "VERIFIED",
            },
            {
                "skill_name": "Spring Boot",
                "proficiency": "expert",
                "years_experience": 4.0,
                "status": "VERIFIED",  # This will raise a validation error
            },
            {
                "skill_name": "PostgreSQL",
                "proficiency": "intermediate",
                "years_experience": 3.0,
                "status": "UNVERIFIED",
            },
        ],
        projects=[],
    )

    # Pydantic schema → SQLAlchemy ORM object
    candidate = CandidateProfile(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        summary=payload.summary,
    )

    # Create SQLAlchemy skill objects
    for skill_data in payload.skills:
        skill = CandidateSkill(
            skill_name=skill_data.skill_name,
            proficiency=skill_data.proficiency,
            years_experience=skill_data.years_experience,
            status=skill_data.status,
        )
        candidate.skills.append(skill)

    # Create SQLAlchemy project objects
    for project_data in payload.projects:
        project = CandidateProject(
            title=project_data.title,
            description=project_data.description,
            technologies=project_data.technologies,
        )
        candidate.projects.append(project)

    db.add(candidate)
    db.commit()
    db.refresh(candidate)

    # SQLAlchemy ORM object → Pydantic response schema
    return candidate


@app.get("/candidates", response_model=List[CandidateResponse])
def list_candidates(db: Session = Depends(get_db)):
    """Return all candidates with their skills and projects."""

    candidates = db.query(CandidateProfile).all()

    return candidates


@app.get("/candidates/{candidate_id}", response_model=CandidateResponse)
def get_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
):
    """Return a single candidate by ID."""

    candidate = db.query(CandidateProfile).filter(
        CandidateProfile.id == candidate_id
    ).first()

    if not candidate:
        raise HTTPException(
            status_code=404,
            detail="Candidate not found",
        )

    return candidate


@app.post("/candidates", response_model=CandidateResponse)
def create_candidate(
    candidate_data: CandidateCreate,
    db: Session = Depends(get_db),
):
    """Create a new candidate with their skills and projects."""

    # Check if candidate already exists
    existing = db.query(CandidateProfile).filter(
        CandidateProfile.email == candidate_data.email
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Candidate with this email already exists",
        )

    # Pydantic CandidateCreate → SQLAlchemy CandidateProfile
    candidate = CandidateProfile(
        name=candidate_data.name,
        email=candidate_data.email,
        phone=candidate_data.phone,
        summary=candidate_data.summary,
        education=candidate_data.education,
        links=candidate_data.links,
    )

    # Pydantic skills → SQLAlchemy skills
    for skill_data in candidate_data.skills:
        skill = CandidateSkill(
            skill_name=skill_data.skill_name,
            proficiency=skill_data.proficiency,
            years_experience=skill_data.years_experience,
            status=skill_data.status,
        )
        candidate.skills.append(skill)

    # Pydantic projects → SQLAlchemy projects
    for project_data in candidate_data.projects:
        project = CandidateProject(
            title=project_data.title,
            description=project_data.description,
            technologies=project_data.technologies,
        )
        candidate.projects.append(project)

    # Save to database
    db.add(candidate)
    db.commit()
    db.refresh(candidate)

    # SQLAlchemy ORM → CandidateResponse
    return candidate


@app.post("/candidates/{candidate_id}/projects", response_model=ProjectResponse, status_code=201)
def add_candidate_project(
    candidate_id: int,
    project_data: ProjectCreate,
    db: Session = Depends(get_db),
):
    """Add a verified project to a candidate profile."""
    candidate = db.query(CandidateProfile).filter(CandidateProfile.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    project = CandidateProject(
        candidate_id=candidate_id,
        title=project_data.title,
        description=project_data.description,
        technologies=project_data.technologies,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project

# ---------- JOB CRUD & PARSING ----------

@app.post("/jobs/sample", response_model=List[JobResponse])
def add_sample_jobs(db: Session = Depends(get_db)):
    """Seed sample job postings."""
    sample_data = scrape_sample_jobs()
    created_jobs = []

    for item in sample_data:
        existing = db.query(Job).filter(Job.source_url == item["source_url"]).first()
        if not existing:
            job = Job(
                title=item.get("title"),
                company=item.get("company"),
                raw_description=item.get("raw_description"),
                source_url=item.get("source_url"),
                parse_status="PENDING",
            )
            db.add(job)
            created_jobs.append(job)
        else:
            created_jobs.append(existing)

    db.commit()
    for job in created_jobs:
        db.refresh(job)

    return created_jobs


@app.get("/jobs", response_model=List[JobResponse])
def list_jobs(db: Session = Depends(get_db)):
    """Return all jobs in the database."""
    return db.query(Job).all()


@app.post("/jobs/{job_id}/parse", response_model=JobResponse)
@limiter.limit("5/minute")
def parse_job(request: Request, job_id: int, db: Session = Depends(get_db)):
    """Parse a job description using LLM and update the job record."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.parse_status in ("PASSED", "PARSED"):
        raise HTTPException(status_code=400, detail="Job already parsed")

    try:
        parsed = parse_job_description(job.raw_description)

        # Update job with parsed data
        job.parsed_role = parsed.role
        job.parsed_required_skills = json.dumps(parsed.required_skills)
        job.parsed_preferred_skills = json.dumps(parsed.preferred_skills)
        job.parsed_min_experience = parsed.min_experience
        job.parse_status = "PARSED"

        db.commit()
        db.refresh(job)

        return job

    except JDParseError as e:
        job.parse_status = "FAILED"
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_id}/parsed")
def get_parsed_job(job_id: int, db: Session = Depends(get_db)):
    """Return only the parsed fields of a job description."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.parse_status not in ("PASSED", "PARSED"):
        raise HTTPException(status_code=400, detail="Job not parsed yet")

    # Parse JSON strings back into lists
    required_skills = json.loads(job.parsed_required_skills) if job.parsed_required_skills else []
    preferred_skills = json.loads(job.parsed_preferred_skills) if job.parsed_preferred_skills else []

    return {
        "role": job.parsed_role,
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "min_experience": job.parsed_min_experience,
    }


@app.post("/jobs/{job_id}/match/{candidate_id}", response_model=JobResponse)
def match_job(job_id: int, candidate_id: int, db: Session = Depends(get_db)):
    """Match a candidate against a job and store the result."""
    # Get job
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.parse_status != "PARSED":
        raise HTTPException(status_code=400, detail="Job not parsed yet")

    # Get candidate
    candidate = db.query(CandidateProfile).filter(CandidateProfile.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Get candidate's verified skills
    candidate_skills = [
        skill.skill_name
        for skill in candidate.skills
        if skill.status == "VERIFIED"
    ]

    # Parse job requirements
    required_skills = json.loads(job.parsed_required_skills) if job.parsed_required_skills else []
    preferred_skills = json.loads(job.parsed_preferred_skills) if job.parsed_preferred_skills else []

    # Run matching
    result = match_candidate_to_job(candidate_skills, required_skills, preferred_skills)

    # Update job with match results
    job.match_score = result.score
    job.match_explanation = result.explanation
    job.match_status = "MATCHED" if result.score >= 60 else "NOT_MATCHED"
    job.match_details = json.dumps(result.to_dict())

    db.commit()
    db.refresh(job)

    return job


@app.get("/jobs/{job_id}/match-details", response_model=MatchDetailsResponse)
def get_match_details(job_id: int, db: Session = Depends(get_db)):
    """Return the structured match details of a job (Mini Challenge)."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.match_details:
        raise HTTPException(status_code=400, detail="Job has not been matched with a candidate yet")

    return json.loads(job.match_details)


# ---------- NORMALIZATION ----------

@app.post("/normalize")
def normalize_endpoint(skills: list[str]):
    """Normalize a list of skill names. Useful for testing."""
    normalized = normalize_skills(skills)
    return {
        "input": skills,
        "output": normalized,
    }


@app.get("/normalize/{skill}")
def normalize_single(skill: str):
    """Normalize a single skill name."""
    return {
        "input": skill,
        "output": normalize_skill(skill),
    }
    
    
# ---------- RESUME GENERATION ----------

@app.post("/jobs/{job_id}/resume/{candidate_id}", response_model=dict)
@limiter.limit("5/minute")
def generate_resume(request: Request, job_id: int, candidate_id: int, db: Session = Depends(get_db)):
    """Generate a tailored resume for a candidate against a specific job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or job.parse_status != "PARSED":
        raise HTTPException(status_code=400, detail="Job must be parsed first")

    candidate = db.query(CandidateProfile).filter(CandidateProfile.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # 1. Gather ONLY verified data
    verified_skills = [
        skill.skill_name 
        for skill in candidate.skills 
        if skill.status == "VERIFIED"
    ]
    
    verified_experience = []
    if candidate.summary:
        verified_experience.append(f"Professional Summary: {candidate.summary}")
    for project in candidate.projects:
        tech_info = f" (Tech: {project.technologies})" if project.technologies else ""
        verified_experience.append(f"Project '{project.title}': {project.description}{tech_info}")

    # 2. Parse job requirements
    required_skills = json.loads(job.parsed_required_skills) if job.parsed_required_skills else []
    preferred_skills = json.loads(job.parsed_preferred_skills) if job.parsed_preferred_skills else []

    # 3. Generate Resume
    try:
        generated = generate_tailored_resume(
            candidate_name=candidate.name,
            verified_skills=verified_skills,
            verified_experience=verified_experience,
            job_role=job.parsed_role or job.title or "Unknown Role",
            job_required_skills=required_skills,
            job_preferred_skills=preferred_skills,
        )
    except ResumeGenerationError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 4. Save to database
    resume = Resume(
        candidate_id=candidate_id,
        job_id=job_id,
        pipeline_id=f"PIPE-2026-{job_id:03d}",  # Simple pipeline ID for MVP
        tailored_summary=generated.tailored_summary,
        tailored_bullets=json.dumps(generated.tailored_bullets),
        relevant_skills=json.dumps(generated.relevant_skills),
        validation_status="PENDING",
    )
    
    db.add(resume)
    db.commit()
    db.refresh(resume)

    return {
        "resume_id": resume.id,
        "pipeline_id": resume.pipeline_id,
        "status": "PENDING",
        "summary": generated.tailored_summary,
        "bullets": generated.tailored_bullets,
        "skills": generated.relevant_skills,
    }

# ---------- RESUME VALIDATION ----------

@app.post("/resumes/{resume_id}/validate", response_model=dict)
@limiter.limit("5/minute")
def validate_resume(request: Request, resume_id: int, db: Session = Depends(get_db)):
    """Run the full claim extraction, verification, and deterministic evidence gate."""
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    if resume.validation_status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Resume already validated with status: {resume.validation_status}")

    candidate = db.query(CandidateProfile).filter(CandidateProfile.id == resume.candidate_id).first()
    
    # 1. Extract Claims
    bullets = json.loads(resume.tailored_bullets) if resume.tailored_bullets else []
    extraction_result = extract_claims(resume.tailored_summary or "", bullets)
    
    # 2. Gather Verified Evidence from BOTH skills and projects
    verified_evidence = []
    # 1. Add Skills
    for skill in candidate.skills:
        if skill.status == "VERIFIED":
            verified_evidence.append({
                "id": str(skill.id),
                "type": "Skill",
                "text": f"Skill: {skill.skill_name} ({skill.proficiency}, {skill.years_experience} years)"
            })
    # 2. Add Projects
    for project in candidate.projects:
        verified_evidence.append({
            "id": str(project.id),
            "type": "Project",
            "text": f"Project '{project.title}': {project.description}. Technologies: {project.technologies or 'N/A'}"
        })

    validation_results = []
    overall_passed = True

    # 3. Verify each claim and run the deterministic gate
    for claim in extraction_result.claims:
        # LLM Verification
        llm_result = verify_claim(claim.claim_text, verified_evidence)
        
        # Deterministic Gate
        gate_result = run_deterministic_evidence_gate(
            db=db,
            candidate_id=candidate.id,
            llm_verdict=llm_result.verdict,
            cited_evidence_ids=llm_result.supported_by,
            claim_text=claim.claim_text
        )
        
        validation_results.append({
            "claim": claim.claim_text,
            "llm_verdict": llm_result.verdict,
            "final_verdict": gate_result["final_verdict"],
            "gate_passed": gate_result["gate_passed"],
            "reason": gate_result["gate_reason"]
        })
        
        if not gate_result["gate_passed"]:
            overall_passed = False

    # 4. Update Resume Status
    resume.validation_status = "PASSED" if overall_passed else "FAILED"
    db.commit()
    db.refresh(resume)

    return {
        "resume_id": resume.id,
        "pipeline_id": resume.pipeline_id,
        "final_status": resume.validation_status,
        "claim_validations": validation_results
    }
    

# --------- TELEGRAM NOTIFICATIONS ----------
@app.post("/resumes/{resume_id}/notify", response_model=dict)
def notify_candidate(resume_id: int, db: Session = Depends(get_db)):
    """Trigger a Telegram notification for a PASSED resume."""
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    # Strict validation check: only notify if the deterministic gate verified all claims
    if resume.validation_status != "PASSED":
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot notify for resume with validation status '{resume.validation_status}'. Resume must pass truth validation (PASSED) before notifying the candidate."
        )

    if resume.approval_status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Resume already {resume.approval_status}")

    job = db.query(Job).filter(Job.id == resume.job_id).first()
    job_title = (job.parsed_role or job.title) if job else "Backend Engineer"
    
    score = 0.0
    if job and job.match_explanation and "Score:" in job.match_explanation:
        try:
            score_str = job.match_explanation.split("Score:")[1].split("/")[0].strip()
            score = float(score_str)
        except (ValueError, IndexError):
            score = 0.0
    elif job and job.match_score is not None:
        score = float(job.match_score)

    success = send_telegram_notification(
        resume_id=resume.id,
        pipeline_id=resume.pipeline_id or f"PIPE-2026-{resume.id:03d}",
        job_title=job_title,
        score=score,
        explanation=(job.match_explanation if job else None) or "Match criteria met for Java and Spring Boot.",
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send Telegram notification")
        
    return {"status": "notified", "resume_id": resume_id}


@app.get("/resumes/{resume_id}")
def get_resume(resume_id: int, db: Session = Depends(get_db)):
    """Return details and approval status of a resume."""
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    return {
        "id": resume.id,
        "candidate_id": resume.candidate_id,
        "job_id": resume.job_id,
        "pipeline_id": resume.pipeline_id,
        "validation_status": resume.validation_status,
        "approval_status": resume.approval_status,
        "summary": resume.tailored_summary,
        "bullets": json.loads(resume.tailored_bullets) if resume.tailored_bullets else [],
        "skills": json.loads(resume.relevant_skills) if resume.relevant_skills else [],
        "created_at": resume.created_at.isoformat() if resume.created_at else None,
    }


@app.get("/resumes/{resume_id}/export", response_class=HTMLResponse)
def export_resume_html(resume_id: int, db: Session = Depends(get_db)):
    """Export a validated resume as a styled, professional HTML page.
    Only PASSED resumes can be exported.
    """
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    if resume.validation_status != "PASSED":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot export resume. Status is {resume.validation_status}. Only PASSED resumes can be exported."
        )

    candidate = db.query(CandidateProfile).filter(CandidateProfile.id == resume.candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    html_content = render_resume_html(candidate=candidate, resume=resume)
    return HTMLResponse(content=html_content, status_code=200)


@app.get("/resumes/{resume_id}/export/pdf")
def export_resume_pdf(resume_id: int, db: Session = Depends(get_db)):
    """Export a validated resume as a downloadable PDF file.
    Only PASSED resumes can be exported.
    """
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    if resume.validation_status != "PASSED":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot export resume. Status is {resume.validation_status}. Only PASSED resumes can be exported."
        )

    candidate = db.query(CandidateProfile).filter(CandidateProfile.id == resume.candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    pdf_bytes = render_resume_pdf(candidate=candidate, resume=resume)

    safe_name = "_".join(candidate.name.split())
    filename = f"{safe_name}_Verified_Resume.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        },
    )


@app.post("/webhook/telegram")
def telegram_webhook(update: dict, db: Session = Depends(get_db)):
    """
    Handles incoming updates from Telegram Bot API.
    For local demo, this can be simulated via curl.
    """
    # Check if it's a callback query (button click)
    if "callback_query" in update:
        callback = update["callback_query"]
        callback_query_id = callback.get("id", "simulated_callback_id")
        data = callback.get("data", "") # e.g., "approve_1" or "reject_1"
        
        # Parse action and resume_id
        parts = data.split("_")
        if len(parts) == 2:
            action = parts[0].upper()
            try:
                resume_id = int(parts[1])
            except ValueError:
                return {"status": "error", "detail": "Invalid resume ID"}
            
            # Update database
            resume = db.query(Resume).filter(Resume.id == resume_id).first()
            if resume:
                resume.approval_status = action
                db.commit()
                db.refresh(resume)
                
                # Answer the callback to remove the loading spinner in Telegram
                answer_callback_query(
                    callback_query_id, 
                    f"Resume {action}D successfully!"
                )
                
                return {"status": "ok", "action": action, "resume_id": resume_id, "approval_status": resume.approval_status}
            else:
                return {"status": "error", "detail": f"Resume {resume_id} not found"}
            
    return {"status": "ignored", "reason": "Not a valid callback query"}


# ---------- RESUME SELF-HEALING LOOP (ASYNC BACKGROUND TASK) ----------

@app.post("/resumes/{resume_id}/heal", status_code=202)
@limiter.limit("5/minute")
def heal_resume(
    request: Request,
    resume_id: int,
    background_tasks: BackgroundTasks,
    max_attempts: int = 3,
    db: Session = Depends(get_db)
):
    """Trigger the self-healing resume generation pipeline in the background."""
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    pipeline_id = resume.pipeline_id or f"PIPE-2026-{resume.id:03d}"
    resume.pipeline_id = pipeline_id
    resume.processing_status = "RUNNING"
    resume.validation_status = "PENDING"
    db.commit()
    
    background_tasks.add_task(run_self_healing_pipeline, resume_id=resume.id, max_attempts=max_attempts)
    
    return {
        "status": "accepted",
        "message": "Self-healing pipeline started in the background.",
        "resume_id": resume.id,
        "pipeline_id": pipeline_id
    }


# ---------- PIPELINE STATUS & METRICS ----------

@app.get("/pipelines/{pipeline_id}/status", response_model=dict)
def get_pipeline_status(pipeline_id: str, db: Session = Depends(get_db)):
    """Poll the status of a background pipeline job."""
    resume = db.query(Resume).filter(Resume.pipeline_id == pipeline_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    
    msg = "Job completed." if resume.processing_status in ["PASSED", "FAILED"] else "Job is still processing. Please poll again in a few seconds."
    return {
        "pipeline_id": resume.pipeline_id,
        "resume_id": resume.id,
        "processing_status": resume.processing_status,
        "validation_status": resume.validation_status,
        "message": msg
    }


@app.get("/metrics/pipeline/{pipeline_id}", response_model=dict)
def get_pipeline_metrics(pipeline_id: str, db: Session = Depends(get_db)):
    """Retrieve aggregated metrics for a specific pipeline run."""
    logs = db.query(PipelineLog).filter(PipelineLog.pipeline_id == pipeline_id).all()
    
    if not logs:
        raise HTTPException(status_code=404, detail="No logs found for this pipeline")
    
    total_latency = sum(log.latency_ms or 0 for log in logs)
    total_prompt_tokens = sum(log.prompt_tokens or 0 for log in logs)
    total_completion_tokens = sum(log.completion_tokens or 0 for log in logs)
    
    gate_failures = sum(1 for log in logs if log.stage == "claim_verification" and log.gate_passed == False)
    total_verifications = sum(1 for log in logs if log.stage == "claim_verification")
    
    leakage_rate = (gate_failures / total_verifications * 100) if total_verifications > 0 else 0.0

    return {
        "pipeline_id": pipeline_id,
        "total_stages_logged": len(logs),
        "total_latency_ms": round(total_latency, 2),
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "claim_verifications": total_verifications,
        "gate_rejections": gate_failures,
        "hallucination_leakage_rate_percent": round(leakage_rate, 2),
        "final_status": logs[-1].final_verdict if logs else "UNKNOWN"
    }