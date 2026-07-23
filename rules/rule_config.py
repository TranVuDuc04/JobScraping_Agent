"""Rule engine configuration for job filtering."""

ALLOWED_TITLES: list[str] = [
    "Project Coordinator",
    "Project Officer",
    "Business Analyst",
    "Product Coordinator",
    "Associate Product Manager",
]

BLOCKED_TITLES: list[str] = [
    "Senior",
    "Lead",
    "Principal",
    "Director",
]

ALLOWED_LOCATIONS: list[str] = [
    "Melbourne",
    "Remote",
]

MAX_EXPERIENCE: int = 3
