"""Indeed job site crawler."""

from urllib.parse import quote_plus

import config
from crawler.base import BaseCrawler
from crawler.playwright_session import PlaywrightSession
from models.job import Job
from utils.logger import Logger


class IndeedCrawler(BaseCrawler):
    """Crawler for Indeed Australia job listings."""

    source_name = "Indeed"

    def __init__(self) -> None:
        """Initialize the Indeed crawler."""
        self.logger = Logger("indeed-crawler")

    async def crawl(self) -> list[Job]:
        """Fetch job listings from Indeed search results."""
        self.logger.info("Starting crawler")
        search_url = self._build_search_url()
        session = PlaywrightSession()

        try:
            page = await session.start()
            await page.goto(search_url, wait_until="domcontentloaded")
            await page.wait_for_load_state("load")
            await session.dismiss_cookie_banner(page)
            await page.wait_for_selector(
                "a.jcs-JobTitle, a.tapItem, div.job_seen_beacon",
                state="attached",
                timeout=config.PLAYWRIGHT_TIMEOUT,
            )
            jobs = await self._extract_jobs(page)
            self.logger.info(f"Found {len(jobs)} jobs")
            return jobs
        finally:
            await session.close()

    def _build_search_url(self) -> str:
        """Build an Indeed Australia search URL from configuration."""
        query = quote_plus(config.INDEED_SEARCH_KEYWORDS)
        location = quote_plus(config.INDEED_SEARCH_LOCATION)
        return f"https://au.indeed.com/jobs?q={query}&l={location}"

    async def _extract_jobs(self, page) -> list[Job]:
        """Extract job listings from the Indeed results page."""
        cards = await page.eval_on_selector_all(
            "div.job_seen_beacon, div.cardOutline, td.resultContent",
            """elements => elements.map(el => {
                const link = el.querySelector('a.jcs-JobTitle, a[id^="job_"], a.tapItem');
                const title = el.querySelector('h2.jobTitle span, h2 span, .jobTitle');
                const company = el.querySelector('[data-testid="company-name"], .companyName, .company');
                const location = el.querySelector('[data-testid="text-location"], .companyLocation, .location');
                const salary = el.querySelector('[data-testid="attribute_snippet_testid"], .salary-snippet, .salaryText');
                if (!link || !title) return null;
                return {
                    href: link.href || link.getAttribute('href'),
                    title: title.textContent.trim(),
                    company: company ? company.textContent.trim() : '',
                    location: location ? location.textContent.trim() : '',
                    salary: salary ? salary.textContent.trim() : '',
                };
            }).filter(Boolean)""",
        )

        seen: set[str] = set()
        jobs: list[Job] = []

        for card in cards:
            href = card.get("href", "")
            url = href if href.startswith("http") else f"https://au.indeed.com{href}"
            if url in seen:
                continue
            seen.add(url)
            title = card.get("title", "")
            company = card.get("company") or "Unknown"
            jobs.append(
                Job(
                    title=title,
                    company=company,
                    location=card.get("location") or None,
                    salary=card.get("salary") or None,
                    employment_type=None,
                    description=title,
                    url=url,
                    source=self.source_name,
                    posted_date=None,
                )
            )

        return jobs
