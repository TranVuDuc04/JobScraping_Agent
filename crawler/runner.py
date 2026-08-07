"""Fault-tolerant multi-source crawler runner."""

import traceback
from dataclasses import dataclass

import config
from crawler.base import BaseCrawler
from models.job import Job
from utils.logger import Logger


@dataclass
class SourceResult:
    """Outcome from a single job source crawler."""

    source: str
    job_count: int
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        """Return True when the crawler completed without error."""
        return self.error is None


async def run_crawlers(
    crawlers: list[BaseCrawler],
    logger: Logger,
) -> tuple[list[Job], list[SourceResult]]:
    """Run all crawlers independently and combine successful results."""
    all_jobs: list[Job] = []
    results: list[SourceResult] = []

    for crawler in crawlers:
        source = crawler.source_name
        logger.info(f"Starting {source}...")
        try:
            jobs = await crawler.crawl()
            logger.info(f"Finished {source} ({len(jobs)} jobs)")
            results.append(SourceResult(source=source, job_count=len(jobs)))
            all_jobs.extend(jobs)
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            logger.error(f"{source} failed: {message}")
            if config.DEBUG:
                logger.error(traceback.format_exc())
            results.append(SourceResult(source=source, job_count=0, error=message))

    return all_jobs, results


def dedupe_jobs(jobs: list[Job]) -> list[Job]:
    """Remove duplicate jobs across sources by URL and title/company fingerprint."""
    seen_urls: set[str] = set()
    seen_fingerprints: set[str] = set()
    unique_jobs: list[Job] = []

    for job in jobs:
        fingerprint = f"{job.title.lower().strip()}|{job.company.lower().strip()}"
        if job.url in seen_urls or fingerprint in seen_fingerprints:
            continue
        seen_urls.add(job.url)
        seen_fingerprints.add(fingerprint)
        unique_jobs.append(job)

    return unique_jobs


def format_source_summary(results: list[SourceResult]) -> str:
    """Format crawler source results for terminal output."""
    lines = ["Sources", ""]
    for result in results:
        if result.succeeded:
            lines.append(f"✅ {result.source} ({result.job_count} jobs)")
        else:
            lines.append(f"❌ {result.source}")
            lines.append(f"Reason: {result.error}")
    return "\n".join(lines)


def failed_sources(results: list[SourceResult]) -> list[str]:
    """Return source names that failed during crawling."""
    return [result.source for result in results if not result.succeeded]


def failed_source_details(results: list[SourceResult]) -> list[tuple[str, str]]:
    """Return failed sources with their error messages."""
    return [
        (result.source, result.error or "unknown error")
        for result in results
        if not result.succeeded
    ]
