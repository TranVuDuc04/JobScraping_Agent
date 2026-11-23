# Robust cookie and modal consent handling for listing crawlers.

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

import config
from utils.logger import Logger

LINKEDIN_CONSENT_SELECTORS = (
    'div[role="dialog"] button:has-text("Accept"):visible',
    'div.artdeco-modal button:has-text("Accept"):visible',
    'button[data-test-id="accept-btn"]:visible',
    'button[data-control-name="accept"]:visible',
)

INDEED_CONSENT_SELECTORS = (
    'button#onetrust-accept-btn-handler:visible',
    'button:has-text("Accept All"):visible',
    'button:has-text("Accept all"):visible',
    'button:has-text("I Accept"):visible',
)

GENERIC_CONSENT_SELECTORS = (
    'button:has-text("Accept all"):visible',
    'button:has-text("Accept All"):visible',
    'button:has-text("Accept"):visible',
    'button:has-text("Agree"):visible',
)


async def dismiss_consent_if_present(
    page: Page,
    logger: Logger,
    *,
    site: str = "generic",
    results_selector: str | None = None,
) -> bool:
    # Dismiss a visible consent modal when present.
    timeout = config.CONSENT_ACTION_TIMEOUT

    if results_selector and await page.locator(results_selector).count() > 0:
        logger.info(f"{site}: search results already visible, skipping consent")
        return False

    selectors = _selectors_for_site(site)
    modal = page.locator(
        'div[role="dialog"]:visible, div.artdeco-modal:visible, '
        'div[class*="modal__overlay--visible"], #onetrust-banner-sdk:visible'
    )

    if await modal.count() == 0:
        for selector in selectors:
            button = page.locator(selector).first
            if await button.count() == 0:
                continue
            if not await button.is_visible():
                continue
            return await _click_consent_button(page, button, logger, site, timeout)

        logger.info(f"{site}: no consent modal detected")
        return False

    logger.info(f"{site}: consent modal detected")
    for selector in selectors:
        button = page.locator(selector).first
        if await button.count() == 0 or not await button.is_visible():
            continue
        clicked = await _click_consent_button(page, button, logger, site, timeout)
        if clicked:
            return True

    await _dismiss_blocking_overlay(page, logger, site, timeout)
    return False


def _selectors_for_site(site: str) -> tuple[str, ...]:
    if site == "linkedin":
        return LINKEDIN_CONSENT_SELECTORS
    if site == "indeed":
        return INDEED_CONSENT_SELECTORS
    return GENERIC_CONSENT_SELECTORS


async def _click_consent_button(
    page: Page,
    button,
    logger: Logger,
    site: str,
    timeout: int,
) -> bool:
    # Click a consent button with a short timeout, without blocking the crawl.
    try:
        await button.click(timeout=timeout)
        logger.info(f"{site}: consent accepted")
        return True
    except PlaywrightTimeoutError:
        logger.warning(f"{site}: consent click timed out after {timeout}ms")
    except Exception as exc:
        message = str(exc)
        if "intercepts pointer events" in message or "modal__overlay" in message:
            logger.warning(f"{site}: consent click blocked by overlay")
            await _dismiss_blocking_overlay(page, logger, site, timeout)
        else:
            logger.warning(f"{site}: consent click failed: {exc}")
    return False


async def _dismiss_blocking_overlay(
    page: Page,
    logger: Logger,
    site: str,
    timeout: int,
) -> None:
    # Try to dismiss a blocking overlay without stalling the crawl.
    dismiss_selectors = (
        'button.artdeco-modal__dismiss:visible',
        'button[aria-label="Dismiss"]:visible',
        'button[aria-label="Close"]:visible',
    )
    for selector in dismiss_selectors:
        button = page.locator(selector).first
        if await button.count() == 0 or not await button.is_visible():
            continue
        try:
            await button.click(timeout=timeout)
            logger.info(f"{site}: dismissed blocking overlay")
            return
        except Exception:
            continue

    try:
        await page.keyboard.press("Escape")
        logger.info(f"{site}: sent Escape to dismiss overlay")
    except Exception:
        pass
