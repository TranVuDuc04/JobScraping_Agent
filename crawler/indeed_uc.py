# Indeed crawler using undetected-chromedriver.

from __future__ import annotations

import asyncio
import time
from urllib.parse import quote_plus

import config
from crawler.diagnostics import save_page_diagnostics_sync
from crawler.uc_browser import (
    build_chrome_options,
    format_fetch_error,
    import_undetected_chromedriver,
    page_is_verification,
)
from models.job import Job
from utils.logger import Logger

INDEED_JOB_SELECTOR = (
    "#mosaic-provider-jobcards a[data-jk], "
    "#mosaic-provider-jobcards h2.jobTitle a, "
    "div.job_seen_beacon, div.cardOutline, a.jcs-JobTitle"
)

EXTRACT_JOBS_SCRIPT = """
const elements = document.querySelectorAll(
    '#mosaic-provider-jobcards div.job_seen_beacon, ' +
    '#mosaic-provider-jobcards div.cardOutline, ' +
    'div.job_seen_beacon, div.cardOutline, td.resultContent'
);
return Array.from(elements).map(el => {
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
}).filter(Boolean);
"""


def _build_search_url() -> str:
    query = quote_plus(config.INDEED_SEARCH_KEYWORDS)
    location = quote_plus(config.INDEED_SEARCH_LOCATION)
    return f"https://au.indeed.com/jobs?q={query}&l={location}"


def _cards_to_jobs(cards: list[dict], source_name: str = "Indeed") -> list[Job]:
    seen: set[str] = set()
    jobs: list[Job] = []

    for card in cards:
        href = card.get("href", "")
        url = href if href.startswith("http") else f"https://au.indeed.com{href}"
        if url in seen:
            continue
        seen.add(url)
        jobs.append(
            Job(
                title=card.get("title", ""),
                company=card.get("company") or "Unknown",
                location=card.get("location") or None,
                salary=card.get("salary") or None,
                employment_type=None,
                description=card.get("title", ""),
                url=url,
                source=source_name,
                posted_date=None,
            )
        )

    return jobs


def _dismiss_indeed_consent(driver, logger: Logger) -> None:
    # Click Indeed OneTrust cookie banner when visible.
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    selectors = (
        "#onetrust-accept-btn-handler",
        "button#onetrust-accept-btn-handler",
    )
    for selector in selectors:
        try:
            button = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            button.click()
            logger.info("Indeed: consent accepted")
            time.sleep(1)
            return
        except TimeoutException:
            continue
        except Exception as exc:
            logger.warning(f"Indeed: consent click failed: {format_fetch_error(exc)}")
            return


def _wait_for_indeed_results(driver, logger: Logger, timeout_seconds: float) -> bool:
    # Wait for Cloudflare/Indeed challenge to clear and job cards to appear.
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    deadline = time.time() + timeout_seconds
    last_log = 0.0

    while time.time() < deadline:
        title = driver.title
        html = driver.page_source
        elapsed = int(time.time() - (deadline - timeout_seconds))

        if page_is_verification(title, html):
            if time.time() - last_log > 5:
                logger.info(
                    f"Indeed challenge page detected ({title!r}) - waiting to clear..."
                )
                last_log = time.time()
            time.sleep(2)
            continue

        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, INDEED_JOB_SELECTOR))
            )
            return True
        except Exception:
            time.sleep(2)

    return False


def _crawl_indeed_sync(logger: Logger) -> list[Job]:
    # Fetch Indeed listings with one undetected Chrome session.
    import_undetected_chromedriver()
    search_url = _build_search_url()
    timeout_seconds = config.PLAYWRIGHT_TIMEOUT / 1000
    driver = None

    try:
        logger.info("Starting undetected Chrome for Indeed")
        uc = import_undetected_chromedriver()
        driver = uc.Chrome(options=build_chrome_options())
        driver.set_page_load_timeout(timeout_seconds)

        logger.info("Warming up Indeed session")
        driver.get("https://au.indeed.com")
        time.sleep(2)

        logger.info(f"Opening Indeed search: {search_url}")
        driver.get(search_url)
        _dismiss_indeed_consent(driver, logger)

        if not _wait_for_indeed_results(driver, logger, timeout_seconds):
            save_page_diagnostics_sync(driver, logger, prefix="Indeed-uc")
            raise RuntimeError("Indeed challenge did not clear or job results not found")

        cards = driver.execute_script(EXTRACT_JOBS_SCRIPT) or []
        jobs = _cards_to_jobs(cards)
        logger.info(f"Found {len(jobs)} jobs")
        return jobs
    except Exception as exc:
        if driver is not None:
            try:
                save_page_diagnostics_sync(driver, logger, prefix="Indeed-uc-error")
            except Exception:
                pass
        raise RuntimeError(format_fetch_error(exc)) from exc
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception as exc:
                logger.warning(f"UC driver quit failed: {format_fetch_error(exc)}")


async def crawl_indeed_uc(logger: Logger) -> list[Job]:
    # Async wrapper for Indeed undetected-chromedriver crawl.
    return await asyncio.to_thread(_crawl_indeed_sync, logger)
