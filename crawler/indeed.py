"""Indeed job site crawler."""

from urllib.parse import quote_plus

import config
from crawler.base import BaseCrawler
from crawler.diagnostics import log_page_state, save_page_diagnostics
from crawler.indeed_uc import crawl_indeed_uc
from crawler.playwright_session import PlaywrightSession
from models.job import Job
from utils.logger import Logger

INDEED_JOB_SELECTORS = (
    "#mosaic-provider-jobcards a[data-jk], "
    "#mosaic-provider-jobcards h2.jobTitle a, "
    "div.job_seen_beacon, "
    "div.cardOutline, "
    "a.jcs-JobTitle, "
    "a.tapItem"
)

INDEED_RESULTS_CONTAINER = (
    "#mosaic-provider-jobcards, .jobsearch-ResultsList, div.job_seen_beacon"
)


class IndeedCrawler(BaseCrawler):
    """Crawler for Indeed Australia job listings."""

    source_name = "Indeed"

    def __init__(self) -> None:
        """Initialize the Indeed crawler."""
        self.logger = Logger("indeed-crawler")

    async def crawl(self) -> list[Job]:
        """Fetch job listings from Indeed search results."""
        self.logger.info("Starting crawler")

        if config.INDEED_USE_UNDETECTED_CHROME:
            self.logger.info("Using undetected-chromedriver for Indeed")
            try:
                return await crawl_indeed_uc(self.logger)
            except Exception as exc:
                self.logger.warning(
                    f"Indeed undetected-chromedriver failed ({exc}) - trying Playwright"
                )

        return await self._crawl_playwright()

    async def _crawl_playwright(self) -> list[Job]:
        """Fetch Indeed listings via Playwright (fallback path)."""
        search_url = self._build_search_url()
        session = PlaywrightSession(site="indeed")

        try:
            page = await session.start()
            await page.goto(search_url, wait_until="domcontentloaded")
            await page.wait_for_load_state("load")

            await session.dismiss_cookie_banner(
                page,
                results_selector=INDEED_RESULTS_CONTAINER,
            )

            blocked_reason = await self._detect_blocked_page(page)
            if blocked_reason:
                await log_page_state(page, self.logger, label="Indeed blocked")
                await save_page_diagnostics(page, self.logger, prefix="Indeed")
                raise RuntimeError(blocked_reason)

            try:
                await page.wait_for_selector(
                    INDEED_JOB_SELECTORS,
                    state="attached",
                    timeout=config.PLAYWRIGHT_TIMEOUT,
                )
            except Exception as exc:
                await save_page_diagnostics(page, self.logger, prefix="Indeed")
                raise RuntimeError("search results selector not found") from exc

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

    async def _detect_blocked_page(self, page) -> str | None:
        """Detect CAPTCHA or bot-protection pages (not normal OneTrust cookie banners)."""
        title = (await page.title()).lower()
        html = (await page.content()).lower()
        has_results = await page.locator(INDEED_RESULTS_CONTAINER).count() > 0

        if has_results:
            return None

        if "security check" in title or "security check" in html:
            return "Indeed returned Security Check (bot protection page)"

        if "just a moment" in title:
            return "Indeed returned CAPTCHA or bot challenge page"

        if "captcha" in title or "recaptcha" in title:
            return "Indeed returned CAPTCHA or bot challenge page"

        return None

    async def _extract_jobs(self, page) -> list[Job]:
        """Extract job listings from the Indeed results page."""
        cards = await page.eval_on_selector_all(
            "#mosaic-provider-jobcards div.job_seen_beacon, "
            "#mosaic-provider-jobcards div.cardOutline, "
            "div.job_seen_beacon, div.cardOutline, td.resultContent",
            """elements => elements.map(el => {
                const link = el.querySelector('a.jcs-JobTitle, a[id^="job_"], a.tapItem, h2.jobTitle a');
                const title = el.querySelector('h2.jobTitle span, h2 span, .jobTitle, a.jcs-JobTitle');
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
