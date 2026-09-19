import json
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field


class EvaluationCase(BaseModel):
    """Schema for a single evaluation case."""
    id: str = Field(..., pattern=r"^TC\d{3}$")
    category: str
    evidence: str
    claim: str
    expected_verdict: str
    notes: str


class EvaluationSuite(BaseModel):
    """Schema for the entire evaluation JSON file."""
    version: str
    description: str
    test_cases: List[EvaluationCase]


def load_evaluation_cases(file_path: str | Path = None) -> EvaluationSuite:
    """Load and validate evaluation cases from JSON.

    Args:
        file_path: Path to the JSON file. Defaults to tests/evaluation/claim_cases.json.

    Returns:
        EvaluationSuite: Validated test cases.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the JSON is malformed or fails validation.
    """
    if file_path is None:
        # Default path: tests/evaluation/claim_cases.json relative to project root
        file_path = Path(__file__).parent.parent.parent / "tests" / "evaluation" / "claim_cases.json"

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Evaluation file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Validate against Pydantic schema
    try:
        suite = EvaluationSuite(**data)
    except Exception as e:
        raise ValueError(f"Invalid evaluation file: {e}")

    return suite


def get_case_categories(suite: EvaluationSuite) -> dict[str, int]:
    """Count cases by category."""
    categories: dict[str, int] = {}
    for case in suite.test_cases:
        categories[case.category] = categories.get(case.category, 0) + 1
    return categories