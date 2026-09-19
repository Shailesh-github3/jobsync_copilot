import re
from typing import Dict


# Alias dictionary: maps variations to canonical names
# Add more aliases as needed
SKILL_ALIASES: Dict[str, str] = {
    # JavaScript frameworks
    "react.js": "react",
    "reactjs": "react",
    "react js": "react",
    
    "vue.js": "vue",
    "vuejs": "vue",
    
    "angular.js": "angular",
    "angularjs": "angular",
    
    "typescript": "typescript",
    
    # Backend frameworks
    "springboot": "spring boot",
    "spring-boot": "spring boot",
    "spring boot framework": "spring boot",
    
    "node.js": "nodejs",
    "node js": "nodejs",
    "node-js": "nodejs",
    
    "express.js": "express",
    "expressjs": "express",
    
    "django rest framework": "django rest framework",
    "drf": "django rest framework",
    
    "rest api": "rest apis",
    
    "machine learning": "ml",

    # Databases
    "postgres": "postgresql",
    "postgre": "postgresql",
    "postgre sql": "postgresql",
    
    "mongo": "mongodb",
    "mongo db": "mongodb",
    
    "mysql db": "mysql",
    
    # Cloud
    "aws ec2": "aws",
    "aws s3": "aws",
    "amazon web services": "aws",
    
    "gcp": "google cloud",
    "google cloud platform": "google cloud",
    
    "azure cloud": "azure",
    "microsoft azure": "azure",
    
    # DevOps
    "k8s": "kubernetes",
    "kube": "kubernetes",
    
    "ci/cd": "ci cd",
    "ci-cd": "ci cd",
    "continuous integration": "ci cd",
    "continuous deployment": "ci cd",
    
    # Version control
    "git hub": "github",
    "git-hub": "github",
    
    "git lab": "gitlab",
    "git-lab": "gitlab",
    
    # Programming languages
    "c++": "cpp",
    "c#": "csharp",
    "c sharp": "csharp",
    
    # Testing
    "unit testing": "unit tests",
    "integration testing": "integration tests",
}


def normalize_skill(skill: str) -> str:
    """Normalize a skill name to its canonical form.

    Steps:
    1. Convert to lowercase
    2. Strip leading/trailing whitespace
    3. Replace multiple spaces with single space
    4. Remove common punctuation (periods, hyphens in some cases)
    5. Look up in alias dictionary
    6. Return canonical name

    Args:
        skill: The skill name to normalize.

    Returns:
        The normalized skill name.

    Examples:
        >>> normalize_skill("  SpringBoot  ")
        'spring boot'
        >>> normalize_skill("React.js")
        'react'
        >>> normalize_skill("PostgreSQL")
        'postgresql'
    """
    if not skill or not skill.strip():
        return ""

    # Step 1: Lowercase
    normalized = skill.lower()

    # Step 2: Strip whitespace
    normalized = normalized.strip()

    # Step 3: Replace multiple spaces with single space
    normalized = re.sub(r"\s+", " ", normalized)

    # Step 4: Remove periods (e.g., "React.js" → "reactjs")
    normalized = normalized.replace(".", "")

    # Step 5: Look up in alias dictionary
    if normalized in SKILL_ALIASES:
        normalized = SKILL_ALIASES[normalized]

    return normalized


def normalize_skills(skills: list[str]) -> list[str]:
    """Normalize a list of skill names.

    Args:
        skills: List of skill names.

    Returns:
        List of normalized skill names (duplicates removed, order preserved).

    Examples:
        >>> normalize_skills(["Java", "java", "JAVA"])
        ['java']
        >>> normalize_skills(["Spring Boot", "springboot"])
        ['spring boot']
    """
    normalized = []
    seen = set()

    for skill in skills:
        norm = normalize_skill(skill)
        if norm and norm not in seen:
            normalized.append(norm)
            seen.add(norm)

    return normalized