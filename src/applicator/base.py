from abc import ABC, abstractmethod

from src.models import ApplicationRecord, JobRecord


class PlatformApplicator(ABC):
    """Abstract base class for submitting applications on a platform."""

    platform_name: str = ""

    @abstractmethod
    def submit_application(self, job: JobRecord, application: ApplicationRecord) -> bool:
        """Submit an application to a job.

        Args:
            job: The job to apply to.
            application: The generated application content.

        Returns:
            True if submission was successful.
        """
        ...
