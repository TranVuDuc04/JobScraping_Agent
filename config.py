"""Application configuration loaded from environment variables."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _playwright_browser_cache_candidates() -> list[Path]:
    """Return common Playwright browser install locations."""
    home = Path.home()
    return [
        home / "Library" / "Caches" / "ms-playwright",
        home / ".cache" / "ms-playwright",
        home / "AppData" / "Local" / "ms-playwright",
    ]


def _playwright_cache_has_chromium(cache_dir: Path) -> bool:
    return cache_dir.is_dir() and any(cache_dir.glob("chromium-*"))


def ensure_playwright_browsers_path() -> None:
    """Use an installed Chromium cache when sandbox paths are empty."""
    configured = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if configured and _playwright_cache_has_chromium(Path(configured)):
        return

    for candidate in _playwright_browser_cache_candidates():
        if _playwright_cache_has_chromium(candidate):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(candidate)
            return


ensure_playwright_browsers_path()

DISCORD_WEBHOOK: str = os.getenv("DISCORD_WEBHOOK", "").strip()
INDEED_USE_UNDETECTED_CHROME: bool = os.getenv(
    "INDEED_USE_UNDETECTED_CHROME", "true"
).lower() in ("1", "true", "yes")
# Indeed UC needs a real browser window; headless mode is often blocked.
_default_headless = "false" if INDEED_USE_UNDETECTED_CHROME else "true"
HEADLESS: bool = os.getenv("HEADLESS", _default_headless).lower() == "true"
PLAYWRIGHT_TIMEOUT: int = int(os.getenv("PLAYWRIGHT_TIMEOUT", "30000"))
SEEK_DETAIL_TIMEOUT: int = int(
    os.getenv("SEEK_DETAIL_TIMEOUT", os.getenv("PLAYWRIGHT_TIMEOUT", "30000"))
)
SEEK_DETAIL_CONCURRENCY: int = int(os.getenv("SEEK_DETAIL_CONCURRENCY", "2"))
SEEK_DETAIL_DIAGNOSTICS_LIMIT: int = int(os.getenv("SEEK_DETAIL_DIAGNOSTICS_LIMIT", "3"))
SEEK_API_FALLBACK: bool = os.getenv("SEEK_API_FALLBACK", "true").lower() in ("1", "true", "yes")
SEEK_SKIP_DETAIL_CRAWL: bool = os.getenv("SEEK_SKIP_DETAIL_CRAWL", "true").lower() in (
    "1",
    "true",
    "yes",
)
SEEK_USE_UNDETECTED_CHROME: bool = os.getenv(
    "SEEK_USE_UNDETECTED_CHROME", ""
).lower() in ("1", "true", "yes")
CONSENT_ACTION_TIMEOUT: int = int(os.getenv("CONSENT_ACTION_TIMEOUT", "5000"))
DEBUG: bool = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")
USE_SEEK_API_FOR_URLS: bool = os.getenv("USE_SEEK_API_FOR_URLS", "true").lower() in (
    "1",
    "true",
    "yes",
)

INDEED_SEARCH_KEYWORDS: str = "junior software engineer"
INDEED_SEARCH_LOCATION: str = "Australia"
LINKEDIN_SEARCH_KEYWORDS: str = "junior software engineer"
LINKEDIN_SEARCH_LOCATION: str = "Australia"
SEEK_SEARCH_LOCATION: str = "Australia"
SEEK_SEARCH_KEYWORDS: list[str] = [
    "junior software engineer",
    "graduate software developer",
    "graduate developer",
    "entry level software engineer",
    "software engineer intern",
    "tech intern",
    "junior developer",
    "junior data analyst",
    "data analyst graduate",
    "business analyst graduate",
    "junior business analyst",
    "machine learning engineer",
    "ai engineer",
    "graduate data scientist",
    "part time software",
    "part time developer",
    "vacationer technology",
]

# Primary URL kept for backwards compatibility (first keyword search).
SEEK_SEARCH_URL: str = (
    f"https://www.seek.com.au/{SEEK_SEARCH_KEYWORDS[0].replace(' ', '-')}-jobs"
    f"/in-{SEEK_SEARCH_LOCATION.replace(' ', '-')}"
)


def get_seek_search_urls() -> list[str]:
    """Build Seek search result URLs for every configured keyword."""
    location_slug = SEEK_SEARCH_LOCATION.replace(" ", "-")
    return [
        f"https://www.seek.com.au/{keywords.replace(' ', '-')}-jobs/in-{location_slug}"
        for keywords in SEEK_SEARCH_KEYWORDS
    ]


def validate_config() -> bool:
    """Validate required configuration and print actionable errors.

    Returns:
        True if configuration is valid, False otherwise.
    """
    if DISCORD_WEBHOOK:
        return True

    print("ERROR\n")
    print("DISCORD_WEBHOOK is not configured.")
    print("\nPlease create a .env file based on .env.example.")
    return False


def exit_if_invalid() -> None:
    """Exit the application when required configuration is missing."""
    if not validate_config():
        sys.exit(1)
