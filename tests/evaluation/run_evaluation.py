import json
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add the project root to the path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.claim_verifier import verify_claim
from app.services.evidence_gate import run_deterministic_evidence_gate
from pydantic import BaseModel

class MockDBSession:
    """A mock database session for evaluation testing."""
    def __init__(self, mock_skills: List[Dict[str, Any]], mock_projects: List[Dict[str, Any]]):
        self.mock_skills = mock_skills
        self.mock_projects = mock_projects

    def query(self, model):
        return MockQuery(self.mock_skills, self.mock_projects, model)

class MockQuery:
    def __init__(self, skills, projects, model):
        self.skills = skills
        self.projects = projects
        self.model = model

    def filter(self, *args):
        # Simplified mock filter for evaluation
        return self

    def first(self):
        # In a real evaluation, we would parse the filter args. 
        # For this MVP evaluator, we will bypass the DB query in the gate 
        # by modifying the gate to accept a mock, or we just test the LLM verifier directly 
        # and assume the gate passes if the LLM cites a valid mock ID.
        return None

# To keep the evaluation script simple and focused on the LLM + Gate logic, 
# we will create a simplified evaluation gate that checks against our mock data directly.

def evaluate_mock_gate(llm_verdict: str, cited_ids: List[str], mock_evidence: List[Dict]) -> Dict[str, Any]:
    """Simplified deterministic gate for evaluation without a real DB."""
    if llm_verdict in ["SUPPORTED", "PARTIAL"] and cited_ids:
        for eid in cited_ids:
            # Check if ID exists in mock evidence
            valid = any(str(e['id']) == str(eid) for e in mock_evidence)
            if not valid:
                return {
                    "final_verdict": "UNSUPPORTED",
                    "gate_passed": False,
                    "gate_reason": f"Mock Gate rejected: Evidence ID {eid} not found."
                }
    
    if llm_verdict == "UNSUPPORTED":
        return {
            "final_verdict": "UNSUPPORTED",
            "gate_passed": False,
            "gate_reason": "Claim lacks supporting evidence."
        }

    return {
        "final_verdict": llm_verdict,
        "gate_passed": True,
        "gate_reason": "Mock LLM verdict accepted."
    }


def run_evaluation():
    # 1. Load test cases
    cases_path = Path(__file__).parent / "claim_cases.json"
    with open(cases_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    test_cases = data["test_cases"]
    print(f"Loaded {len(test_cases)} evaluation cases.\n")

    # 2. Metrics tracking
    metrics = {
        "total": len(test_cases),
        "correct": 0,
        "false_positives": 0, # System said SUPPORTED/PARTIAL, but expected UNSUPPORTED
        "false_negatives": 0, # System said UNSUPPORTED, but expected SUPPORTED
        "true_positives": 0,  # System said SUPPORTED, expected SUPPORTED
        "true_negatives": 0,  # System said UNSUPPORTED, expected UNSUPPORTED
    }

    results = []

    # 3. Run evaluation
    for case in test_cases:
        print(f"Testing {case['id']} ({case['category']})...", end=" ")
        
        # Format mock evidence
        mock_evidence = [{
            "id": "E1",
            "type": "Evidence",
            "text": case["evidence"]
        }] if case["evidence"] else []

        try:
            # Run LLM Verifier
            llm_result = verify_claim(case["claim"], mock_evidence)
            
            # Run Mock Deterministic Gate
            gate_result = evaluate_mock_gate(
                llm_verdict=llm_result.verdict,
                cited_ids=llm_result.supported_by,
                mock_evidence=mock_evidence
            )
            
            final_verdict = gate_result["final_verdict"]
            expected = case["expected_verdict"]

            # Calculate Metrics
            is_correct = (final_verdict == expected)
            if is_correct:
                metrics["correct"] += 1
                if expected == "SUPPORTED":
                    metrics["true_positives"] += 1
                elif expected == "UNSUPPORTED":
                    metrics["true_negatives"] += 1
            else:
                if final_verdict in ["SUPPORTED", "PARTIAL"] and expected == "UNSUPPORTED":
                    metrics["false_positives"] += 1
                elif final_verdict == "UNSUPPORTED" and expected in ["SUPPORTED", "PARTIAL"]:
                    metrics["false_negatives"] += 1

            results.append({
                "id": case["id"],
                "category": case["category"],
                "expected": expected,
                "actual": final_verdict,
                "correct": is_correct,
                "reason": gate_result["gate_reason"]
            })
            
            status = "PASS" if is_correct else "FAIL"
            print(f"{status} (Expected: {expected}, Got: {final_verdict})")

        except Exception as e:
            print(f"ERROR: {e}")
            metrics["false_negatives"] += 1 # Count as failure

    # 4. Calculate Final Metrics
    total_predicted_positive = metrics["true_positives"] + metrics["false_positives"]
    total_actual_positive = metrics["true_positives"] + metrics["false_negatives"]
    total_actual_negative = metrics["true_negatives"] + metrics["false_positives"]

    accuracy = (metrics["correct"] / metrics["total"]) * 100 if metrics["total"] > 0 else 0
    precision = (metrics["true_positives"] / total_predicted_positive) * 100 if total_predicted_positive > 0 else 0
    recall = (metrics["true_positives"] / total_actual_positive) * 100 if total_actual_positive > 0 else 0
    fpr = (metrics["false_positives"] / total_actual_negative) * 100 if total_actual_negative > 0 else 0
    fnr = (metrics["false_negatives"] / total_actual_positive) * 100 if total_actual_positive > 0 else 0

    # 5. Print Report
    print("\n" + "="*60)
    print(" EVALUATION REPORT: CLAIM VERIFIER + DETERMINISTIC GATE")
    print("="*60)
    print(f"Total Cases Evaluated:     {metrics['total']}")
    print(f"Correct Predictions:       {metrics['correct']}")
    print("-" * 60)
    print(f"Accuracy:                  {accuracy:.2f}%")
    print(f"Precision (of Supported):  {precision:.2f}%")
    print(f"Recall (of Supported):     {recall:.2f}%")
    print(f"False Positive Rate (FPR): {fpr:.2f}%  <-- CRITICAL METRIC")
    print(f"False Negative Rate (FNR): {fnr:.2f}%")
    print("="*60)
    
    # Print failures for debugging
    failures = [r for r in results if not r["correct"]]
    if failures:
        print("\n FAILED CASES (Requires Prompt/Gate Tuning):")
        for f in failures:
            print(f"  - {f['id']} ({f['category']}): Expected {f['expected']}, Got {f['actual']}")
            print(f"    Reason: {f['reason']}")
    else:
        print("\nALL TEST CASES PASSED. ZERO FALSE POSITIVES.")

if __name__ == "__main__":
    run_evaluation()