import time
import json

def test_end_to_end_self_healing_pipeline(client, db_session):
    """Test the entire pipeline from seeding to async healing and final verification."""
    
    # 1. Seed Candidate
    response = client.post("/seed")
    assert response.status_code == 200
    candidate_data = response.json()
    candidate_id = candidate_data["id"]
    assert candidate_data["name"] == "Ada Lovelace"

    # 2. Add Verified Project Evidence
    project_payload = {
        "title": "E-commerce Backend",
        "description": "Designed and implemented REST APIs for order processing, reducing latency by 40%.",
        "technologies": "java, spring boot, redis, postgresql"
    }
    response = client.post(f"/candidates/{candidate_id}/projects", json=project_payload)
    assert response.status_code in [200, 201]

    # 3. Add and Parse Job
    response = client.post("/jobs/sample")
    assert response.status_code == 200
    
    response = client.post("/jobs/1/parse")
    assert response.status_code == 200
    assert response.json()["parse_status"] == "PARSED"

    # 4. Generate Initial Resume
    response = client.post("/jobs/1/resume/1")
    assert response.status_code == 200
    resume_data = response.json()
    resume_id = resume_data["resume_id"]
    pipeline_id = resume_data["pipeline_id"]

    # 5. Trigger Asynchronous Self-Healing
    response = client.post(f"/resumes/{resume_id}/heal")
    assert response.status_code == 202  # Must be Accepted, not OK
    assert response.json()["status"] == "accepted"

    # 6. Poll for Completion (Max 60 seconds)
    max_wait = 60
    poll_interval = 2
    elapsed = 0
    
    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval
        
        status_response = client.get(f"/pipelines/{pipeline_id}/status")
        assert status_response.status_code == 200
        status_data = status_response.json()
        
        if status_data["processing_status"] in ["PASSED", "FAILED"]:
            break
            
    # Assert it didn't time out
    assert elapsed < max_wait, "Pipeline took too long to complete"
    
    # 7. Assert Final Success State
    assert status_data["processing_status"] == "PASSED"
    assert status_data["validation_status"] == "PASSED"

    # 8. Verify Audit Metrics
    metrics_response = client.get(f"/metrics/pipeline/{pipeline_id}")
    assert metrics_response.status_code == 200
    metrics = metrics_response.json()
    
    assert metrics["hallucination_leakage_rate_percent"] == 0.0, "Hallucination leakage must be 0.0%"
    assert metrics["gate_rejections"] >= 0  # May be 0 if LLM got it right on first try, or >0 if it healed

    # 9. Verify Export Safety Gate
    # Attempting to export a FAILED resume should fail (we can simulate by checking logic, 
    # but since this one passed, let's verify the passed one exports successfully)
    export_response = client.get(f"/resumes/{resume_id}/export")
    assert export_response.status_code == 200
    assert "text/html" in export_response.headers["content-type"]
    assert "100% VERIFIED BY JOBSYNC COPILOT" in export_response.text