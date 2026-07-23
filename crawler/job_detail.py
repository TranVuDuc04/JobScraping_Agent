"""Job detail page crawler."""

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

import config
from utils.logger import Logger

MAX_RETRIES = 3
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class JobDetailCrawler:
    """Fetches raw HTML from individual job detail pages.

    Launches a single browser instance and reuses it across multiple
    job pages, opening and closing a new page for each request.
    """

    def __init__(self) -> None:
        """Initialize the job detail crawler."""
        self.logger = Logger("job-detail-crawler")
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def start(self) -> None:
        """Launch the browser and create a reusable context."""
        if self._browser is not None:
            return

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=config.HEADLESS
        )
        self._context = await self._browser.new_context(user_agent=USER_AGENT)

    async def close(self) -> None:
        """Close the browser and release all Playwright resources."""
        if self._context is not None:
            await self._context.close()
            self._context = None

        if self._browser is not None:
            await self._browser.close()
            self._browser = None

        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def fetch_job(self, url: str) -> str | None:
        """Fetch the raw HTML content of a job detail page.

        Args:
            url: Job detail page URL.

        Returns:
            Full page HTML as a string, or None if all retries fail.
        """
        await self.start()

        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                self.logger.warning(f"Retry {attempt}")

            html = await self._fetch_page(url)
            if html is not None:
                self.logger.info("Job fetched")
                return html

        self.logger.error("Failed after retries")
        return None

    async def fetch_jobs(self, urls: list[str]) -> list[str | None]:
        """Fetch HTML for multiple job URLs, continuing on individual failures.

        Args:
            urls: List of job detail page URLs.

        Returns:
            List of HTML strings (or None for jobs that failed after retries).
        """
        await self.start()
        results: list[str | None] = []

        for url in urls:
            results.append(await self.fetch_job(url))

        return results

    async def _fetch_page(self, url: str) -> str | None:
        """Open a job page and return its HTML content.

        Args:
            url: Job detail page URL.

        Returns:
            Page HTML, or None if the page could not be loaded.
        """
        if self._context is None:
            raise RuntimeError("Browser context is not initialized")

        page: Page | None = None
        try:
            self.logger.info("Opening job page")
            page = await self._context.new_page()
            page.set_default_timeout(config.PLAYWRIGHT_TIMEOUT)
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_load_state("load")
            await self._dismiss_cookie_banner(page)
            return await page.content()
        except Exception:
            return None
        finally:
            if page is not None:
                await page.close()

    async def _dismiss_cookie_banner(self, page: Page) -> None:
        """Dismiss the cookie consent banner if it appears.

        Args:
            page: Active Playwright page.
        """
        accept_button = page.locator(
            'button:has-text("Accept"), button:has-text("Accept all")'
        )
        if await accept_button.count() > 0:
            await accept_button.first.click()
            await page.wait_for_load_state("load")

    async def __aenter__(self) -> "JobDetailCrawler":
        """Enter async context and start the browser."""
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        """Exit async context and close the browser."""
        await self.close()
