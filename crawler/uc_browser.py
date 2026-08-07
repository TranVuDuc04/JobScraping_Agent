"""Shared undetected-chromedriver helpers."""

from __future__ import annotations

import config

VERIFICATION_MARKERS = (
    "human verification",
    "verify you are human",
    "verify you're human",
    "just a moment",
    "cf-browser-verification",
    "challenge-platform",
    "px-captcha",
    "datadome",
    "recaptcha",
    "captcha",
    "access denied",
    "security check",
)


def ensure_ssl_certificates() -> None:
    """Use certifi CA bundle so UC can download ChromeDriver on macOS Python."""
    try:
        import os

        import certifi

        bundle = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", bundle)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", bundle)
    except ImportError:
        pass


def import_undetected_chromedriver():
    """Import undetected-chromedriver, raising a clear error on Python 3.12+."""
    ensure_ssl_certificates()
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


def build_chrome_options():
    """Build Chrome options for undetected-chromedriver."""
    uc = import_undetected_chromedriver()
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=en-AU")
    options.add_argument("--disable-blink-features=AutomationControlled")
    if config.HEADLESS:
        options.add_argument("--headless=new")
    return options


def page_is_verification(title: str, html: str) -> bool:
    """Return True when page content looks like a bot challenge."""
    lowered_title = title.lower()
    lowered_html = html.lower()
    return any(
        marker in lowered_title or marker in lowered_html
        for marker in VERIFICATION_MARKERS
    )


def format_fetch_error(exc: Exception) -> str:
    """Format an exception for logging."""
    message = str(exc).strip()
    if message:
        return f"{exc.__class__.__name__}: {message}"
    return exc.__class__.__name__
