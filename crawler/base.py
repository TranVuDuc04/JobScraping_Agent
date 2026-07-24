"""Abstract base crawler."""

from abc import ABC, abstractmethod

from models.job import Job


class BaseCrawler(ABC):
    """Abstract base class for job site crawlers."""

    source_name: str = "Unknown"

    @abstractmethod
    async def crawl(self) -> list[Job]:
        """Fetch job listings from the target platform.

        Returns:
            A list of parsed Job objects from the source.
        """
        raise NotImplementedError
