import pytest

from app.services.normalizer import normalize_skill, normalize_skills


class TestNormalizeSkill:
    """Unit tests for the normalize_skill function."""

    def test_lowercase(self):
        assert normalize_skill("Java") == "java"
        assert normalize_skill("SPRING BOOT") == "spring boot"

    def test_strip_whitespace(self):
        assert normalize_skill("  Python  ") == "python"
        assert normalize_skill("\tDocker\n") == "docker"

    def test_multiple_spaces(self):
        assert normalize_skill("Spring   Boot") == "spring boot"
        assert normalize_skill("Node   JS") == "nodejs"

    def test_remove_periods(self):
        assert normalize_skill("React.js") == "react"
        assert normalize_skill("Node.js") == "nodejs"
        assert normalize_skill("Express.js") == "express"

    def test_alias_lookup(self):
        assert normalize_skill("SpringBoot") == "spring boot"
        assert normalize_skill("spring-boot") == "spring boot"
        assert normalize_skill("Postgres") == "postgresql"
        assert normalize_skill("K8s") == "kubernetes"
        assert normalize_skill("C++") == "cpp"

    def test_empty_string(self):
        assert normalize_skill("") == ""
        assert normalize_skill("   ") == ""

    def test_no_alias(self):
        # Skills without aliases should just be lowercased
        assert normalize_skill("FastAPI") == "fastapi"
        assert normalize_skill("SQLAlchemy") == "sqlalchemy"


class TestNormalizeSkills:
    """Unit tests for the normalize_skills function."""

    def test_remove_duplicates(self):
        result = normalize_skills(["Java", "java", "JAVA"])
        assert result == ["java"]

    def test_normalize_and_deduplicate(self):
        result = normalize_skills(["Spring Boot", "springboot", "SpringBoot"])
        assert result == ["spring boot"]

    def test_preserve_order(self):
        result = normalize_skills(["Python", "Java", "Docker"])
        assert result == ["python", "java", "docker"]

    def test_empty_list(self):
        assert normalize_skills([]) == []

    def test_filter_empty_strings(self):
        result = normalize_skills(["Java", "", "  ", "Python"])
        assert result == ["java", "python"]

    def test_mixed_aliases(self):
        result = normalize_skills(["React.js", "reactjs", "REACT"])
        assert result == ["react"]