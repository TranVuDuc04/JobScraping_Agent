# Seek job detail fetcher using undetected-chromedriver.

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import config
from crawler.diagnostics import VERIFICATION_MARKERS, job_id_from_url
from crawler.job_detail import DetailCrawlStats, format_fetch_error
from utils.logger import Logger

if TYPE_CHECKING:
    import undetected_chromedriver as uc
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.support.ui import WebDriverWait

JOB_DETAIL_SELECTOR = (
    '[data-automation="job-detail-title"], '
    '[data-automation="jobAdDetails"]'
)


def _page_is_verification(title: str, html: str) -> bool:
    # Return True when page content looks like a bot challenge.
    lowered_title = title.lower()
    lowered_html = html.lower()
    return any(
        marker in lowered_title or marker in lowered_html
        for marker in VERIFICATION_MARKERS
    )


def _build_chrome_options():
    # Build Chrome options for undetected-chromedriver.
    uc = _import_undetected_chromedriver()

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=en-AU")
    if config.HEADLESS:
        options.add_argument("--headless=new")
    return options


def _wait_for_job_detail(driver: WebDriver, timeout_seconds: float) -> None:
    # Wait until Seek job detail markers appear.
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    WebDriverWait(driver, timeout_seconds).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, JOB_DETAIL_SELECTOR))
    )


def _import_undetected_chromedriver():
    # Import undetected-chromedriver, raising a clear error on Python 3.12+.
    try:
        import undetected_chromedriver as uc
    except ModuleNotFoundError as exc:
        if exc.name == "distutils":
            raise RuntimeError(
                "undetected-chromedriver needs setuptools on Python 3.12+ "
                "(pip install setuptools)"
            ) from exc
        raise
    return uc


def _fetch_jobs_sync(urls: list[str], logger: Logger) -> tuple[list[str | None], DetailCrawlStats]:
    # Fetch Seek detail pages sequentially with one undetected Chrome session.
    uc = _import_undetected_chromedriver()

    stats = DetailCrawlStats(total=len(urls))
    results: list[str | None] = [None] * len(urls)
    timeout_seconds = config.SEEK_DETAIL_TIMEOUT / 1000
    driver: WebDriver | None = None

    try:
        logger.info("Starting undetected Chrome for Seek detail pages")
        driver = uc.Chrome(options=_build_chrome_options())
        driver.set_page_load_timeout(timeout_seconds)

        logger.info("Warming up Seek session (undetected Chrome)")
        driver.get("https://www.seek.com.au")
        time.sleep(2)

        for index, url in enumerate(urls):
            if stats.aborted_early:
                stats.failed += 1
                continue

            started = time.perf_counter()
            try:
                logger.info(f"Opening job page (UC): {url}")
                driver.get(url)

                title = driver.title
                html = driver.page_source
                if _page_is_verification(title, html):
                    stats.verification_blocked += 1
                    stats.aborted_early = True
                    logger.error(
                        f"Seek human verification detected on {url} - "
                        "stopping undetected Chrome detail crawl"
                    )
                    stats.failed += 1
                    continue

                _wait_for_job_detail(driver, timeout_seconds)
                html = driver.page_source
                if _page_is_verification(driver.title, html):
                    stats.verification_blocked += 1
                    stats.aborted_early = True
                    logger.error(f"Seek verification after wait on {url}")
                    stats.failed += 1
                    continue

                if 'data-automation="job-detail-title"' not in html:
                    raise RuntimeError("job detail markers missing from page HTML")

                results[index] = html
                stats.successful += 1
                logger.info("Job fetched")
            except Exception as exc:
                stats.failed += 1
                logger.error(
                    f"UC job fetch failed for {url}: {format_fetch_error(exc)}"
                )
            finally:
                stats.per_job_seconds.append(time.perf_counter() - started)
                stats.total_seconds += stats.per_job_seconds[-1]

        return results, stats
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception as exc:
                logger.warning(f"UC driver quit failed: {format_fetch_error(exc)}")


async def fetch_seek_details_uc(
    urls: list[str],
    logger: Logger,
) -> tuple[list[str | None], DetailCrawlStats]:
    # Fetch Seek detail HTML using undetected-chromedriver in a worker thread.
    return await asyncio.to_thread(_fetch_jobs_sync, urls, logger)
