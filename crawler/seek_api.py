"""Seek job search API client for URL discovery."""

from urllib.parse import urlparse

import requests

from crawler.browser_config import get_user_agent

SEEK_API_URL = "https://www.seek.com.au/api/jobsearch/v5/search"
DEFAULT_PAGE_SIZE = 30


def parse_search_url(search_url: str) -> tuple[str, str]:
    """Extract keywords and location slugs from a Seek search results URL."""
    path = urlparse(search_url).path.strip("/")
    segments = path.split("/")
    keywords = segments[0].removesuffix("-jobs").replace("-", " ")
    location = ""
    if len(segments) > 1:
        location = segments[1].removeprefix("in-").replace("-", " ")
    return keywords, location


def fetch_job_urls_for_query(
    keywords: str,
    location: str = "",
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[str]:
    """Fetch job detail URLs for a single keyword/location query."""
    params: dict[str, str | int] = {
        "keywords": keywords,
        "page": 1,
        "pageSize": page_size,
    }
    if location:
        params["where"] = location

    response = requests.get(
        SEEK_API_URL,
        params=params,
        headers={
            "Accept": "application/json",
            "Accept-Language": "en-AU,en;q=0.9",
            "User-Agent": get_user_agent(),
        },
        timeout=30,
    )
    response.raise_for_status()

    urls: list[str] = []
    for job in response.json().get("data", []):
        job_id = job.get("id")
        if job_id:
            urls.append(f"https://www.seek.com.au/job/{job_id}")
    return urls


def fetch_job_urls(search_url: str, page_size: int = DEFAULT_PAGE_SIZE) -> list[str]:
    """Fetch job detail URLs from a Seek search results URL."""
    keywords, location = parse_search_url(search_url)
    return fetch_job_urls_for_query(keywords, location, page_size)


def fetch_job_urls_for_keywords(
    keywords_list: list[str],
    location: str = "",
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[str]:
    """Fetch and deduplicate job URLs across multiple keyword searches."""
    seen: set[str] = set()
    urls: list[str] = []

    for keywords in keywords_list:
        for url in fetch_job_urls_for_query(keywords, location, page_size):
            if url not in seen:
                seen.add(url)
                urls.append(url)

    return urls
