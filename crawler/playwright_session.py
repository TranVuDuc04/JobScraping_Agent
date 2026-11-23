# Shared Playwright helpers for listing-page crawlers.

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

import config
from crawler.browser_config import BROWSER_ARGS, STEALTH_INIT_SCRIPT, get_context_options
from crawler.consent import dismiss_consent_if_present
from utils.logger import Logger


class PlaywrightSession:
    # Reusable Playwright browser session for listing crawlers.

    def __init__(self, site: str = "generic") -> None:
        self.site = site
        self.logger = Logger(f"{site}-session")
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self) -> Page:
        # Launch the browser and return a configured page.
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=config.HEADLESS,
            args=BROWSER_ARGS,
        )
        self._context = await self._browser.new_context(**get_context_options())
        await self._context.add_init_script(STEALTH_INIT_SCRIPT)
        self._page = await self._context.new_page()
        self._page.set_default_timeout(config.PLAYWRIGHT_TIMEOUT)
        return self._page

    async def close(self) -> None:
        # Close all Playwright resources.
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

    async def dismiss_cookie_banner(
        self,
        page: Page,
        *,
        results_selector: str | None = None,
    ) -> bool:
        # Dismiss consent modals when present without blocking the crawl.
        return await dismiss_consent_if_present(
            page,
            self.logger,
            site=self.site,
            results_selector=results_selector,
        )
