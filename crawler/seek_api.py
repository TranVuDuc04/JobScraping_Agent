# Seek job search API client for URL discovery.

from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from crawler.browser_config import get_user_agent
from models.job import Job
from rules import rule_config
from rules.filters import is_recent_job

SEEK_API_URL = "https://www.seek.com.au/api/jobsearch/v5/search"
DEFAULT_PAGE_SIZE = 30


@dataclass(frozen=True)
class SeekListing:
    # Metadata for a job returned by the Seek search API.

    job_id: str
    title: str
    company: str
    location: str | None
    url: str
    listing_date: str | None
    listing_date_display: str | None
    salary_label: str | None
    employment_type: str | None
    teaser: str | None


def listing_to_job(listing: SeekListing) -> Job:
    # Build a Job from Seek search API metadata when detail pages are unavailable.
    description = listing.teaser or listing.title
    posted_date = listing.listing_date_display
    if not posted_date and listing.listing_date:
        posted_date = listing.listing_date

    return Job(
        title=listing.title,
        company=listing.company,
        location=listing.location,
        salary=listing.salary_label,
        employment_type=listing.employment_type,
        description=description,
        url=listing.url,
        source="Seek",
        posted_date=posted_date,
    )


def parse_search_url(search_url: str) -> tuple[str, str]:
    # Extract keywords and location slugs from a Seek search results URL.
    path = urlparse(search_url).path.strip("/")
    segments = path.split("/")
    keywords = segments[0].removesuffix("-jobs").replace("-", " ")
    location = ""
    if len(segments) > 1:
        location = segments[1].removeprefix("in-").replace("-", " ")
    return keywords, location


def _parse_listing(job: dict) -> SeekListing | None:
    # Convert a Seek API job payload into a SeekListing.
    job_id = job.get("id")
    if not job_id:
        return None

    location = None
    locations = job.get("locations") or []
    if locations:
        location = locations[0].get("label")

    employer = job.get("employer") or {}
    work_types = job.get("workTypes") or []

    return SeekListing(
        job_id=str(job_id),
        title=job.get("title", ""),
        company=job.get("companyName") or employer.get("name") or "Unknown",
        location=location,
        url=f"https://www.seek.com.au/job/{job_id}",
        listing_date=job.get("listingDate"),
        listing_date_display=job.get("listingDateDisplay"),
        salary_label=job.get("salaryLabel") or None,
        employment_type=work_types[0] if work_types else None,
        teaser=job.get("teaser") or None,
    )


def _iso_age_days(iso_date: str) -> int | None:
    # Convert a Seek ISO listing date into whole days since posting.
    try:
        normalized = iso_date.replace("Z", "+00:00")
        posted = datetime.fromisoformat(normalized)
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - posted.astimezone(timezone.utc)
        return max(delta.days, 0)
    except ValueError:
        return None


def is_listing_recent(
    listing: SeekListing,
    max_days: int | None = None,
) -> bool:
    # Return True when a Seek API listing is within the allowed age window.
    max_age = max_days if max_days is not None else rule_config.MAX_JOB_AGE_DAYS

    if listing.listing_date:
        age_days = _iso_age_days(listing.listing_date)
        if age_days is not None:
            return age_days <= max_age

    if listing.listing_date_display:
        return is_recent_job(listing.listing_date_display, max_age)

    return True


def filter_recent_listings(
    listings: list[SeekListing],
    max_days: int | None = None,
) -> list[SeekListing]:
    # Keep only listings newer than the configured age limit.
    return [listing for listing in listings if is_listing_recent(listing, max_days)]


def fetch_job_listings_for_query(
    keywords: str,
    location: str = "",
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[SeekListing]:
    # Fetch job listings for a single keyword/location query.
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

    listings: list[SeekListing] = []
    for job in response.json().get("data", []):
        listing = _parse_listing(job)
        if listing is not None:
            listings.append(listing)
    return listings


def fetch_job_listings_for_keywords(
    keywords_list: list[str],
    location: str = "",
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[SeekListing]:
    # Fetch and deduplicate Seek listings across multiple keyword searches.
    seen: set[str] = set()
    listings: list[SeekListing] = []

    for keywords in keywords_list:
        for listing in fetch_job_listings_for_query(keywords, location, page_size):
            if listing.job_id not in seen:
                seen.add(listing.job_id)
                listings.append(listing)

    return listings


def fetch_job_urls_for_query(
    keywords: str,
    location: str = "",
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[str]:
    # Fetch job detail URLs for a single keyword/location query.
    return [listing.url for listing in fetch_job_listings_for_query(keywords, location, page_size)]


def fetch_job_urls(search_url: str, page_size: int = DEFAULT_PAGE_SIZE) -> list[str]:
    # Fetch job detail URLs from a Seek search results URL.
    keywords, location = parse_search_url(search_url)
    return fetch_job_urls_for_query(keywords, location, page_size)


def fetch_job_urls_for_keywords(
    keywords_list: list[str],
    location: str = "",
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[str]:
    # Fetch and deduplicate job URLs across multiple keyword searches.
    return [
        listing.url
        for listing in fetch_job_listings_for_keywords(keywords_list, location, page_size)
    ]
