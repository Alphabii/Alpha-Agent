from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def make_job_id(platform: str, external_id: str) -> str:
    """Generate a deterministic ID from platform + external_id."""
    return hashlib.sha256(f"{platform}:{external_id}".encode()).hexdigest()[:16]


class ScrapedJob(BaseModel):
    """Raw job data coming from a scraper."""

    platform: str
    external_id: str
    title: str
    company: str = ""
    description: str = ""
    location: str = ""
    remote: bool = False
    daily_rate_min: int = 0
    daily_rate_max: int = 0
    skills: list[str] = []
    url: str
    language: str = "fr"
    posted_at: str = ""
    contract_type: str = ""
    duration: str = ""

    @property
    def job_id(self) -> str:
        return make_job_id(self.platform, self.external_id)


class JobRecord(BaseModel):
    """Job stored in the database."""

    id: str
    platform: str
    external_id: str
    title: str
    company: str = ""
    description: str = ""
    location: str = ""
    remote: bool = False
    daily_rate_min: int = 0
    daily_rate_max: int = 0
    skills: list[str] = []
    url: str
    language: str = "fr"
    posted_at: str = ""
    discovered_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    relevance_score: int = 0
    relevance_reason: str = ""
    status: str = "new"  # new, applied, skipped, failed
    contract_type: str = ""
    duration: str = ""

    @classmethod
    def from_scraped(cls, job: ScrapedJob) -> JobRecord:
        return cls(
            id=job.job_id,
            platform=job.platform,
            external_id=job.external_id,
            title=job.title,
            company=job.company,
            description=job.description,
            location=job.location,
            remote=job.remote,
            daily_rate_min=job.daily_rate_min,
            daily_rate_max=job.daily_rate_max,
            skills=job.skills,
            url=job.url,
            language=job.language,
            posted_at=job.posted_at,
            contract_type=job.contract_type,
            duration=job.duration,
        )


class ApplicationRecord(BaseModel):
    """Application stored in the database."""

    id: int | None = None
    job_id: str
    cover_letter: str = ""
    proposal_message: str = ""
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    submitted_at: str = ""
    submission_status: str = "draft"  # draft, submitted, failed
    error_message: str = ""


class RelevanceResult(BaseModel):
    """Result from AI relevance analysis."""

    score: int = 0
    reasoning: str = ""
    matching_skills: list[str] = []
    concerns: list[str] = []


class ScanStats(BaseModel):
    """Summary stats for status command."""

    total_jobs: int = 0
    new_jobs: int = 0
    applied_jobs: int = 0
    skipped_jobs: int = 0
    failed_jobs: int = 0
    total_applications: int = 0
    submitted_applications: int = 0
