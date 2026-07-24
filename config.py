"""Application configuration loaded from environment variables."""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK: str = os.getenv("DISCORD_WEBHOOK", "").strip()
HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"
PLAYWRIGHT_TIMEOUT: int = int(os.getenv("PLAYWRIGHT_TIMEOUT", "30000"))
DEBUG: bool = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")
USE_SEEK_API_FOR_URLS: bool = (
    os.getenv("USE_SEEK_API_FOR_URLS", "").lower() == "true"
    or os.getenv("CI", "").lower() == "true"
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
