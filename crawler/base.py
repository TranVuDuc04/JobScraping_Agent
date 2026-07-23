"""Abstract base crawler."""

from abc import ABC, abstractmethod


class BaseCrawler(ABC):
    """Abstract base class for job site crawlers.

    Subclasses must implement the crawl method to fetch job listing URLs
    from a specific source platform.
    """

    @abstractmethod
    async def crawl(self) -> list[str]:
        """Fetch job detail URLs from the target platform.

        Returns:
            A list of job detail page URLs.

        Raises:
            NotImplementedError: If the subclass has not implemented this method.
        """
        raise NotImplementedError
