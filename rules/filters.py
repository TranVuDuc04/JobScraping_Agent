# Job filtering, recency checks, and location prioritization.

import re

from models.job import Job
from rules import rule_config

DAYS_AGO_PATTERN = re.compile(r"(\d+)\s*d(?:ay)?s?\s*ago", re.IGNORECASE)
HOURS_AGO_PATTERN = re.compile(r"(\d+)\s*h(?:our)?s?\s*ago", re.IGNORECASE)

LOCATION_PRIORITY_CHECKS: list[tuple[int, str]] = [
    (1, "melbourne_cbd"),
    (2, "inner_melbourne"),
    (3, "greater_melbourne"),
    (4, "melbourne"),
    (5, "victoria_remote"),
    (6, "victoria"),
    (7, "sydney"),
    (8, "brisbane"),
    (9, "adelaide"),
    (10, "perth"),
]


def is_recent_job(posted_date: str | None, max_days: int | None = None) -> bool:
    # Return True if a job was posted within the allowed age window.
    if not posted_date:
        return True

    max_age = max_days if max_days is not None else rule_config.MAX_JOB_AGE_DAYS
    age_days = _posted_age_days(posted_date)
    if age_days is None:
        return True

    return age_days <= max_age


def location_priority(location: str | None) -> int:
    # Return a lower number for higher-priority locations.
    loc = (location or "").lower()
    if not loc:
        return 100

    for priority, rule in LOCATION_PRIORITY_CHECKS:
        if _location_matches_rule(loc, rule):
            return priority

    return 11


def get_matched_keywords(job: Job, limit: int = 3) -> list[str]:
    # Return up to ``limit`` allowed keywords found in the job title or description.
    text = f"{job.title} {job.description}".lower()
    matched: list[str] = []

    for keyword in sorted(rule_config.ALLOWED_TITLES, key=len, reverse=True):
        keyword_lower = keyword.lower()
        if keyword_lower in text and keyword not in matched:
            matched.append(keyword)
        if len(matched) >= limit:
            break

    return matched


def _posted_age_days(posted_date: str) -> int | None:
    # Convert a Seek posted-date string into an approximate day count.
    text = posted_date.strip().lower()

    if text in {"today", "just posted"}:
        return 0
    if text == "yesterday":
        return 1
    if "minute" in text or "min" in text:
        return 0
    if HOURS_AGO_PATTERN.search(text) or "hour" in text:
        return 0

    days_match = DAYS_AGO_PATTERN.search(text)
    if days_match:
        return int(days_match.group(1))

    days_match = re.search(r"(\d+)\s*days?", text)
    if days_match:
        return int(days_match.group(1))

    if "week" in text or "month" in text:
        return 999

    return None


def _location_matches_rule(location: str, rule: str) -> bool:
    # Check whether a location string matches a priority rule.
    if rule == "melbourne_cbd":
        return "melbourne" in location and "cbd" in location
    if rule == "inner_melbourne":
        return "melbourne" in location and "inner" in location
    if rule == "greater_melbourne":
        return "greater melbourne" in location
    if rule == "melbourne":
        return "melbourne" in location
    if rule == "victoria_remote":
        return "remote" in location and ("vic" in location or "victoria" in location)
    if rule == "victoria":
        return "victoria" in location or " vic" in location
    if rule == "sydney":
        return "sydney" in location or "nsw" in location
    if rule == "brisbane":
        return "brisbane" in location or "qld" in location
    if rule == "adelaide":
        return "adelaide" in location or " sa" in location
    if rule == "perth":
        return "perth" in location or " wa" in location
    return False
