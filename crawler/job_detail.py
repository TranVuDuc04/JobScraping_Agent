# Job detail page crawler.

import asyncio
import time
from dataclasses import dataclass, field

from playwright.async_api import Browser, BrowserContext, Page, Playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

import config
from crawler.browser_config import BROWSER_ARGS, STEALTH_INIT_SCRIPT, get_context_options
from crawler.consent import dismiss_consent_if_present
from crawler.diagnostics import is_verification_page, job_id_from_url, save_page_diagnostics
from utils.logger import Logger

MAX_TRANSIENT_RETRIES = 2
JOB_DETAIL_SELECTOR = (
    '[data-automation="job-detail-title"], '
    '[data-automation="jobAdDetails"]'
)


@dataclass
class DetailCrawlStats:
    # Metrics for Seek detail page fetching.

    total: int = 0
    successful: int = 0
    failed: int = 0
    verification_blocked: int = 0
    aborted_early: bool = False
    total_seconds: float = 0.0
    per_job_seconds: list[float] = field(default_factory=list)

    @property
    def average_seconds(self) -> float:
        # Return the average fetch time for attempted jobs.
        if not self.per_job_seconds:
            return 0.0
        return sum(self.per_job_seconds) / len(self.per_job_seconds)


def format_fetch_error(exc: Exception) -> str:
    # Format an exception for logging, including empty-message cases.
    message = str(exc).strip()
    if message:
        return f"{exc.__class__.__name__}: {message}"
    return exc.__class__.__name__


def is_retryable_error(exc: Exception) -> bool:
    # Return True only for errors that may succeed on a quick retry.
    if isinstance(exc, PlaywrightTimeoutError):
        return False

    if isinstance(exc, TimeoutError):
        return False

    if isinstance(exc, asyncio.CancelledError):
        return False

    message = str(exc).lower()
    non_retryable_markers = (
        "timeout",
        "target closed",
        "target page, context or browser has been closed",
        "net::err_aborted",
        "net::err_blocked",
        "403",
        "404",
        "access denied",
        "blocked",
        "invalid url",
    )
    if any(marker in message for marker in non_retryable_markers):
        return False

    retryable_markers = (
        "net::err_connection",
        "connection reset",
        "econnreset",
        "502",
        "503",
        "504",
        "temporarily unavailable",
    )
    return any(marker in message for marker in retryable_markers)


def _detail_timeouts() -> tuple[int, int]:
    # Split the detail timeout budget between navigation and selector waits.
    total = config.SEEK_DETAIL_TIMEOUT
    goto_timeout = max(int(total * 0.5), 5000)
    selector_timeout = max(total - goto_timeout, 5000)
    return goto_timeout, selector_timeout


class JobDetailCrawler:
    # Fetches raw HTML from individual job detail pages.

    def __init__(self) -> None:
        # Initialize the job detail crawler.
        self.logger = Logger("job-detail-crawler")
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._start_lock = asyncio.Lock()
        self._active_lock = asyncio.Lock()
        self._active_fetches = 0
        self._closing = False
        self._open_pages: set[Page] = set()
        self._diagnostics_saved = 0
        self._abort_detail_crawl = False
        self._verification_blocked = 0

    async def start(self) -> None:
        # Launch the browser and create a reusable context.
        async with self._start_lock:
            if self._browser is not None:
                return

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=config.HEADLESS,
                args=BROWSER_ARGS,
            )
            self._context = await self._browser.new_context(**get_context_options())
            await self._context.add_init_script(STEALTH_INIT_SCRIPT)
            await self._warmup_session()

    async def _warmup_session(self) -> None:
        # Establish a Seek session before fetching individual job pages.
        if self._context is None:
            return

        page = await self._context.new_page()
        goto_timeout, _ = _detail_timeouts()
        try:
            self.logger.info("Warming up Seek session")
            page.set_default_timeout(goto_timeout)
            await page.goto(
                "https://www.seek.com.au",
                wait_until="domcontentloaded",
                timeout=goto_timeout,
            )
            await dismiss_consent_if_present(page, self.logger, site="generic")
        finally:
            await self._close_page(page)

    async def close(self) -> None:
        # Close the browser after all in-flight detail tasks finish.
        if self._closing and self._browser is None:
            return

        self._closing = True
        await self._wait_for_active_fetches()
        await self._close_open_pages()

        if self._context is not None:
            await self._context.close()
            self._context = None

        if self._browser is not None:
            await self._browser.close()
            self._browser = None

        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def _wait_for_active_fetches(self) -> None:
        # Wait until no detail fetch tasks are still using the browser.
        while True:
            async with self._active_lock:
                if self._active_fetches == 0:
                    return
            await asyncio.sleep(0.05)

    async def _close_open_pages(self) -> None:
        # Close any pages still tracked as open.
        pages = list(self._open_pages)
        for page in pages:
            await self._close_page(page)

    async def fetch_job(self, url: str) -> str | None:
        # Fetch the raw HTML content of a job detail page.
        await self.start()
        return await self._fetch_job_once(url)

    async def fetch_jobs_concurrent(
        self,
        urls: list[str],
        concurrency: int | None = None,
    ) -> tuple[list[str | None], DetailCrawlStats]:
        # Fetch multiple job pages concurrently with bounded parallelism.
        await self.start()
        self._closing = False
        self._diagnostics_saved = 0
        self._abort_detail_crawl = False
        self._verification_blocked = 0
        self._verification_blocked = 0

        limit = concurrency or config.SEEK_DETAIL_CONCURRENCY
        semaphore = asyncio.Semaphore(limit)
        stats = DetailCrawlStats(total=len(urls))
        results: list[str | None] = [None] * len(urls)

        async def _fetch_one(index: int, url: str) -> None:
            async with semaphore:
                if self._closing or self._abort_detail_crawl:
                    results[index] = None
                    stats.failed += 1
                    return

                async with self._active_lock:
                    self._active_fetches += 1

                started = time.perf_counter()
                try:
                    html = await self._fetch_job_once(url)
                    results[index] = html
                    if html is None:
                        stats.failed += 1
                    else:
                        stats.successful += 1
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.logger.error(
                        f"Job fetch failed for {url}: {format_fetch_error(exc)}"
                    )
                    results[index] = None
                    stats.failed += 1
                finally:
                    elapsed = time.perf_counter() - started
                    stats.per_job_seconds.append(elapsed)
                    stats.total_seconds += elapsed
                    async with self._active_lock:
                        self._active_fetches -= 1

        tasks = [
            asyncio.create_task(_fetch_one(index, url))
            for index, url in enumerate(urls)
        ]
        task_outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        for index, outcome in enumerate(task_outcomes):
            if isinstance(outcome, Exception):
                self.logger.error(
                    f"Uncollected task exception for job index {index}: "
                    f"{format_fetch_error(outcome)}"
                )
                results[index] = None

        stats.verification_blocked = self._verification_blocked
        stats.aborted_early = self._abort_detail_crawl
        return results, stats

    async def _fetch_job_once(self, url: str) -> str | None:
        # Fetch one job without calling start(); safe for concurrent use.
        if self._closing or self._context is None:
            return None

        last_error: Exception | None = None

        for attempt in range(1, MAX_TRANSIENT_RETRIES + 1):
            if attempt > 1:
                self.logger.warning(f"Retry {attempt}")

            try:
                html = await self._fetch_page(url)
                self.logger.info("Job fetched")
                return html
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                if not is_retryable_error(exc):
                    self.logger.error(
                        f"Job fetch failed for {url}: {format_fetch_error(exc)}"
                    )
                    return None
                if attempt == MAX_TRANSIENT_RETRIES:
                    break

        if last_error is not None:
            self.logger.error(
                f"Failed after retries for {url}: {format_fetch_error(last_error)}"
            )
        else:
            self.logger.error(f"Failed after retries for {url}")
        return None

    async def _save_failure_diagnostics(
        self,
        page: Page,
        url: str,
        phase: str,
    ) -> None:
        # Save screenshot/HTML for the first few failed detail pages.
        if self._diagnostics_saved >= config.SEEK_DETAIL_DIAGNOSTICS_LIMIT:
            return

        if page.is_closed():
            return

        job_id = job_id_from_url(url)
        prefix = f"seek-detail-{job_id}-{phase}"
        self.logger.error(
            f"Saving Seek detail diagnostics for {url} (failed during {phase})"
        )
        try:
            await save_page_diagnostics(page, self.logger, prefix=prefix)
            self._diagnostics_saved += 1
        except Exception as exc:
            self.logger.warning(
                f"Could not save Seek detail diagnostics: {format_fetch_error(exc)}"
            )

    async def _fetch_page(self, url: str) -> str:
        # Open a job page and return its HTML content.
        if self._context is None or self._closing:
            raise RuntimeError("Browser context is not available")

        page: Page | None = None
        goto_timeout, selector_timeout = _detail_timeouts()
        phase = "navigation"

        try:
            self.logger.info(f"Opening job page: {url}")
            page = await self._context.new_page()
            self._open_pages.add(page)
            page.set_default_timeout(selector_timeout)

            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=goto_timeout,
            )
            await page.wait_for_load_state("load", timeout=goto_timeout)
            if await is_verification_page(page):
                await self._save_failure_diagnostics(page, url, "verification")
                self._abort_detail_crawl = True
                self._verification_blocked += 1
                raise RuntimeError("Seek human verification page detected")
            await dismiss_consent_if_present(
                page,
                self.logger,
                site="generic",
                results_selector=JOB_DETAIL_SELECTOR,
            )
            phase = "selector"
            await page.wait_for_selector(
                JOB_DETAIL_SELECTOR,
                state="attached",
                timeout=selector_timeout,
            )
            return await page.content()
        except PlaywrightTimeoutError as exc:
            if page is not None and not page.is_closed():
                await self._save_failure_diagnostics(page, url, phase)
            raise RuntimeError(
                f"timeout during {phase} "
                f"(goto={goto_timeout}ms, selector={selector_timeout}ms, "
                f"total={goto_timeout + selector_timeout}ms)"
            ) from exc
        except Exception:
            if page is not None and not page.is_closed():
                await self._save_failure_diagnostics(page, url, phase)
            raise
        finally:
            await self._close_page(page)

    async def _close_page(self, page: Page | None) -> None:
        # Close a page without letting cleanup errors escape.
        if page is None:
            return

        self._open_pages.discard(page)
        try:
            if not page.is_closed():
                await page.close()
        except Exception as exc:
            self.logger.warning(f"Page close failed: {format_fetch_error(exc)}")

    async def __aenter__(self) -> "JobDetailCrawler":
        # Enter async context and start the browser.
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        # Exit async context and close the browser.
        await self.close()
