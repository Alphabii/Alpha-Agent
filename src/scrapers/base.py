from abc import ABC, abstractmethod

from src.models import ScrapedJob


class PlatformScraper(ABC):
    """Abstract base class for platform scrapers."""

    platform_name: str = ""

    @abstractmethod
    def scrape_jobs(self, filters: dict) -> list[ScrapedJob]:
        """Scrape job listings matching the given filters.

        Args:
            filters: Dict with keys like 'skills', 'location', 'remote',
                     'min_rate', 'keywords'.

        Returns:
            List of ScrapedJob objects.
        """
        ...

    @abstractmethod
    def get_job_details(self, job_url: str) -> str:
        """Fetch the full job description from a job URL."""
        ...
