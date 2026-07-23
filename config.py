"""Application configuration loaded from environment variables."""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK: str = os.getenv("DISCORD_WEBHOOK", "").strip()
HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"
PLAYWRIGHT_TIMEOUT: int = int(os.getenv("PLAYWRIGHT_TIMEOUT", "30000"))
SEEK_SEARCH_URL: str = (
    "https://www.seek.com.au/project-coordinator-jobs/in-All-Melbourne-VIC"
)


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
