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


def fetch_job_urls(search_url: str, page_size: int = DEFAULT_PAGE_SIZE) -> list[str]:
    """Fetch job detail URLs from Seek's public search API.

    Args:
        search_url: Seek search results page URL used to derive query params.
        page_size: Number of jobs to request from the API.

    Returns:
        A list of canonical Seek job detail URLs.
    """
    keywords, location = parse_search_url(search_url)
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

    payload = response.json()
    urls: list[str] = []
    seen: set[str] = set()

    for job in payload.get("data", []):
        job_id = job.get("id")
        if not job_id:
            continue
        url = f"https://www.seek.com.au/job/{job_id}"
        if url not in seen:
            seen.add(url)
            urls.append(url)

    return urls
