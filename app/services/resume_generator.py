import json
import logging
import os
import re
from typing import List

from openai import OpenAI
from pydantic import ValidationError

from app.schemas.resume import GeneratedResume

logger = logging.getLogger(__name__)


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
        raise ResumeGenerationError("LLM API key (GROQ_API_KEY or OPENAI_API_KEY) not configured.")

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


class ResumeGenerationError(Exception):
    """Raised when resume generation fails."""
    pass


def generate_tailored_resume(
    candidate_name: str,
    verified_skills: List[str],
    verified_experience: List[str],  # e.g., project descriptions
    job_role: str,
    job_required_skills: List[str],
    job_preferred_skills: List[str],
    excluded_claims: List[str] = None,
    max_retries: int = 1,
) -> GeneratedResume:
    """Generate a tailored resume strictly from verified candidate data.

    Args:
        candidate_name: Name of the candidate.
        verified_skills: List of candidate's VERIFIED skills.
        verified_experience: List of candidate's verified project/experience descriptions.
        job_role: The target job title.
        job_required_skills: Skills required by the job.
        job_preferred_skills: Skills preferred by the job.
        excluded_claims: List of previously rejected claims to exclude.
        max_retries: Number of retry attempts if validation fails.

    Returns:
        GeneratedResume: Structured resume data.
    """
    # CRITICAL: We only provide VERIFIED data to the LLM.
    candidate_context = f"""
CANDIDATE NAME: {candidate_name}

VERIFIED SKILLS:
{', '.join(verified_skills) if verified_skills else 'None'}

VERIFIED EXPERIENCE / PROJECTS:
{chr(10).join(f'- {exp}' for exp in verified_experience) if verified_experience else 'None'}
"""

    job_context = f"""
TARGET ROLE: {job_role}

REQUIRED SKILLS: {', '.join(job_required_skills) if job_required_skills else 'None'}
PREFERRED SKILLS: {', '.join(job_preferred_skills) if job_preferred_skills else 'None'}
"""

    exclusion_context = ""
    if excluded_claims:
        exclusion_list = "\n".join(f"- {claim}" for claim in excluded_claims)
        exclusion_context = f"""
STRICT NEGATIVE CONSTRAINTS:
The following claims were previously generated but REJECTED due to lack of verified evidence. 
You MUST NOT include these concepts, phrases, or implications in this new version:
{exclusion_list}
"""

    prompt = f"""You are an expert resume writer. Your task is to rewrite and reorder the candidate's VERIFIED experience to strongly align with the TARGET ROLE.

STRICT RULES:
1. You may ONLY use the information provided in the CANDIDATE CONTEXT.
2. You may reorder, summarize, or rephrase the verified experience to emphasize relevance to the job.
3. You MUST NOT invent, assume, or hallucinate any skills, projects, companies, responsibilities, metrics, or years of experience.
4. Do NOT include vague corporate buzzwords, generic fluff, or ungrounded claims (e.g. 'delivering robust solutions', 'optimizing performance', 'leading teams') unless directly backed by the CANDIDATE CONTEXT.
5. If the candidate lacks a required skill, do not mention it. Do not claim they have it.
{exclusion_context}
6. Return ONLY a valid JSON object matching these exact fields:
   - "tailored_summary": A 2-3 sentence professional summary tailored to the target role (string, minimum 50 characters).
   - "tailored_bullets": 3 to 5 bullet points highlighting relevant verified experience/projects (array of 3 to 5 strings).
   - "relevant_skills": List of candidate's verified skills relevant to the job (array of strings).

{candidate_context}
{job_context}

Return ONLY valid JSON. No markdown, no explanations."""

    client, model = get_llm_client()

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a strict resume generator. Return only valid JSON adhering strictly to the requested schema keys."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,  # Low temperature for deterministic, constrained output
            )

            content = response.choices[0].message.content or ""
            
            # Strip markdown code blocks (Groq often adds these)
            content = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.MULTILINE)
            content = re.sub(r"\s*```$", "", content.strip(), flags=re.MULTILINE)
            
            data = json.loads(content.strip())
            
            # Validate against Pydantic schema
            parsed_resume = GeneratedResume(**data)
            logger.info(f"Successfully generated resume on attempt {attempt + 1}")
            return parsed_resume

        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning(f"Resume validation failed on attempt {attempt + 1}: {e}")
            if attempt == max_retries:
                raise ResumeGenerationError(f"Failed to generate valid resume JSON after {max_retries + 1} attempts: {e}")
            prompt = f"""{prompt}

IMPORTANT: Ensure the JSON has "tailored_summary" (>= 50 chars), "tailored_bullets" (3-5 items), and "relevant_skills" (list). Error: {e}"""
            
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower():
                logger.warning("Rate limited during resume generation. Retrying in 4s...")
                import time
                time.sleep(4)
                continue
            logger.error(f"LLM API error during resume generation: {e}")
            raise ResumeGenerationError(f"LLM API error: {e}")

    raise ResumeGenerationError("Failed to generate resume")