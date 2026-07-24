"""HTML parser for job listings."""

import re

from bs4 import BeautifulSoup

from models.job import Job
from utils.logger import Logger

SOURCE = "Seek"
SELECTORS = {
    "title": '[data-automation="job-detail-title"]',
    "company": '[data-automation="advertiser-name"]',
    "location": '[data-automation="job-detail-location"]',
    "salary": '[data-automation="job-detail-salary"]',
    "employment_type": '[data-automation="job-detail-work-type"]',
    "description": '[data-automation="jobAdDetails"]',
    "page": '[data-automation="jobDetailsPage"]',
}
POSTED_PREFIX = re.compile(r"^Posted\s+", re.IGNORECASE)


class JobParser:
    """Parses raw Seek job HTML into structured Job objects."""

    def __init__(self) -> None:
        """Initialize the job parser."""
        self.logger = Logger("job-parser")

    def parse(self, html: str, url: str) -> Job:
        """Parse HTML content into a Job object.

        Args:
            html: Raw HTML string of a job listing page.
            url: Canonical URL of the job listing.

        Returns:
            A populated Job instance.

        Raises:
            ValueError: If the HTML is empty or not a recognizable job page.
        """
        if not html or not html.strip():
            raise ValueError("HTML content is empty or invalid")

        soup = BeautifulSoup(html, "html.parser")
        if not self._is_valid_job_page(soup):
            raise ValueError("HTML does not contain a recognizable Seek job page")

        title = self._extract_title(soup)
        company = self._extract_company(soup)
        location = self._extract_location(soup)
        salary = self._extract_salary(soup)
        employment_type = self._extract_employment_type(soup)
        description = self._extract_description(soup)
        posted_date = self._extract_posted_date(soup)

        self._log_results(title, company, salary, posted_date)

        return Job(
            title=title or "",
            company=company or "",
            location=location,
            salary=salary,
            employment_type=employment_type,
            description=description or "",
            url=url,
            source=SOURCE,
            posted_date=posted_date,
        )

    def _is_valid_job_page(self, soup: BeautifulSoup) -> bool:
        """Check whether the soup contains a Seek job detail page."""
        return (
            soup.select_one(SELECTORS["page"]) is not None
            or soup.select_one(SELECTORS["title"]) is not None
        )

    def _log_results(
        self,
        title: str | None,
        company: str | None,
        salary: str | None,
        posted_date: str | None,
    ) -> None:
        """Log parsing outcomes for key fields."""
        if title:
            self.logger.info(f"Parsed title: {title}")
        if company:
            self.logger.info(f"Parsed company: {company}")
        if salary is None:
            self.logger.warning("Salary missing")
        if posted_date is None:
            self.logger.warning("Posted date missing")

    def _select_text(self, soup: BeautifulSoup, selector: str) -> str | None:
        """Return cleaned text from the first element matching a selector."""
        element = soup.select_one(selector)
        if element is None:
            return None
        return self._clean_text(element.get_text(" ", strip=True))

    def _extract_title(self, soup: BeautifulSoup) -> str | None:
        """Extract the job title."""
        return self._select_text(soup, SELECTORS["title"])

    def _extract_company(self, soup: BeautifulSoup) -> str | None:
        """Extract the company name."""
        return self._select_text(soup, SELECTORS["company"])

    def _extract_location(self, soup: BeautifulSoup) -> str | None:
        """Extract the job location."""
        return self._select_text(soup, SELECTORS["location"])

    def _extract_salary(self, soup: BeautifulSoup) -> str | None:
        """Extract the salary information."""
        return self._select_text(soup, SELECTORS["salary"])

    def _extract_employment_type(self, soup: BeautifulSoup) -> str | None:
        """Extract the employment type (e.g. Full time)."""
        return self._select_text(soup, SELECTORS["employment_type"])

    def _extract_description(self, soup: BeautifulSoup) -> str | None:
        """Extract the full job description as plain text."""
        element = soup.select_one(SELECTORS["description"])
        if element is None:
            return None
        return self._clean_description(element.get_text("\n", strip=True))

    def _extract_posted_date(self, soup: BeautifulSoup) -> str | None:
        """Extract the job posted date."""
        page = soup.select_one(SELECTORS["page"]) or soup
        for span in page.find_all("span"):
            text = span.get_text(strip=True)
            if text.lower().startswith("posted "):
                return self._clean_text(POSTED_PREFIX.sub("", text))
        return None

    def _clean_text(self, text: str | None) -> str | None:
        """Normalize whitespace in a single-line string."""
        if text is None:
            return None
        cleaned = re.sub(r"\s+", " ", text.strip())
        return cleaned or None

    def _clean_description(self, text: str | None) -> str | None:
        """Normalize whitespace while preserving readable paragraph breaks."""
        if text is None:
            return None
        lines = [self._clean_text(line) for line in text.splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines) if lines else None
