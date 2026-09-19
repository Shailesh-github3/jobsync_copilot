import json
import logging
import os
import re
from typing import List, Dict, Any

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.claim_extractor import get_llm_client

logger = logging.getLogger(__name__)

class ClaimVerificationResult(BaseModel):
    claim_text: str = ""
    verdict: str = Field(default="UNSUPPORTED", description="SUPPORTED, PARTIAL, or UNSUPPORTED")
    supported_by: List[str] = Field(default_factory=list, description="List of evidence IDs (e.g., ['1', '2']) that support this claim.")
    reason: str = Field(default="", description="Reason for the verdict.")

    @model_validator(mode="before")
    @classmethod
    def map_synonyms(cls, values):
        if isinstance(values, dict):
            # map verdict synonyms
            if "verdict" not in values and "status" in values:
                values["verdict"] = str(values["status"]).upper()
            # map supported_by synonyms
            if "supported_by" not in values and "evidence" in values:
                ev = values["evidence"]
                values["supported_by"] = [str(x) for x in ev] if isinstance(ev, list) else [str(ev)]
            elif "supported_by" in values and isinstance(values["supported_by"], list):
                values["supported_by"] = [str(x) for x in values["supported_by"]]
            # default claim_text if missing
            if "claim_text" not in values:
                values["claim_text"] = values.get("claim", "")
            # default reason if missing
            if "reason" not in values:
                values["reason"] = values.get("explanation", values.get("notes", "Automated verification"))
        return values

    model_config = ConfigDict(from_attributes=True)

def verify_claim(
    claim_text: str, 
    candidate_evidence: List[Dict[str, Any]] # List of {id, skill_name, evidence_text}
) -> ClaimVerificationResult:
    """Verify a single claim against candidate evidence using LLM + Deterministic Gate."""
    
    evidence_context = "\n".join([
        f"EVIDENCE_ID: {e['id']} [{e.get('type', 'Evidence')}] | {e.get('text', e.get('evidence_text', ''))}"
        for e in candidate_evidence
    ]) or "NO VERIFIED EVIDENCE AVAILABLE."

    prompt = f"""You are a precise, rigorous evaluation and fact-checking engine for technical resumes. Determine if the CLAIM is substantiated by the provided VERIFIED EVIDENCE.

VERIFICATION RULES:
1. SUPPORTED:
   - The claim is SUPPORTED if the verified evidence directly substantiates the core technologies, actions, or accomplishments claimed.
   - Technical Normalization & Synonyms: Standard industry synonyms, equivalent terminology, and natural phrasing are fully SUPPORTED (e.g., "React" = "React.js", "frontend components" = "responsive UIs", "Postgres" = "PostgreSQL", "REST services" = "REST APIs", "Docker containers" = "containerizing applications", "Kubernetes" = "container orchestration").
   - Multi-Evidence Aggregation: If multiple pieces of evidence or sentences together substantiate the technologies (e.g., "Built REST APIs using Spring Boot" + "Used PostgreSQL for persistence" -> "Developed full-stack applications with Spring Boot and PostgreSQL"), this is fully SUPPORTED.
   - Generalization: Standard tool generalization (e.g., Jenkins -> CI/CD pipelines, Git in team projects -> proficient in Git) is SUPPORTED.

2. PARTIAL:
   - The claim is PARTIAL if the candidate demonstrably has the verified skill or base experience, but has inflated the scope, environment, or responsibility:
     * Skill-Only Evidence: If the evidence contains the skill name (e.g., "Spring Boot") but the claim asserts architectural actions (e.g., "Architected microservices using Spring Boot"), the verdict MUST be PARTIAL.
     * Environment / Production Inflation: If the evidence shows development experience with an operating system / tool (e.g., "Used Linux for development") but the claim exaggerates to server administration (e.g., "Administered production Linux servers"), the verdict MUST be PARTIAL (NOT Unsupported, because Linux experience is verified).
     * Scope Inflation: If the evidence shows managing developers (e.g. "Managed a team of 5 developers") but the claim says "Led cross-functional teams", the verdict is PARTIAL.

3. UNSUPPORTED (ZERO-TOLERANCE FOR FABRICATION & UNRELATED CLAIMS):
   - The claim is UNSUPPORTED if the core claimed technology, architecture, metrics, or roles have NO basis in the verified text (e.g., claiming Kubernetes when only Docker was used; claiming Python from coursework to mean 5 years professional experience; claiming team leadership when only contributing to open source; claiming MongoDB production clusters when only doing a class project; or claiming 'Architected scalable microservices' when evidence is only 'Worked with REST APIs').
   - If there is NO verified evidence provided (empty evidence), the verdict MUST be UNSUPPORTED.

4. CITED EVIDENCE:
   - In "supported_by", you MUST list the exact EVIDENCE_IDs (e.g. ["E1"] or ["1"]) from the verified evidence that substantiate or partially ground the claim. If UNSUPPORTED, return [].

5. Return ONLY a valid JSON object matching these exact keys:
   - "claim_text": "{claim_text}"
   - "verdict": "SUPPORTED" | "PARTIAL" | "UNSUPPORTED"
   - "supported_by": ["EVIDENCE_ID", ...]
   - "reason": "Concise explanation of verdict."

CLAIM: "{claim_text}"

VERIFIED EVIDENCE:
{evidence_context}

Return ONLY valid JSON. No markdown, no explanations."""
    client, model = get_llm_client()

    for attempt in range(4):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            content = response.choices[0].message.content or ""
            content = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.MULTILINE)
            content = re.sub(r"\s*```$", "", content.strip(), flags=re.MULTILINE)
            
            data = json.loads(content.strip())
            if "claim_text" not in data or not data["claim_text"]:
                data["claim_text"] = claim_text
            return ClaimVerificationResult(**data)
        except Exception as e:
            err_str = str(e)
            if ("429" in err_str or "rate_limit" in err_str.lower()) and attempt < 3:
                wait_s = (attempt + 1) * 3
                logger.warning(f"Rate limited during claim verification. Retrying in {wait_s}s...")
                import time
                time.sleep(wait_s)
                continue
            logger.error(f"Claim verification failed: {e}")
            raise ValueError(f"Failed to verify claim: {e}")