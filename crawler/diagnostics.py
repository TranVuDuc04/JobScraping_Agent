# Save Playwright page diagnostics for failed crawls.

import re
from pathlib import Path

from playwright.async_api import Page

from utils.logger import Logger

ARTIFACTS_DIR = Path("artifacts")
JOB_ID_PATTERN = re.compile(r"/job/(\d+)")
VERIFICATION_MARKERS = (
    "human verification",
    "verify you are human",
    "verify you're human",
    "captcha",
    "recaptcha",
    "challenge-platform",
    "px-captcha",
    "datadome",
    "access denied",
)


async def is_verification_page(page: Page) -> bool:
    # Return True when the page looks like a bot/human verification challenge.
    title = (await page.title()).lower()
    html = (await page.content()).lower()
    return any(marker in title or marker in html for marker in VERIFICATION_MARKERS)


async def log_page_state(page: Page, logger: Logger, label: str = "") -> None:
    # Log URL, title, and a short HTML snippet for debugging.
    prefix = f"{label} " if label else ""
    title = await page.title()
    logger.error(f"{prefix}Current URL: {page.url}")
    logger.error(f"{prefix}Page title: {title}")

    html = await page.content()
    lowered = html.lower()
    markers = {
        "consent": "consent" in lowered or "onetrust" in lowered,
        "captcha": "captcha" in lowered or "recaptcha" in lowered,
        "security_check": "security check" in lowered or "just a moment" in lowered,
        "human_verification": "human verification" in lowered or "verify you are human" in lowered,
        "error_page": "error" in title.lower(),
        "seek_job_title": 'data-automation="job-detail-title"' in html,
        "seek_job_details": 'data-automation="jobaddetails"' in lowered,
    }
    logger.error(f"{prefix}Page markers: {markers}")
    logger.error(f"{prefix}HTML snippet: {html[:800]}")


def job_id_from_url(url: str) -> str:
    # Extract a Seek job ID from a detail URL.
    match = JOB_ID_PATTERN.search(url)
    return match.group(1) if match else "unknown"


def save_page_diagnostics_sync(driver, logger: Logger, prefix: str = "") -> None:
    # Persist screenshot and HTML from a Selenium WebDriver.
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    prefix_label = f"{prefix} " if prefix else ""
    title = driver.title
    url = driver.current_url
    html = driver.page_source
    lowered = html.lower()

    logger.error(f"{prefix_label}Current URL: {url}")
    logger.error(f"{prefix_label}Page title: {title}")
    logger.error(
        f"{prefix_label}Page markers: "
        f"{{'just_a_moment': {'just a moment' in title.lower()}, "
        f"'captcha': {'captcha' in lowered}, "
        f"'job_results': {'mosaic-provider-jobcards' in lowered or 'job_seen_beacon' in lowered}}}"
    )
    logger.error(f"{prefix_label}HTML snippet: {html[:800]}")

    slug = prefix.strip().replace(" ", "-").lower() or "page"
    screenshot_path = ARTIFACTS_DIR / f"{slug}-screenshot.png"
    html_path = ARTIFACTS_DIR / f"{slug}.html"
    driver.save_screenshot(str(screenshot_path))
    html_path.write_text(html, encoding="utf-8")
    logger.error(f"Saved screenshot to {screenshot_path}")
    logger.error(f"Saved HTML to {html_path}")


async def save_page_diagnostics(page: Page, logger: Logger, prefix: str = "") -> None:
    # Persist screenshot and HTML for debugging failed page loads.
    await log_page_state(page, logger, prefix)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    slug = prefix.strip().replace(" ", "-").lower() or "page"
    screenshot_path = ARTIFACTS_DIR / f"{slug}-screenshot.png"
    html_path = ARTIFACTS_DIR / f"{slug}.html"

    await page.screenshot(path=str(screenshot_path), full_page=True)
    html_path.write_text(await page.content(), encoding="utf-8")

    logger.error(f"Saved screenshot to {screenshot_path}")
    logger.error(f"Saved HTML to {html_path}")
