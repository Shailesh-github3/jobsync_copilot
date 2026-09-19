import ipaddress
import logging
import socket
from typing import List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """Raised when scraping fails."""
    pass


def is_safe_url(url: str) -> bool:
    """Validate that the URL is public and uses http/https."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        ip_str = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(ip_str)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
        return True
    except Exception:
        return False


class JobSourceStrategy:
    """Interface for job sources. Swap implementations without changing callers."""
    def fetch_jobs(self) -> List[dict]:
        raise NotImplementedError


class HttpScraper(JobSourceStrategy):
    """Requests + BeautifulSoup. Fast, cheap, fragile."""
    def __init__(self, url: str):
        self.url = url

    def fetch_jobs(self) -> List[dict]:
        if not is_safe_url(self.url):
            raise ScraperError(f"Invalid or restricted URL: {self.url}")

        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError as e:
            raise ScraperError(f"Scraping library missing: {e}. Install requests and beautifulsoup4.")

        try:
            response = requests.get(self.url, timeout=10, stream=True)
            response.raise_for_status()
            max_bytes = 5 * 1024 * 1024  # 5MB limit
            content = b""
            for chunk in response.iter_content(chunk_size=8192):
                content += chunk
                if len(content) > max_bytes:
                    raise ScraperError("Response payload exceeds 5MB limit")
            html_text = content.decode(response.encoding or "utf-8", errors="replace")
        except Exception as e:
            logger.error(f"HTTP error scraping {self.url}: {e}")
            raise ScraperError(f"Failed to fetch {self.url}: {e}")

        try:
            soup = BeautifulSoup(html_text, "html.parser")
            job_elements = soup.find_all("div", class_="job-posting")

            jobs = []
            for element in job_elements:
                title_tag = element.find("h2", class_="job-title")
                company_tag = element.find("span", class_="company")
                desc_tag = element.find("div", class_="description")

                title = title_tag.get_text(strip=True) if title_tag else None
                company = company_tag.get_text(strip=True) if company_tag else None
                description = desc_tag.get_text(strip=True) if desc_tag else ""

                if description:
                    jobs.append({
                        "title": title,
                        "company": company,
                        "raw_description": description,
                        "source_url": self.url,
                    })

            logger.info(f"Scraped {len(jobs)} jobs from {self.url}")
            return jobs

        except Exception as e:
            logger.error(f"Parsing error for {self.url}: {e}")
            raise ScraperError(f"Failed to parse {self.url}: {e}")


class SampleSource(JobSourceStrategy):
    """Hardcoded sample data. Reliable fallback for demos."""
    def fetch_jobs(self) -> List[dict]:
        return [
            {
                "title": "Backend Engineer",
                "company": "TechCorp",
                "raw_description": (
                    "We are looking for a Backend Engineer with experience in Java, "
                    "Spring Boot, and PostgreSQL. You will build REST APIs and microservices. "
                    "Docker and Kubernetes experience is a plus. Minimum 2 years experience."
                ),
                "source_url": "sample://backend-engineer-001",
            },
            {
                "title": "Full Stack Developer",
                "company": "StartupXYZ",
                "raw_description": (
                    "Join our team as a Full Stack Developer. Required skills: React, Node.js, "
                    "PostgreSQL. Experience with AWS and CI/CD pipelines is preferred. "
                    "You will work on customer-facing applications."
                ),
                "source_url": "sample://fullstack-dev-002",
            },
        ]


# Keep backward-compatible functions for existing endpoints
def scrape_jobs_from_url(url: str) -> List[dict]:
    scraper = HttpScraper(url)
    return scraper.fetch_jobs()


def scrape_sample_jobs() -> List[dict]:
    source = SampleSource()
    return source.fetch_jobs()