# Configurable job filtering rule engine.

import re

from models.job import Job
from rules import rule_config
from rules.filters import is_recent_job
from utils.logger import Logger

EXPERIENCE_RANGE_PATTERN = re.compile(
    r"(\d+)\s*[-–—to]+\s*(\d+)\s*(?:years?|yrs?)",
    re.IGNORECASE,
)
EXPERIENCE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(\d+)\+\s*(?:years?|yrs?)", re.IGNORECASE),
    re.compile(
        r"(?:minimum|at least|min\.?)\s*(\d+)\s*(?:years?|yrs?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![\d\-–—])(\d+)\s*(?:years?|yrs?)['']?\s*(?:of\s+)?experience",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![\d\-–—])(\d+)\s*(?:years?|yrs?)\s+(?:experience|exp\.?)",
        re.IGNORECASE,
    ),
]


class RuleEngine:
    # Evaluates jobs against configurable title, location, and experience rules.

    def __init__(self) -> None:
        # Initialize the rule engine with configuration values.
        self.logger = Logger("rule-engine")
        self.allowed_titles = rule_config.ALLOWED_TITLES
        self.blocked_titles = rule_config.BLOCKED_TITLES
        self.allowed_locations = rule_config.ALLOWED_LOCATIONS
        self.max_experience = rule_config.MAX_EXPERIENCE

    def evaluate(self, job: Job) -> tuple[bool, list[str]]:
        # Evaluate whether a job matches all configured rules.
        title = (job.title or "").strip()
        self.logger.info(f"Evaluating {title or 'Unknown job'}")

        if not title:
            return False, ["Missing title"]

        location = (job.location or "").strip()
        if not location:
            return False, ["Missing location"]

        blocked = self._contains_blocked_title(title)
        if blocked:
            self.logger.warning(f"Rejected by blocked title: {blocked}")
            return False, ["Blocked title"]

        if not self._match_title(title):
            return False, ["Title not matched"]

        reasons = ["Matched title"]
        self.logger.info("Passed title rule")

        if not self._match_location(location):
            return False, ["Location not matched"]

        reasons.append("Matched location")
        self.logger.info("Passed location")

        if not is_recent_job(job.posted_date):
            self.logger.info("Job too old")
            return False, ["Job too old"]

        experience_ok, experience_reason = self._match_experience(job)
        if not experience_ok:
            return False, [experience_reason or "Experience exceeds maximum"]

        self.logger.info("Evaluation complete")
        return True, reasons

    def _match_title(self, title: str) -> bool:
        # Check whether the title contains an allowed keyword.
        title_lower = title.lower()
        return any(
            allowed.lower() in title_lower for allowed in self.allowed_titles
        )

    def _contains_blocked_title(self, title: str) -> str | None:
        # Return the blocked keyword found in the title, if any.
        title_lower = title.lower()
        for blocked in self.blocked_titles:
            if blocked.lower() in title_lower:
                return blocked
        return None

    def _match_location(self, location: str) -> bool:
        # Check whether the location matches an allowed value.
        location_lower = location.lower()
        return any(
            allowed.lower() in location_lower
            for allowed in self.allowed_locations
        )

    def _match_experience(self, job: Job) -> tuple[bool, str | None]:
        # Check whether experience requirements are within the configured limit.
        required_years = self._extract_required_experience(job.description)
        if required_years is None:
            return True, None

        if required_years > self.max_experience:
            return False, "Experience exceeds maximum"

        return True, None

    def _extract_required_experience(self, description: str | None) -> int | None:
        # Extract the minimum required years of experience from a description.
        if not description:
            return None

        requirements: list[int] = []

        for match in EXPERIENCE_RANGE_PATTERN.finditer(description):
            requirements.append(int(match.group(1)))

        for pattern in EXPERIENCE_PATTERNS:
            for match in pattern.finditer(description):
                requirements.append(int(match.group(1)))

        if not requirements:
            return None

        return max(requirements)
