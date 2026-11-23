# Shared Playwright browser configuration for local and CI environments.

import platform

BROWSER_ARGS: list[str] = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]

USER_AGENTS: dict[str, str] = {
    "darwin": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "linux": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

STEALTH_INIT_SCRIPT = (
    "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
)


def get_user_agent() -> str:
    # Return a platform-appropriate desktop Chrome user agent.
    system = platform.system().lower()
    return USER_AGENTS.get(system, USER_AGENTS["linux"])


def get_context_options() -> dict[str, object]:
    # Return browser context options aligned with Seek's AU audience.
    return {
        "user_agent": get_user_agent(),
        "viewport": {"width": 1920, "height": 1080},
        "locale": "en-AU",
        "timezone_id": "Australia/Melbourne",
        "geolocation": {"latitude": -37.8136, "longitude": 144.9631},
        "permissions": ["geolocation"],
        "extra_http_headers": {"Accept-Language": "en-AU,en;q=0.9"},
    }
