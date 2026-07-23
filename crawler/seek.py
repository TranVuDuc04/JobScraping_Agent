"""Seek job site crawler."""

import re
from urllib.parse import urljoin, urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

import config
from crawler.base import BaseCrawler
from utils.logger import Logger

JOB_LINK_SELECTOR = (
    'a[data-automation="jobTitle"], '
    'a[data-automation="job-list-view-job-link"], '
    'a[href*="/job/"]'
)
MAX_RETRIES = 3
JOB_ID_PATTERN = re.compile(r"/job/(\d+)")


class SeekCrawler(BaseCrawler):
    """Crawler that collects job detail URLs from Seek Australia."""

    def __init__(self, search_url: str | None = None) -> None:
        """Initialize the Seek crawler.

        Args:
            search_url: Optional override for the Seek search results URL.
        """
        self.search_url = search_url or config.SEEK_SEARCH_URL
        self.logger = Logger("seek-crawler")
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def crawl(self) -> list[str]:
        """Fetch job detail URLs from Seek with automatic retries.

        Returns:
            A deduplicated list of Seek job detail URLs.

        Raises:
            RuntimeError: If all retry attempts fail.
        """
        self.logger.info("Starting crawler")
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                urls = await self._run_crawl()
                self.logger.info("Returning URLs")
                return urls
            except Exception as exc:
                last_error = exc
                self.logger.error(
                    f"Attempt {attempt}/{MAX_RETRIES} failed to load page: {exc}"
                )
                await self._close_browser()
                if attempt == MAX_RETRIES:
                    break

        raise RuntimeError(
            f"Seek crawler failed after {MAX_RETRIES} attempts"
        ) from last_error

    async def _run_crawl(self) -> list[str]:
        """Execute a single crawl attempt.

        Returns:
            A deduplicated list of job detail URLs.
        """
        try:
            await self._launch_browser()
            await self._open_search_page()
            urls = await self._extract_urls()
            self.logger.info(f"Found {len(urls)} jobs")
            return urls
        finally:
            await self._close_browser()

    async def _launch_browser(self) -> None:
        """Launch Chromium and open a new browser page."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=config.HEADLESS
        )
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(config.PLAYWRIGHT_TIMEOUT)

    async def _open_search_page(self) -> None:
        """Navigate to the Seek search results page and wait for listings."""
        if self._page is None:
            raise RuntimeError("Browser page is not initialized")

        self.logger.info("Opening Seek...")
        await self._page.goto(self.search_url, wait_until="domcontentloaded")
        await self._page.wait_for_load_state("load")
        await self._dismiss_cookie_banner()
        await self._page.wait_for_selector(
            JOB_LINK_SELECTOR,
            state="attached",
            timeout=config.PLAYWRIGHT_TIMEOUT,
        )

    async def _dismiss_cookie_banner(self) -> None:
        """Dismiss the cookie consent banner if it appears."""
        if self._page is None:
            return

        accept_button = self._page.locator(
            'button:has-text("Accept"), button:has-text("Accept all")'
        )
        if await accept_button.count() > 0:
            await accept_button.first.click()
            await self._page.wait_for_load_state("load")

    async def _extract_urls(self) -> list[str]:
        """Extract and deduplicate job detail URLs from the current page.

        Returns:
            A list of normalized Seek job detail URLs.
        """
        if self._page is None:
            raise RuntimeError("Browser page is not initialized")

        hrefs = await self._page.eval_on_selector_all(
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
        """Normalize a href into a canonical Seek job detail URL.

        Args:
            href: Raw link href from the page.

        Returns:
            Canonical job URL, or None if the link is not a job detail page.
        """
        if not href:
            return None

        absolute_url = urljoin("https://www.seek.com.au", href)
        match = JOB_ID_PATTERN.search(urlparse(absolute_url).path)
        if not match:
            return None

        return f"https://www.seek.com.au/job/{match.group(1)}"

    async def _close_browser(self) -> None:
        """Close browser resources in the correct order."""
        if self._page is not None:
            await self._page.close()
            self._page = None

        if self._context is not None:
            await self._context.close()
            self._context = None

        if self._browser is not None:
            await self._browser.close()
            self._browser = None

        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
