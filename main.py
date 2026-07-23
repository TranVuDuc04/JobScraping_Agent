"""AI Job Agent entry point."""

import sys


def _ensure_dependencies() -> None:
    """Verify required packages are installed before importing project modules."""
    missing: list[str] = []
    for package in ("playwright", "dotenv", "bs4", "requests"):
        try:
            __import__(package)
        except ModuleNotFoundError:
            missing.append(package)

    if not missing:
        return

    print("ERROR\n")
    print("Required dependencies are not installed in the current Python environment.")
    print(f"Missing packages: {', '.join(missing)}\n")
    print("Set up the project virtual environment:")
    print("  cd jobscraping_aiagent")
    print("  python3 -m venv .venv")
    print("  source .venv/bin/activate")
    print("  pip install -r requirements.txt")
    print("  python -m playwright install chromium")
    print("\nThen run:")
    print("  python main.py")
    sys.exit(1)


_ensure_dependencies()

import asyncio
import time
from dataclasses import dataclass

import config
from crawler.job_detail import JobDetailCrawler
from crawler.seek import SeekCrawler
from notifier.discord import DiscordNotifier
from parser.parser import JobParser
from rules.engine import RuleEngine
from storage.duplicate_checker import DuplicateChecker
from utils.logger import Logger


@dataclass
class RunStats:
    """Tracks pipeline execution metrics."""

    crawled: int = 0
    parsed: int = 0
    matched: int = 0
    duplicates: int = 0
    new_jobs: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0


async def process_job(
    url: str,
    detail_crawler: JobDetailCrawler,
    parser: JobParser,
    engine: RuleEngine,
    notifier: DiscordNotifier,
    duplicate_checker: DuplicateChecker,
    logger: Logger,
    stats: RunStats,
) -> None:
    """Fetch, parse, evaluate, and optionally notify for one job URL."""
    try:
        html = await detail_crawler.fetch_job(url)
        if not html:
            stats.errors += 1
            return
        job = parser.parse(html, url)
        stats.parsed += 1
        logger.info("Job parsed")
        matched, reasons = engine.evaluate(job)
        if not matched:
            stats.skipped += 1
            logger.info("Rule Engine rejected")
            logger.info("Skip notification")
            return
        stats.matched += 1
        logger.info("Rule Engine passed")
        logger.info("Duplicate check")
        if duplicate_checker.is_sent(job.url):
            stats.duplicates += 1
            logger.info("Duplicate job detected")
            logger.info("Skip notification")
            return
        stats.new_jobs += 1
        logger.info("New job")
        logger.info("Sending Discord notification")
        try:
            notifier.send(job, reasons)
            stats.sent += 1
            duplicate_checker.mark_sent(job.url)
            logger.info("Marked as sent")
            logger.info("Notification sent")
        except Exception as exc:
            stats.failed += 1
            stats.errors += 1
            logger.error(f"Discord notification failed: {exc}")
        logger.info("Finished processing job")
    except Exception as exc:
        stats.errors += 1
        logger.error(f"Failed to process job {url}: {exc}")


def print_summary(stats: RunStats, elapsed: float) -> None:
    """Print the run summary report."""
    border = "===================================="
    print(f"{border}\nRUN SUMMARY\nJobs Crawled: {stats.crawled}")
    print(f"Jobs Parsed: {stats.parsed}\nMatched Jobs: {stats.matched}")
    print(f"Duplicate Jobs: {stats.duplicates}\nNew Jobs: {stats.new_jobs}")
    print(f"Notifications Sent: {stats.sent}\nNotifications Failed: {stats.failed}")
    print(f"Skipped: {stats.skipped}\nErrors: {stats.errors}")
    print(f"Execution Time: {elapsed:.1f}s\n{border}")


async def run() -> None:
    """Execute the full crawl-to-Discord pipeline."""
    start = time.perf_counter()
    logger, stats = Logger("main"), RunStats()
    duplicate_checker = DuplicateChecker()
    duplicate_checker.load()
    urls = await SeekCrawler().crawl()
    stats.crawled = len(urls)
    parser, engine = JobParser(), RuleEngine()
    notifier = DiscordNotifier(config.DISCORD_WEBHOOK)
    try:
        async with JobDetailCrawler() as detail_crawler:
            for url in urls:
                await process_job(
                    url, detail_crawler, parser, engine, notifier,
                    duplicate_checker, logger, stats,
                )
    finally:
        duplicate_checker.save()
    print_summary(stats, time.perf_counter() - start)


def main() -> None:
    """Initialize and execute the application."""
    config.exit_if_invalid()
    asyncio.run(run())


if __name__ == "__main__":
    main()
