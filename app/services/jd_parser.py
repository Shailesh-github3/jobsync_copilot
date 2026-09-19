import json
import logging
import os
import re
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

from app.schemas.jd import ParsedJobDescription

logger = logging.getLogger(__name__)


class JDParseError(Exception):
    """Raised when JD parsing fails."""
    pass


def get_llm_client() -> tuple[OpenAI, str]:
    """Get LLM client configured for Groq or OpenAI.

    Returns:
        tuple[OpenAI, str]: (client_instance, model_name)
    """
    groq_api_key = (
        os.getenv("GROQ_API_KEY")
        or os.getenv("GROQ_KEY")
        or os.getenv("GROQ_APIKEY")
        or os.getenv("GROQ")
    )
    openai_api_key = os.getenv("OPENAI_API_KEY")

    api_key = groq_api_key or openai_api_key
    if not api_key:
        raise JDParseError("LLM API key not configured")

    # Auto-detect Groq: Groq keys start with 'gsk_' or when GROQ_API_KEY is provided
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


def parse_job_description(raw_description: str, max_retries: int = 1) -> ParsedJobDescription:
    """Parse a raw job description using structured LLM output.

    Args:
        raw_description: The raw job description text.
        max_retries: Number of retry attempts if validation fails.

    Returns:
        ParsedJobDescription: Structured job data.

    Raises:
        JDParseError: If parsing fails after all retries.
    """
    prompt = f"""Extract structured information from this job description.

Return a JSON object with these fields:
- role: The job title/role (string)
- required_skills: List of required skills (array of strings)
- preferred_skills: List of preferred/nice-to-have skills (array of strings)
- min_experience: Minimum years of experience required (integer or null)

Job Description:
{raw_description}

Return ONLY valid JSON. No markdown, no explanations."""

    client, model = get_llm_client()

    for attempt in range(max_retries + 1):
        try:
            # Call LLM with structured JSON output
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a job description parser. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )

            # Parse the JSON response with markdown strip
            content = response.choices[0].message.content or ""
            # Strip markdown code blocks if present (e.g., ```json ... ```)
            content = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.MULTILINE)
            content = re.sub(r"\s*```$", "", content.strip(), flags=re.MULTILINE)
            data = json.loads(content.strip())

            # Validate against Pydantic schema
            parsed = ParsedJobDescription(**data)
            logger.info(f"Successfully parsed JD using {model} on attempt {attempt + 1}")
            return parsed

        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning(f"Validation failed on attempt {attempt + 1}: {e}")
            if attempt == max_retries:
                raise JDParseError(f"Failed to parse JD after {max_retries + 1} attempts: {e}")
            prompt = f"""{prompt}

IMPORTANT: Return ONLY valid JSON. Ensure all required fields are present."""

        except Exception as e:
            logger.error(f"LLM API error ({model}): {e}")
            raise JDParseError(f"LLM API error ({model}): {e}")

    raise JDParseError("Failed to parse JD")