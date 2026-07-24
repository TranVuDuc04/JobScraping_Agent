"""LinkedIn job site crawler."""

from urllib.parse import quote_plus

import config
from crawler.base import BaseCrawler
from crawler.playwright_session import PlaywrightSession
from models.job import Job
from utils.logger import Logger

LINKEDIN_JOB_SELECTOR = (
    "a.base-card__full-link, a.job-card-container__link, a[href*='/jobs/view/']"
)


class LinkedInCrawler(BaseCrawler):
    """Crawler for LinkedIn job listings."""

    source_name = "LinkedIn"

    def __init__(self) -> None:
        """Initialize the LinkedIn crawler."""
        self.logger = Logger("linkedin-crawler")

    async def crawl(self) -> list[Job]:
        """Fetch job listings from LinkedIn search results."""
        self.logger.info("Starting crawler")
        search_url = self._build_search_url()
        session = PlaywrightSession()

        try:
            page = await session.start()
            await page.goto(search_url, wait_until="domcontentloaded")
            await page.wait_for_load_state("load")
            await session.dismiss_cookie_banner(page)
            await page.wait_for_selector(
                LINKEDIN_JOB_SELECTOR,
                state="attached",
                timeout=config.PLAYWRIGHT_TIMEOUT,
            )
            jobs = await self._extract_jobs(page)
            self.logger.info(f"Found {len(jobs)} jobs")
            return jobs
        finally:
            await session.close()

    def _build_search_url(self) -> str:
        """Build a LinkedIn jobs search URL from configuration."""
        keywords = quote_plus(config.LINKEDIN_SEARCH_KEYWORDS)
        location = quote_plus(config.LINKEDIN_SEARCH_LOCATION)
        return (
            "https://www.linkedin.com/jobs/search/"
            f"?keywords={keywords}&location={location}"
        )

    async def _extract_jobs(self, page) -> list[Job]:
        """Extract job listings from the LinkedIn results page."""
        cards = await page.eval_on_selector_all(
            "li .base-card, li .job-card-container, li",
            """elements => elements.map(el => {
                const link = el.querySelector('a.base-card__full-link, a.job-card-container__link, a[href*="/jobs/view/"]');
                const title = el.querySelector('.base-search-card__title, .job-card-list__title, h3');
                const company = el.querySelector('.base-search-card__subtitle, .job-card-container__company-name, h4');
                const location = el.querySelector('.job-search-card__location, .job-card-container__metadata-item');
                const time = el.querySelector('time');
                if (!link || !title) return null;
                return {
                    href: link.href || link.getAttribute('href'),
                    title: title.textContent.trim(),
                    company: company ? company.textContent.trim() : '',
                    location: location ? location.textContent.trim() : '',
                    posted: time ? time.textContent.trim() : ''
                };
            }).filter(Boolean)""",
        )

        seen: set[str] = set()
        jobs: list[Job] = []

        for card in cards:
            url = card.get("href")
            if not url or url in seen:
                continue
            seen.add(url)
            title = card.get("title", "")
            company = card.get("company") or "Unknown"
            jobs.append(
                Job(
                    title=title,
                    company=company,
                    location=card.get("location") or None,
                    salary=None,
                    employment_type=None,
                    description=title,
                    url=url,
                    source=self.source_name,
                    posted_date=card.get("posted") or None,
                )
            )

        return jobs
