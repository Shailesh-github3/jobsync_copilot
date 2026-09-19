import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.main import app
from app.db.database import Base, get_db
import app.db.database as db_module
import app.services.background_tasks as bg_module

# Use an in-memory SQLite database with StaticPool for isolated testing
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(autouse=True)
def mock_llm_services(monkeypatch):
    """Hermetic mocks for LLM and external API calls so tests run reliably in CI."""
    from app.schemas.jd import ParsedJobDescription
    from app.schemas.resume import GeneratedResume
    from app.services.claim_extractor import ClaimExtractionResult, ExtractedClaim
    from app.services.claim_verifier import ClaimVerificationResult

    def fake_parse_jd(raw_description: str):
        return ParsedJobDescription(
            role="Senior Java Backend Engineer",
            required_skills=["java", "spring boot"],
            preferred_skills=["postgresql", "redis"],
            min_experience=3,
        )

    def fake_generate_resume(
        candidate_name,
        verified_skills,
        verified_experience,
        job_role,
        job_required_skills,
        job_preferred_skills,
        excluded_claims=None,
    ):
        return GeneratedResume(
            tailored_summary="Experienced Java Backend Engineer specializing in Spring Boot, PostgreSQL, and scalable microservices architectures.",
            tailored_bullets=[
                "Designed and implemented high-throughput REST APIs using Java and Spring Boot.",
                "Optimized database indexing and query performance for PostgreSQL transactions.",
                "Architected distributed caching and session management using Redis.",
            ],
            relevant_skills=["Java", "Spring Boot", "PostgreSQL", "Redis"],
        )

    def fake_extract_claims(summary: str, bullets: list):
        return ClaimExtractionResult(
            claims=[
                ExtractedClaim(
                    claim_text="Designed and implemented high-throughput REST APIs using Java and Spring Boot.",
                    claim_type="technical_skill",
                ),
                ExtractedClaim(
                    claim_text="Optimized database indexing and query performance for PostgreSQL transactions.",
                    claim_type="technical_skill",
                ),
            ]
        )

    def fake_verify_claim(claim_text: str, verified_evidence: list):
        evidence_ids = [str(item["id"]) for item in verified_evidence if item.get("type") in ("Skill", "Project")]
        return ClaimVerificationResult(
            claim_text=claim_text,
            verdict="SUPPORTED",
            supported_by=evidence_ids[:2] if evidence_ids else ["1"],
            reason="Verified against candidate skill and project database records.",
        )

    def fake_send_telegram(resume_id, pipeline_id, job_title, score, explanation):
        return True

    # Patch LLM & external service calls across main and service modules
    monkeypatch.setattr("app.main.parse_job_description", fake_parse_jd)
    monkeypatch.setattr("app.services.jd_parser.parse_job_description", fake_parse_jd)

    monkeypatch.setattr("app.main.generate_tailored_resume", fake_generate_resume)
    monkeypatch.setattr("app.services.resume_generator.generate_tailored_resume", fake_generate_resume)
    monkeypatch.setattr("app.services.background_tasks.generate_tailored_resume", fake_generate_resume)

    monkeypatch.setattr("app.main.extract_claims", fake_extract_claims)
    monkeypatch.setattr("app.services.claim_extractor.extract_claims", fake_extract_claims)
    monkeypatch.setattr("app.services.background_tasks.extract_claims", fake_extract_claims)

    monkeypatch.setattr("app.main.verify_claim", fake_verify_claim)
    monkeypatch.setattr("app.services.claim_verifier.verify_claim", fake_verify_claim)
    monkeypatch.setattr("app.services.background_tasks.verify_claim", fake_verify_claim)

    monkeypatch.setattr("app.main.send_telegram_notification", fake_send_telegram)
    monkeypatch.setattr("app.services.telegram_service.send_telegram_notification", fake_send_telegram)


@pytest.fixture(scope="function")
def client(db_session, monkeypatch):
    """Override get_db and background task SessionLocal to use the isolated test database."""
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(db_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(bg_module, "SessionLocal", TestingSessionLocal)

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()