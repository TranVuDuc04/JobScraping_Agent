"""Seek job site crawler."""

import re
from urllib.parse import urljoin, urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

import config
from crawler.base import BaseCrawler
from crawler.browser_config import BROWSER_ARGS, STEALTH_INIT_SCRIPT, get_context_options
from crawler.diagnostics import save_page_diagnostics
from crawler.job_detail import DetailCrawlStats, JobDetailCrawler
from crawler.seek_detail_uc import fetch_seek_details_uc
from crawler.seek_api import (
    SeekListing,
    fetch_job_listings_for_keywords,
    filter_recent_listings,
    listing_to_job,
)
from models.job import Job
from parser.parser import JobParser
from rules import rule_config
from utils.logger import Logger

JOB_LINK_SELECTOR = (
    'a[data-automation="jobTitle"], '
    'a[data-automation="job-list-view-job-link"], '
    'a[href*="/job/"]'
)
MAX_RETRIES = 3
JOB_ID_PATTERN = re.compile(r"/job/(\d+)")


class SeekCrawler(BaseCrawler):
    """Crawler that collects job listings from Seek Australia."""

    source_name = "Seek"

    def __init__(self, search_url: str | None = None) -> None:
        """Initialize the Seek crawler.

        Args:
            search_url: Optional override for the Seek search results URL.
        """
        self.search_urls = (
            [search_url] if search_url else config.get_seek_search_urls()
        )
        self.logger = Logger("seek-crawler")

    async def crawl(self) -> list[Job]:
        """Fetch parsed job listings from Seek with automatic retries.

        Returns:
            A deduplicated list of Seek Job objects.

        Raises:
            RuntimeError: If all retry attempts fail.
        """
        self.logger.info("Starting crawler")
        if config.USE_SEEK_API_FOR_URLS:
            listings = self._discover_listings_via_api()
            jobs = await self._fetch_jobs_from_listings(listings)
        else:
            urls = await self._discover_urls()
            jobs = await self._fetch_jobs_from_urls(urls)

        self.logger.info(f"Returning {len(jobs)} jobs")
        return jobs

    def _discover_listings_via_api(self) -> list[SeekListing]:
        """Fetch listings via API and drop jobs older than the age limit."""
        self.logger.info("Using Seek search API for URL discovery")
        try:
            listings = fetch_job_listings_for_keywords(
                config.SEEK_SEARCH_KEYWORDS,
                config.SEEK_SEARCH_LOCATION,
            )
        except Exception as exc:
            self.logger.error(f"Seek API request failed: {exc}")
            raise RuntimeError("Seek API URL discovery failed") from exc

        self.logger.info(
            f"Found {len(listings)} jobs across {len(config.SEEK_SEARCH_KEYWORDS)} searches"
        )
        self.logger.info(f"Seek discovered: {len(listings)} jobs")

        recent = filter_recent_listings(listings)
        skipped = len(listings) - len(recent)
        self.logger.info(
            f"Jobs newer than {rule_config.MAX_JOB_AGE_DAYS} days: {len(recent)}"
        )
        self.logger.info(f"Jobs skipped as old: {skipped}")
        return recent

    async def _discover_urls(self) -> list[str]:
        """Discover job detail URLs from Seek via Playwright search pages."""
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                urls = await self._run_url_crawl()
                self.logger.info("Returning URLs")
                return urls
            except Exception as exc:
                last_error = exc
                self.logger.error(
                    f"Attempt {attempt}/{MAX_RETRIES} failed to load page: {exc}"
                )
                if attempt == MAX_RETRIES:
                    break

        raise RuntimeError(
            f"Seek crawler failed after {MAX_RETRIES} attempts"
        ) from last_error

    async def _fetch_jobs_from_listings(self, listings: list[SeekListing]) -> list[Job]:
        """Fetch and parse recent Seek job detail pages concurrently."""
        if not listings:
            return []

        if config.SEEK_SKIP_DETAIL_CRAWL:
            self.logger.warning(
                "SEEK_SKIP_DETAIL_CRAWL enabled - using Seek API metadata only"
            )
            return [listing_to_job(listing) for listing in listings]

        parser = JobParser()
        urls = [listing.url for listing in listings]
        self.logger.info("Detail crawling started...")

        if config.SEEK_USE_UNDETECTED_CHROME:
            self.logger.info(
                "Using undetected-chromedriver for Seek detail pages "
                f"(timeout={config.SEEK_DETAIL_TIMEOUT}ms, sequential)"
            )
            try:
                html_results, stats = await fetch_seek_details_uc(urls, self.logger)
            except Exception as exc:
                self.logger.warning(
                    f"undetected-chromedriver failed ({exc}) - falling back to Playwright"
                )
                html_results, stats = await self._fetch_details_playwright(urls)
        else:
            html_results, stats = await self._fetch_details_playwright(urls)

        if stats.verification_blocked > 0:
            self.logger.warning(
                "Seek human verification blocked detail pages - "
                "falling back to API metadata for failed jobs"
            )

        jobs, api_fallback = self._parse_detail_results(listings, html_results, parser)
        self._log_detail_stats(stats, api_fallback=api_fallback)
        return jobs

    async def _fetch_details_playwright(
        self,
        urls: list[str],
    ) -> tuple[list[str | None], DetailCrawlStats]:
        """Fetch Seek detail pages via Playwright."""
        async with JobDetailCrawler() as detail_crawler:
            self.logger.info(
                f"Detail crawl config: concurrency={config.SEEK_DETAIL_CONCURRENCY}, "
                f"timeout={config.SEEK_DETAIL_TIMEOUT}ms"
            )
            return await detail_crawler.fetch_jobs_concurrent(urls)

    async def _fetch_jobs_from_urls(self, urls: list[str]) -> list[Job]:
        """Fetch and parse Seek job detail pages discovered via Playwright."""
        if not urls:
            return []

        parser = JobParser()
        self.logger.info("Detail crawling started...")

        async with JobDetailCrawler() as detail_crawler:
            self.logger.info(
                f"Detail crawl config: concurrency={config.SEEK_DETAIL_CONCURRENCY}, "
                f"timeout={config.SEEK_DETAIL_TIMEOUT}ms"
            )
            html_results, stats = await detail_crawler.fetch_jobs_concurrent(urls)

        jobs: list[Job] = []
        for url, html in zip(urls, html_results, strict=True):
            if not html:
                continue
            try:
                jobs.append(parser.parse(html, url))
            except Exception as exc:
                self.logger.error(f"Failed to parse Seek job {url}: {exc}")

        self._log_detail_stats(stats)
        return jobs

    def _parse_detail_results(
        self,
        listings: list[SeekListing],
        html_results: list[str | None],
        parser: JobParser,
    ) -> tuple[list[Job], int]:
        """Parse fetched HTML into Job objects, with API fallback on failure."""
        jobs: list[Job] = []
        api_fallback = 0

        for listing, html in zip(listings, html_results, strict=True):
            if html:
                try:
                    jobs.append(parser.parse(html, listing.url))
                    continue
                except Exception as exc:
                    self.logger.error(f"Failed to parse Seek job {listing.url}: {exc}")

            if config.SEEK_API_FALLBACK:
                jobs.append(listing_to_job(listing))
                api_fallback += 1
                self.logger.info(
                    f"Using API metadata fallback for {listing.url} "
                    "(detail page unavailable)"
                )
            else:
                self.logger.error(f"Skipped failed detail page: {listing.url}")

        return jobs, api_fallback

    def _log_detail_stats(
        self,
        stats: DetailCrawlStats,
        *,
        api_fallback: int = 0,
    ) -> None:
        """Log detail crawl performance metrics."""
        self.logger.info("Job details:")
        self.logger.info(f"{stats.total} total")
        self.logger.info(f"{stats.successful} successful")
        self.logger.info(f"{stats.failed} failed")
        if stats.verification_blocked:
            self.logger.info(
                f"{stats.verification_blocked} blocked by human verification"
            )
        if api_fallback:
            self.logger.info(f"{api_fallback} filled from API metadata fallback")
        if stats.aborted_early:
            self.logger.info("Detail crawl aborted early after verification detected")
        self.logger.info(f"Total detail crawl time: {stats.total_seconds:.1f}s")
        self.logger.info(f"Average detail time: {stats.average_seconds:.2f}s")

    async def _run_url_crawl(self) -> list[str]:
        """Execute a single crawl attempt across all configured searches."""
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=config.HEADLESS,
            args=BROWSER_ARGS,
        )
        context = await browser.new_context(**get_context_options())
        await context.add_init_script(STEALTH_INIT_SCRIPT)
        page = await context.new_page()
        page.set_default_timeout(config.PLAYWRIGHT_TIMEOUT)

        try:
            seen: set[str] = set()
            urls: list[str] = []

            for search_url in self.search_urls:
                self.logger.info(f"Opening Seek search: {search_url}")
                page_urls = await self._open_search_page(page, search_url)
                for url in page_urls:
                    if url not in seen:
                        seen.add(url)
                        urls.append(url)

            self.logger.info(f"Found {len(urls)} jobs")
            return urls
        finally:
            await page.close()
            await context.close()
            await browser.close()
            await playwright.stop()

    async def _open_search_page(self, page: Page, search_url: str) -> list[str]:
        """Navigate to a Seek search page and return job detail URLs."""
        response = await page.goto(
            search_url,
            wait_until="domcontentloaded",
        )
        if response is not None:
            self.logger.info(f"HTTP status: {response.status}")

        await page.wait_for_load_state("load")
        await self._dismiss_cookie_banner(page)

        try:
            await page.wait_for_selector(
                JOB_LINK_SELECTOR,
                state="attached",
                timeout=config.PLAYWRIGHT_TIMEOUT,
            )
        except Exception:
            await save_page_diagnostics(page, self.logger)
            raise

        return await self._extract_urls(page)

    async def _dismiss_cookie_banner(self, page: Page) -> None:
        """Dismiss the cookie consent banner if it appears."""
        accept_button = page.locator(
            'button:has-text("Accept"), button:has-text("Accept all")'
        )
        if await accept_button.count() > 0:
            await accept_button.first.click()
            await page.wait_for_load_state("load")

    async def _extract_urls(self, page: Page) -> list[str]:
        """Extract and deduplicate job detail URLs from the current page."""
        hrefs = await page.eval_on_selector_all(
            JOB_LINK_SELECTOR,
            "elements => elements.map(el => el.href || el.getAttribute('href'))",
        )

        seen: set[str] = set()
        urls: list[str] = []

        for href in hrefs:
            normalized = self._normalize_job_url(href)
            if normalized and normalized not in seen:
                seen.add(normalized)
                urls.append(normalized)

        return urls

    def _normalize_job_url(self, href: str) -> str | None:
        """Normalize a href into a canonical Seek job detail URL."""
        if not href:
            return None

        absolute_url = urljoin("https://www.seek.com.au", href)
        match = JOB_ID_PATTERN.search(urlparse(absolute_url).path)
        if not match:
            return None

        return f"https://www.seek.com.au/job/{match.group(1)}"
