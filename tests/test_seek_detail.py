"""Tests for Seek detail crawler optimizations."""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from crawler.job_detail import (
    DetailCrawlStats,
    JobDetailCrawler,
    format_fetch_error,
    is_retryable_error,
)
from crawler.seek_api import SeekListing, filter_recent_listings, is_listing_recent

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
except ImportError:  # pragma: no cover - allows running without Playwright installed
    class PlaywrightTimeoutError(TimeoutError):
        pass


def _listing(job_id: str, iso_date: str, display: str | None = None) -> SeekListing:
    return SeekListing(
        job_id=job_id,
        title=f"Job {job_id}",
        company="Acme",
        location="Melbourne VIC",
        url=f"https://www.seek.com.au/job/{job_id}",
        listing_date=iso_date,
        listing_date_display=display,
        salary_label=None,
        employment_type="Full time",
        teaser=None,
    )


def test_filter_recent_listings_skips_old_jobs() -> None:
    """Test A: only recent jobs remain after API pre-filtering."""
    now = datetime.now(timezone.utc)
    recent_listings = []
    for index in range(34):
        days_old = index % 3  # 0, 1, or 2 days old
        recent_listings.append(
            _listing(
                f"recent-{index}",
                (now - timedelta(days=days_old, hours=index % 12)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        )
    old_listings = [
        _listing(
            f"old-{index}",
            (now - timedelta(days=3 + index)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        for index in range(200)
    ]
    listings = recent_listings + old_listings

    recent = filter_recent_listings(listings, max_days=2)

    assert len(listings) == 234
    assert len(recent) == 34
    assert len(listings) - len(recent) == 200


def test_is_listing_recent_uses_iso_date() -> None:
    now = datetime.now(timezone.utc)
    recent = _listing("1", (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    old = _listing("2", (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ"))

    assert is_listing_recent(recent, max_days=2) is True
    assert is_listing_recent(old, max_days=2) is False


def test_retryable_error_classification() -> None:
    assert is_retryable_error(PlaywrightTimeoutError("Timeout 20000ms exceeded")) is False
    assert is_retryable_error(TimeoutError()) is False
    assert is_retryable_error(Exception("net::ERR_CONNECTION_RESET")) is True
    assert is_retryable_error(Exception("HTTP 503 temporarily unavailable")) is True
    assert is_retryable_error(Exception("net::ERR_BLOCKED_BY_CLIENT")) is False


def test_format_fetch_error_handles_empty_timeout() -> None:
    assert format_fetch_error(TimeoutError()) == "TimeoutError"
    formatted = format_fetch_error(PlaywrightTimeoutError("Timeout 8000ms exceeded"))
    assert "8000ms" in formatted


def test_detail_timeouts_split_budget() -> None:
    goto_timeout, selector_timeout = __import__(
        "crawler.job_detail", fromlist=["_detail_timeouts"]
    )._detail_timeouts()
    assert goto_timeout + selector_timeout == config.SEEK_DETAIL_TIMEOUT
    assert goto_timeout >= 5000
    assert selector_timeout >= 5000


async def _run_fetch_jobs_concurrent(urls: list[str]) -> tuple[list[str | None], DetailCrawlStats]:
    crawler = JobDetailCrawler()

    async def fake_fetch(url: str) -> str | None:
        if url.endswith("/fail"):
            return None
        return f"<html>{url}</html>"

    with patch.object(crawler, "start", new=AsyncMock()), patch.object(
        crawler, "_fetch_job_once", side_effect=fake_fetch
    ):
        return await crawler.fetch_jobs_concurrent(urls, concurrency=3)


def test_one_failed_detail_page_does_not_stop_others() -> None:
    """Test B: one failed job is skipped and the rest continue."""
    urls = [
        "https://www.seek.com.au/job/1",
        "https://www.seek.com.au/job/fail",
        "https://www.seek.com.au/job/3",
    ]

    results, stats = asyncio.run(_run_fetch_jobs_concurrent(urls))

    assert results[0] is not None
    assert results[1] is None
    assert results[2] is not None
    assert stats.total == 3
    assert stats.successful == 2
    assert stats.failed == 1


def test_multiple_failures_finish_without_long_waits() -> None:
    """Test C: several failures should complete quickly with mocked fetches."""
    urls = [f"https://www.seek.com.au/job/{index}" for index in range(6)]

    async def slow_or_fail(url: str) -> str | None:
        await asyncio.sleep(0.05)
        if url.endswith("/2") or url.endswith("/4"):
            return None
        return f"<html>{url}</html>"

    crawler = JobDetailCrawler()
    with patch.object(crawler, "start", new=AsyncMock()), patch.object(
        crawler, "_fetch_job_once", side_effect=slow_or_fail
    ):
        started = time.perf_counter()
        _, stats = asyncio.run(crawler.fetch_jobs_concurrent(urls, concurrency=4))
        elapsed = time.perf_counter() - started

    assert stats.failed == 2
    assert stats.successful == 4
    assert elapsed < 1.0


def test_detail_stats_average_time() -> None:
    stats = DetailCrawlStats(
        total=3,
        successful=2,
        failed=1,
        total_seconds=3.0,
        per_job_seconds=[1.0, 1.0, 1.0],
    )

    assert stats.average_seconds == 1.0


def test_gather_collects_task_exceptions() -> None:
    """Task exceptions must be collected without aborting sibling fetches."""

    async def run() -> None:
        crawler = JobDetailCrawler()
        call_count = 0

        async def flaky_fetch(url: str) -> str | None:
            nonlocal call_count
            call_count += 1
            if url.endswith("/boom"):
                raise RuntimeError("simulated task failure")
            return f"<html>{url}</html>"

        with patch.object(crawler, "start", new=AsyncMock()), patch.object(
            crawler, "_fetch_job_once", side_effect=flaky_fetch
        ):
            results, stats = await crawler.fetch_jobs_concurrent(
                [
                    "https://www.seek.com.au/job/1",
                    "https://www.seek.com.au/job/boom",
                    "https://www.seek.com.au/job/3",
                ],
                concurrency=2,
            )

        assert call_count == 3
        assert results[0] is not None
        assert results[1] is None
        assert results[2] is not None
        assert stats.failed == 1
        assert stats.successful == 2

    asyncio.run(run())


def test_listing_to_job_uses_api_metadata() -> None:
    listing = SeekListing(
        job_id="123",
        title="Junior Developer",
        company="Acme",
        location="Melbourne VIC",
        url="https://www.seek.com.au/job/123",
        listing_date="2026-08-06T01:30:05Z",
        listing_date_display="1d ago",
        salary_label="$80k",
        employment_type="Full time",
        teaser="Build features with Python and React.",
    )
    from crawler.seek_api import listing_to_job

    job = listing_to_job(listing)
    assert job.title == "Junior Developer"
    assert job.company == "Acme"
    assert job.description == "Build features with Python and React."
    assert job.posted_date == "1d ago"
    assert job.source == "Seek"


def test_page_is_verification_detects_human_check() -> None:
    from crawler.seek_detail_uc import _page_is_verification

    assert _page_is_verification("Human Verification", "<html></html>") is True
    assert _page_is_verification("Job Details", "<html>job-detail-title</html>") is False


if __name__ == "__main__":
    tests = [
        test_filter_recent_listings_skips_old_jobs,
        test_is_listing_recent_uses_iso_date,
        test_retryable_error_classification,
        test_format_fetch_error_handles_empty_timeout,
        test_detail_timeouts_split_budget,
        test_listing_to_job_uses_api_metadata,
        test_page_is_verification_detects_human_check,
        test_one_failed_detail_page_does_not_stop_others,
        test_multiple_failures_finish_without_long_waits,
        test_detail_stats_average_time,
        test_gather_collects_task_exceptions,
    ]
    passed = 0
    for test in tests:
        test()
        passed += 1
        print(f"PASS: {test.__name__}")

    print(f"\n{passed}/{len(tests)} tests passed")
