from datetime import datetime, timezone

from loguru import logger

from src.ai.analyzer import JobAnalyzer
from src.ai.generator import ApplicationGenerator
from src.config import settings
from src.db import (
    get_application_for_job,
    get_jobs,
    log_scan_finish,
    log_scan_start,
    save_application,
    save_job,
    update_application_status,
    update_job_relevance,
    update_job_status,
)
from src.models import ApplicationRecord, JobRecord
from src.registry import SCRAPERS, APPLICATORS
from src.scrapers.base import PlatformScraper
from src.sheets import track_application, track_job_found


def _get_enabled_scrapers(platforms: list[str] | None = None) -> list[PlatformScraper]:
    """Instantiate scrapers for the requested platforms."""
    names = platforms or list(SCRAPERS.keys())
    scrapers = []
    for name in names:
        if name in SCRAPERS:
            scrapers.append(SCRAPERS[name]())
        else:
            logger.warning(f"Unknown platform: {name}")
    return scrapers


class Pipeline:
    """Orchestrates the full scan → score → generate → apply cycle."""

    def __init__(self):
        self._analyzer = JobAnalyzer()
        self._generator = ApplicationGenerator()

    def run_cycle(
        self,
        platforms: list[str] | None = None,
        filters: dict | None = None,
    ) -> dict:
        """Run one full cycle. Returns summary dict.

        Args:
            platforms: List of platform names to scan (default: all registered).
            filters: Search filters to pass to scrapers. Supported keys:
                - query (str): search keywords
                - skills (list[str]): skills to search for
                - contracts (list[str] | str): "freelance", "cdi", "cdd"
                - freshness (str): "24h", "7d", "14d", "30d"
                - remote (str | bool): "full", "partial", "no", True/False
                - location (str | list[str]): city/region/country
                - min_rate (int): minimum daily rate
                - max_rate (int): maximum daily rate
                - max_pages (int): max pages to scrape per query
                If None, defaults are built from settings.
        """
        total_new = 0
        total_applied = 0

        scrapers = _get_enabled_scrapers(platforms)
        if not scrapers:
            logger.warning("No scrapers available. Register scrapers first.")
            return {"new_jobs": 0, "applied": 0}

        if filters is None:
            base_filters = {
                "skills": settings.freelancer_skills,
                "location": settings.preferred_locations,
                "remote": settings.remote_only,
                "min_rate": settings.daily_rate_min,
                "contracts": ["freelance"],
            }
        else:
            base_filters = filters

        # Use search_queries when no explicit query was provided
        if "query" not in base_filters and settings.search_queries:
            filter_sets = []
            for q in settings.search_queries:
                f = dict(base_filters)
                f["query"] = q
                filter_sets.append(f)
        else:
            filter_sets = [base_filters]

        for scraper in scrapers:
            platform = scraper.platform_name
            logger.info(f"Scanning {platform}...")
            now = datetime.now(timezone.utc).isoformat()
            log_id = log_scan_start(platform, now)

            try:
                jobs = []
                for f in filter_sets:
                    logger.info(f"Query: {f.get('query', f.get('skills', [])[:3])}")
                    jobs.extend(scraper.scrape_jobs(f))
                new_count = 0

                for job in jobs:
                    if save_job(job):
                        new_count += 1

                log_scan_finish(
                    log_id,
                    datetime.now(timezone.utc).isoformat(),
                    len(jobs),
                    new_count,
                )
                logger.info(f"{platform}: found {len(jobs)} jobs, {new_count} new")
                total_new += new_count

            except Exception as e:
                logger.error(f"Scraper {platform} failed: {e}")
                log_scan_finish(
                    log_id,
                    datetime.now(timezone.utc).isoformat(),
                    0,
                    0,
                    status="error",
                )
                continue

        # Process new jobs: score → generate → apply
        new_jobs = get_jobs(status="new")
        for job in new_jobs:
            applied = self._process_job(job)
            if applied:
                total_applied += 1

        # Retry scored jobs that have draft applications (failed on previous attempt)
        scored_jobs = get_jobs(status="scored")
        for job in scored_jobs:
            app = get_application_for_job(job.id)
            if app and app.submission_status == "draft" and app.proposal_message:
                logger.info(f"Retrying apply for scored job: '{job.title}'")
                submitted = self._submit(job, app, app.id)
                if submitted:
                    total_applied += 1

        return {"new_jobs": total_new, "applied": total_applied}

    def _process_job(self, job: JobRecord) -> bool:
        """Score, generate application, and submit for a single job."""
        try:
            # Stage 1: Score relevance
            result = self._analyzer.score_relevance(job)
            update_job_relevance(
                job.id,
                result.score,
                result.reasoning,
                result.matching_skills,
                result.concerns,
            )
            job.relevance_score = result.score

            # Track every scored job in Google Sheets
            now_str = datetime.now(timezone.utc).isoformat()
            status = "qualified" if result.score >= settings.relevance_threshold else "skipped"
            track_job_found(
                date=now_str,
                platform=job.platform,
                title=job.title,
                company=job.company,
                location=job.location,
                remote=job.remote,
                contract_type=job.contract_type or "freelance",
                duration=job.duration,
                daily_rate_min=job.daily_rate_min,
                daily_rate_max=job.daily_rate_max,
                skills=job.skills,
                score=result.score,
                reasoning=result.reasoning,
                matching_skills=result.matching_skills,
                concerns=result.concerns,
                status=status,
                language=job.language,
                url=job.url,
            )

            # Stage 2: Filter by threshold
            if result.score < settings.relevance_threshold:
                update_job_status(job.id, "skipped")
                logger.info(
                    f"Skipped '{job.title}' (score {result.score} < {settings.relevance_threshold})"
                )
                return False

            # Stage 3: Generate proposal
            proposal = self._generator.generate_proposal(job)

            app = ApplicationRecord(
                job_id=job.id,
                proposal_message=proposal,
            )
            app_id = save_application(app)

            # Stage 4: Submit (fully automatic)
            submitted = self._submit(job, app, app_id)
            return submitted

        except Exception as e:
            logger.error(f"Failed to process '{job.title}': {e}")
            update_job_status(job.id, "failed")
            return False

    def _submit(self, job: JobRecord, app: ApplicationRecord, app_id: int) -> bool:
        """Submit application via the platform's applicator."""
        if job.platform not in APPLICATORS:
            logger.warning(f"No applicator for {job.platform}, keeping as draft")
            return False

        applicator = APPLICATORS[job.platform]()
        try:
            success = applicator.submit_application(job, app)
            now = datetime.now(timezone.utc).isoformat()

            # Get detailed result from applicator
            apply_result = getattr(applicator, "last_apply_result", None)
            application_result = apply_result.application_result if apply_result else ""
            external_url = apply_result.external_url if apply_result else ""

            # Track every attempt in Google Sheets
            track_application(
                date=now,
                platform=job.platform,
                title=job.title,
                company=job.company,
                location=job.location,
                remote=job.remote,
                daily_rate_min=job.daily_rate_min,
                daily_rate_max=job.daily_rate_max,
                score=job.relevance_score,
                status="submitted" if success else "failed",
                application_result=application_result,
                external_url=external_url,
                url=job.url,
                proposal=app.proposal_message,
            )

            if success:
                update_application_status(app_id, "submitted", submitted_at=now)
                update_job_status(job.id, "applied")
                logger.info(f"Applied to '{job.title}' on {job.platform}")
                return True
            else:
                update_application_status(app_id, "failed", error=application_result)
                update_job_status(job.id, "failed")
                return False
        except Exception as e:
            update_application_status(app_id, "failed", error=str(e))
            update_job_status(job.id, "failed")
            logger.error(f"Submit failed for '{job.title}': {e}")
            return False
