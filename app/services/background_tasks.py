import logging
import time
import json
import os
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.models import Resume, CandidateProfile, Job, CandidateSkill, CandidateProject
from app.services.resume_generator import generate_tailored_resume
from app.services.claim_extractor import extract_claims
from app.services.claim_verifier import verify_claim
from app.services.evidence_gate import run_deterministic_evidence_gate
from app.services.audit_logger import log_pipeline_event

logger = logging.getLogger(__name__)

def run_self_healing_pipeline(resume_id: int, max_attempts: int = 3):
    """Background task to run the self-healing loop without blocking the HTTP request."""
    db = SessionLocal()
    try:
        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        if not resume:
            logger.error(f"Resume {resume_id} not found for background task")
            return

        # Mark as running
        resume.processing_status = "RUNNING"
        db.commit()

        candidate = db.query(CandidateProfile).filter(CandidateProfile.id == resume.candidate_id).first()
        job = db.query(Job).filter(Job.id == resume.job_id).first()

        verified_skills = [skill.skill_name for skill in candidate.skills if skill.status == "VERIFIED"]
        verified_experience = []
        if candidate.summary:
            verified_experience.append(f"Professional Summary: {candidate.summary}")
        for project in candidate.projects:
            tech_info = f" (Tech: {project.technologies})" if project.technologies else ""
            verified_experience.append(f"Project '{project.title}': {project.description}{tech_info}")

        required_skills = json.loads(job.parsed_required_skills) if job.parsed_required_skills else []
        preferred_skills = json.loads(job.parsed_preferred_skills) if job.parsed_preferred_skills else []

        excluded_claims = []
        llm_model_name = os.getenv("GROQ_MODEL", "groq/llama-3.3-70b-versatile")

        for attempt in range(max_attempts):
            logger.info(f"--- Background Healing Attempt {attempt + 1}/{max_attempts} for Resume {resume_id} ---")
            attempt_start = time.time()
            
            try:
                generated = generate_tailored_resume(
                    candidate_name=candidate.name,
                    verified_skills=verified_skills,
                    verified_experience=verified_experience,
                    job_role=job.parsed_role or job.title or "Unknown Role",
                    job_required_skills=required_skills,
                    job_preferred_skills=preferred_skills,
                    excluded_claims=excluded_claims,
                )
                
                latency = (time.time() - attempt_start) * 1000

                log_pipeline_event(
                    db=db,
                    pipeline_id=resume.pipeline_id,
                    stage="resume_generation",
                    llm_model=llm_model_name,
                    latency_ms=latency,
                    input_summary=f"Skills: {len(verified_skills)}, Excluded: {len(excluded_claims)}",
                    output_summary=generated.tailored_summary[:100] if generated.tailored_summary else "",
                )

                resume.tailored_summary = generated.tailored_summary
                resume.tailored_bullets = json.dumps(generated.tailored_bullets)
                resume.relevant_skills = json.dumps(generated.relevant_skills)
                resume.validation_status = "PENDING"
                db.commit()

                # Verification Logic
                bullets = json.loads(resume.tailored_bullets) if resume.tailored_bullets else []
                extraction_result = extract_claims(resume.tailored_summary or "", bullets)
                
                verified_evidence = []
                for skill in candidate.skills:
                    if skill.status == "VERIFIED":
                        verified_evidence.append({
                            "id": str(skill.id),
                            "type": "Skill",
                            "text": f"Skill: {skill.skill_name} ({skill.proficiency}, {skill.years_experience} years)"
                        })
                for project in candidate.projects:
                    verified_evidence.append({
                        "id": str(project.id),
                        "type": "Project",
                        "text": f"Project '{project.title}': {project.description}. Technologies: {project.technologies or 'N/A'}"
                    })

                overall_passed = True
                new_excluded_claims = []

                for claim in extraction_result.claims:
                    verify_start = time.time()
                    llm_result = verify_claim(claim.claim_text, verified_evidence)
                    verify_latency = (time.time() - verify_start) * 1000

                    gate_result = run_deterministic_evidence_gate(
                        db=db, candidate_id=candidate.id, llm_verdict=llm_result.verdict, 
                        cited_evidence_ids=llm_result.supported_by, claim_text=claim.claim_text
                    )
                    
                    log_pipeline_event(
                        db=db,
                        pipeline_id=resume.pipeline_id,
                        stage="claim_verification",
                        llm_model=llm_model_name,
                        latency_ms=verify_latency,
                        gate_passed=gate_result["gate_passed"],
                        final_verdict=gate_result["final_verdict"],
                        input_summary=claim.claim_text,
                        output_summary=gate_result["gate_reason"],
                    )
                    
                    if not gate_result["gate_passed"]:
                        overall_passed = False
                        new_excluded_claims.append(claim.claim_text)

                if overall_passed:
                    resume.validation_status = "PASSED"
                    resume.processing_status = "PASSED"
                    db.commit()
                    logger.info(f"Resume {resume_id} successfully healed on attempt {attempt + 1}")
                    return
                else:
                    logger.warning(f"Attempt {attempt + 1} failed. Excluding: {new_excluded_claims}")
                    excluded_claims = new_excluded_claims

            except Exception as e:
                logger.error(f"Error in healing attempt {attempt + 1}: {e}")
                db.rollback() # Rollback any failed transaction state

        # If we exit the loop, it failed all attempts
        resume.validation_status = "FAILED"
        resume.processing_status = "FAILED"
        db.commit()
        logger.warning(f"Resume {resume_id} failed to heal after {max_attempts} attempts.")

    except Exception as e:
        logger.error(f"Critical error in run_self_healing_pipeline for resume {resume_id}: {e}")
        db.rollback()
    finally:
        db.close()