import json
import logging
import os
import re
from typing import List

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

class ExtractedClaim(BaseModel):
    claim_text: str = Field(..., description="The specific factual claim extracted from the resume.")
    claim_type: str = Field(..., description="e.g., 'technical_skill', 'experience', 'role', 'metric'")

    model_config = ConfigDict(from_attributes=True)

class ClaimExtractionResult(BaseModel):
    claims: List[ExtractedClaim] = Field(..., description="List of extracted claims.")

    model_config = ConfigDict(from_attributes=True)

def get_llm_client() -> tuple[OpenAI, str]:
    """Lazy initialization of LLM client with pre-check and auto-detection."""
    groq_api_key = (
        os.getenv("GROQ_API_KEY")
        or os.getenv("GROQ_KEY")
        or os.getenv("GROQ_APIKEY")
        or os.getenv("GROQ")
    )
    openai_api_key = os.getenv("OPENAI_API_KEY")

    api_key = groq_api_key or openai_api_key
    if not api_key:
        raise ValueError("LLM API key not configured.")

    is_groq = bool(groq_api_key) or api_key.startswith("gsk_")
    if is_groq:
        base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
        client = OpenAI(base_url=base_url, api_key=api_key)
        return client, model
    else:
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        client = OpenAI(api_key=api_key)
        return client, model

def extract_claims(resume_summary: str, resume_bullets: List[str]) -> ClaimExtractionResult:
    """Extract discrete factual claims from a generated resume."""
    resume_text = f"SUMMARY: {resume_summary}\n\nBULLETS:\n" + "\n".join(f"- {b}" for b in resume_bullets)
    
    prompt = f"""Extract every distinct, verifiable factual claim from this resume text. 
Focus on technical skills, tools, responsibilities, and metrics. 
Do not extract subjective opinions (e.g., "passionate about clean code").

RESUME TEXT:
{resume_text}

Return ONLY valid JSON matching this schema:
{{
  "claims": [
    {{"claim_text": "string", "claim_type": "string"}}
  ]
}}
"""
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
            
            data = json.loads(content)
            return ClaimExtractionResult(**data)
        except Exception as e:
            err_str = str(e)
            if ("429" in err_str or "rate_limit" in err_str.lower()) and attempt < 3:
                wait_s = (attempt + 1) * 3
                logger.warning(f"Rate limited during claim extraction. Retrying in {wait_s}s...")
                import time
                time.sleep(wait_s)
                continue
            logger.error(f"Claim extraction failed: {e}")
            raise ValueError(f"Failed to extract claims: {e}")