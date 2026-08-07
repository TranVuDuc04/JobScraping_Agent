#!/usr/bin/env python3
"""Standalone Indeed crawler test — does not run Seek/LinkedIn or Discord."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _ensure_dependencies() -> None:
    for package in ("playwright", "dotenv", "bs4", "requests"):
        try:
            __import__(package)
        except ModuleNotFoundError as exc:
            print(f"Missing dependency: {exc.name}")
            print("Run: pip install -r requirements.txt")
            sys.exit(1)


_ensure_dependencies()

import config
from crawler.indeed import IndeedCrawler


async def main() -> None:
    print("Indeed crawler test")
    print(f"  HEADLESS={config.HEADLESS}")
    print(f"  INDEED_USE_UNDETECTED_CHROME={config.INDEED_USE_UNDETECTED_CHROME}")
    print(f"  Keywords: {config.INDEED_SEARCH_KEYWORDS}")
    print(f"  Location: {config.INDEED_SEARCH_LOCATION}")
    print()

    try:
        jobs = await IndeedCrawler().crawl()
    except Exception as exc:
        print(f"FAILED: {exc}")
        print("\nTips:")
        print("  HEADLESS=false python scripts/test_indeed.py")
        print("  INDEED_USE_UNDETECTED_CHROME=false  # if Playwright works but UC SSL fails")
        print("  pip install setuptools certifi")
        print("  /Applications/Python\\ 3.12/Install\\ Certificates.command  # macOS SSL")
        sys.exit(1)

    print(f"SUCCESS: {len(jobs)} jobs found\n")
    for index, job in enumerate(jobs[:15], start=1):
        print(f"{index}. {job.title}")
        print(f"   {job.company} | {job.location or 'N/A'}")
        print(f"   {job.url}\n")

    if len(jobs) > 15:
        print(f"... and {len(jobs) - 15} more")


if __name__ == "__main__":
    asyncio.run(main())
