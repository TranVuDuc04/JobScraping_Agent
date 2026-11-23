# Job data model.

from dataclasses import dataclass


@dataclass
class Job:
    # Represents a scraped job listing.

    title: str
    company: str
    location: str | None
    salary: str | None
    employment_type: str | None
    description: str
    url: str
    source: str
    posted_date: str | None
