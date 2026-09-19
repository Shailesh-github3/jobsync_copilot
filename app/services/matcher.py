import json
import logging
from typing import List, Tuple

from app.services.normalizer import normalize_skills

logger = logging.getLogger(__name__)


class MatchResult:
    """Result of matching a candidate against a job."""
    
    def __init__(
        self,
        score: float,
        matched_required: List[str],
        missing_required: List[str],
        matched_preferred: List[str],
        missing_preferred: List[str],
        explanation: str,
    ):
        self.score = score
        self.matched_required = matched_required
        self.missing_required = missing_required
        self.matched_preferred = matched_preferred
        self.missing_preferred = missing_preferred
        self.explanation = explanation

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "matched_required": self.matched_required,
            "missing_required": self.missing_required,
            "matched_preferred": self.matched_preferred,
            "missing_preferred": self.missing_preferred,
            "explanation": self.explanation,
        }


def match_candidate_to_job(
    candidate_skills: List[str],
    required_skills: List[str],
    preferred_skills: List[str],
) -> MatchResult:
    """Match a candidate's skills against job requirements.

    Args:
        candidate_skills: List of candidate's verified skill names.
        required_skills: List of required skills from parsed JD.
        preferred_skills: List of preferred skills from parsed JD.

    Returns:
        MatchResult with score and explanation.
    """
    # Normalize all skill sets
    norm_candidate = set(normalize_skills(candidate_skills))
    norm_required = set(normalize_skills(required_skills))
    norm_preferred = set(normalize_skills(preferred_skills))

    # Calculate intersections
    matched_required = norm_candidate & norm_required
    missing_required = norm_required - norm_candidate
    matched_preferred = norm_candidate & norm_preferred
    missing_preferred = norm_preferred - norm_candidate

    # Calculate score
    required_score = 0.0
    if norm_required:
        required_score = len(matched_required) / len(norm_required)

    preferred_score = 0.0
    if norm_preferred:
        preferred_score = len(matched_preferred) / len(norm_preferred)

    # Weighted score: 70% required, 30% preferred
    final_score = (required_score * 70) + (preferred_score * 30)

    # Generate explanation
    explanation = _generate_explanation(
        final_score,
        matched_required,
        missing_required,
        matched_preferred,
        missing_preferred,
    )

    return MatchResult(
        score=round(final_score, 1),
        matched_required=sorted(matched_required),
        missing_required=sorted(missing_required),
        matched_preferred=sorted(matched_preferred),
        missing_preferred=sorted(missing_preferred),
        explanation=explanation,
    )


def _generate_explanation(
    score: float,
    matched_required: set,
    missing_required: set,
    matched_preferred: set,
    missing_preferred: set,
) -> str:
    """Generate human-readable explanation of the match."""
    lines = [f"Score: {score}/100", ""]

    if matched_required:
        lines.append("Matched Required:")
        for skill in sorted(matched_required):
            lines.append(f"  ✓ {skill}")
        lines.append("")

    if missing_required:
        lines.append("Missing Required:")
        for skill in sorted(missing_required):
            lines.append(f"  ✗ {skill}")
        lines.append("")

    if matched_preferred:
        lines.append("Matched Preferred:")
        for skill in sorted(matched_preferred):
            lines.append(f"  ✓ {skill}")
        lines.append("")

    if missing_preferred:
        lines.append("Missing Preferred:")
        for skill in sorted(missing_preferred):
            lines.append(f"  ✗ {skill}")
        lines.append("")

    # Summary
    if score >= 80:
        lines.append("Strong match. Candidate meets most requirements.")
    elif score >= 60:
        lines.append("Good match. Candidate meets key requirements but has gaps.")
    elif score >= 40:
        lines.append("Moderate match. Candidate meets some requirements.")
    else:
        lines.append("Weak match. Candidate does not meet most requirements.")

    return "\n".join(lines)
