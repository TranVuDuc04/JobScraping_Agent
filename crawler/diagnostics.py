"""Save Playwright page diagnostics for failed crawls."""

from pathlib import Path

from playwright.async_api import Page

from utils.logger import Logger

ARTIFACTS_DIR = Path("artifacts")


async def save_page_diagnostics(page: Page, logger: Logger) -> None:
    """Persist screenshot and HTML for debugging failed page loads."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    title = await page.title()
    logger.error(f"Current URL: {page.url}")
    logger.error(f"Page title: {title}")

    screenshot_path = ARTIFACTS_DIR / "screenshot.png"
    html_path = ARTIFACTS_DIR / "page.html"

    await page.screenshot(path=str(screenshot_path), full_page=True)
    html_path.write_text(await page.content(), encoding="utf-8")

    logger.error(f"Saved screenshot to {screenshot_path}")
    logger.error(f"Saved HTML to {html_path}")
