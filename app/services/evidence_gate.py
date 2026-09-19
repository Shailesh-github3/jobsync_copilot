import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models import CandidateSkill, CandidateProject

logger = logging.getLogger(__name__)

def run_deterministic_evidence_gate(
    db: Session,
    candidate_id: int,
    llm_verdict: str,
    cited_evidence_ids: List[str], # e.g., ["1", "2"]
    claim_text: str
) -> Dict[str, Any]:
    """
    Deterministic gate that verifies cited evidence against SQLite ground truth.
    - Checks if the cited ID exists as a VERIFIED skill for the candidate.
    - If not, checks if it exists as a candidate project.
    - Rejects the claim if neither holds true or if the LLM verdict is UNSUPPORTED.
    """
    gate_passed = True
    gate_reason = "LLM verdict accepted."
    final_verdict = llm_verdict

    if llm_verdict in ["SUPPORTED", "PARTIAL"] and cited_evidence_ids:
        for eid_str in cited_evidence_ids:
            # Strip prefixes like 'S' or 'P' if present, or parse directly
            cleaned_str = str(eid_str).strip()
            if cleaned_str.upper().startswith(("S", "P")) and len(cleaned_str) > 1:
                num_part = cleaned_str[1:]
            else:
                num_part = cleaned_str

            try:
                eid = int(num_part)
            except ValueError:
                gate_passed = False
                gate_reason = f"Gate rejected: Invalid evidence ID format '{eid_str}'."
                final_verdict = "UNSUPPORTED"
                break

            # Check 1: Is it a VERIFIED skill?
            skill = db.query(CandidateSkill).filter(
                CandidateSkill.id == eid,
                CandidateSkill.candidate_id == candidate_id
            ).first()

            if skill and skill.status == "VERIFIED":
                continue # This ID is valid, check the next one
            
            # Check 2: Is it a verified project?
            project = db.query(CandidateProject).filter(
                CandidateProject.id == eid,
                CandidateProject.candidate_id == candidate_id
            ).first()

            if project:
                continue # Projects in this table are considered verified evidence for MVP
            
            # If neither, the LLM hallucinated the ID or cited unverified data
            gate_passed = False
            gate_reason = f"Gate rejected: Evidence ID {eid_str} does not exist, is not VERIFIED, or does not belong to this candidate."
            final_verdict = "UNSUPPORTED"
            break

    if llm_verdict == "UNSUPPORTED":
        gate_passed = False
        gate_reason = "Claim lacks supporting evidence."

    return {
        "final_verdict": final_verdict,
        "gate_passed": gate_passed,
        "gate_reason": gate_reason,
        "original_llm_verdict": llm_verdict
    }