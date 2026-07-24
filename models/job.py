"""Job data model."""

from dataclasses import dataclass


@dataclass
class Job:
    """Represents a scraped job listing.

    Attributes:
        title: Job title.
        company: Company name.
        location: Job location, if available.
        salary: Salary information, if available.
        employment_type: Employment type (e.g. Full-time), if available.
        description: Full job description text.
        url: URL of the job listing.
        source: Source platform (e.g. seek, linkedin).
        posted_date: Date the job was posted, if available.
    """

    title: str
    company: str
    location: str | None
    salary: str | None
    employment_type: str | None
    description: str
    url: str
    source: str
    posted_date: str | None
