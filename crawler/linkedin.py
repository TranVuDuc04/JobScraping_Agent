"""LinkedIn job site crawler."""

from crawler.base import BaseCrawler


class LinkedInCrawler(BaseCrawler):
    """Crawler for LinkedIn job listings."""

    async def crawl(self) -> list[str]:
        """Fetch job detail URLs from LinkedIn.

        Returns:
            A list of LinkedIn job detail URLs.

        Raises:
            NotImplementedError: Crawling logic is not yet implemented.
        """
        raise NotImplementedError
