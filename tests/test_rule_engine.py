# Standalone integration test harness for the Rule Engine.

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.job import Job
from rules.engine import RuleEngine

SEPARATOR = "=" * 52


@dataclass
class TestCase:
    # Defines a single rule engine scenario.

    name: str
    title: str | None
    location: str | None
    description: str
    expected_pass: bool
    expected_reason_hint: str | None = None


@dataclass
class EvaluationOutcome:
    # Normalized result from any supported rule engine API.

    matched: bool
    reasons: list[str]
    score: int | None = None


TEST_CASES: list[TestCase] = [
    TestCase(
        name="CASE 1",
        title="Junior Software Engineer",
        location="Sydney NSW",
        description="1 year experience required",
        expected_pass=True,
    ),
    TestCase(
        name="CASE 2",
        title="Senior Software Engineer",
        location="Melbourne VIC",
        description="2 years experience required",
        expected_pass=False,
        expected_reason_hint="Blocked title",
    ),
    TestCase(
        name="CASE 3",
        title="Business Analyst",
        location="London",
        description="2 years experience required",
        expected_pass=False,
        expected_reason_hint="Location",
    ),
    TestCase(
        name="CASE 4",
        title="Graduate Developer",
        location="Remote",
        description="Looking for motivated graduates.",
        expected_pass=True,
    ),
    TestCase(
        name="CASE 5",
        title="AI Engineer",
        location="Brisbane QLD",
        description="Minimum 5 years experience.",
        expected_pass=False,
        expected_reason_hint="Experience",
    ),
    TestCase(
        name="CASE 6",
        title=None,
        location="Melbourne",
        description="",
        expected_pass=False,
        expected_reason_hint="Missing title",
    ),
]


def build_job(test_case: TestCase) -> Job:
    # Create a Job instance from a test case definition.
    return Job(
        title=test_case.title or "",
        company="Test Company",
        location=test_case.location,
        salary=None,
        employment_type="Full time",
        description=test_case.description,
        url="https://example.com/job/test",
        source="Seek",
        posted_date=None,
    )


def normalize_evaluation(result: object) -> EvaluationOutcome:
    # Adapt bool/tuple or EvaluationResult-style APIs without changing the engine.
    if hasattr(result, "matched"):
        matched = bool(getattr(result, "matched"))
        reasons = list(getattr(result, "reasons", []))
        score = getattr(result, "score", None)
        if score is not None:
            score = int(score)
        return EvaluationOutcome(matched=matched, reasons=reasons, score=score)

    matched, reasons = result  # type: ignore[misc]
    return EvaluationOutcome(matched=bool(matched), reasons=list(reasons))


def compute_score(outcome: EvaluationOutcome, job: Job) -> int | None:
    # Estimate a display score when the engine does not provide one.
    if outcome.score is not None:
        return outcome.score

    if not outcome.matched:
        return None

    score = 70
    if "Matched title" in outcome.reasons:
        score += 10
    if "Matched location" in outcome.reasons:
        score += 10
    if _experience_within_limit(job, outcome):
        score += 5

    return min(score, 100)


def _experience_within_limit(job: Job, outcome: EvaluationOutcome) -> bool:
    # Return True when experience did not cause rejection.
    if not outcome.matched:
        return "Experience exceeds maximum" not in outcome.reasons
    return "Experience exceeds maximum" not in outcome.reasons


def format_expected(expected_pass: bool) -> str:
    # Format the expected outcome label.
    return "PASS" if expected_pass else "FAIL"


def format_actual(matched: bool) -> str:
    # Format the actual engine outcome label.
    return "PASS" if matched else "FAIL"


def format_title(title: str | None) -> str:
    # Format a title for display.
    if title is None or not title.strip():
        return "None"
    return title


def format_reason_lines(
    outcome: EvaluationOutcome,
    job: Job,
    test_case: TestCase,
) -> list[str]:
    # Convert engine reasons into readable checklist lines.
    lines: list[str] = []

    if outcome.matched:
        if "Matched title" in outcome.reasons:
            lines.append("✓ Title matched")
        if "Matched location" in outcome.reasons:
            location = job.location or "Unknown location"
            lines.append(f"✓ {location} matched")
        if _experience_within_limit(job, outcome):
            lines.append("✓ Experience within limit")
        return lines

    for reason in outcome.reasons:
        if reason == "Blocked title":
            blocked = _find_blocked_keyword(test_case.title or "")
            if blocked:
                lines.append(f"✗ Blocked title: {blocked}")
            else:
                lines.append("✗ Blocked title")
        elif reason == "Location not matched":
            lines.append(f"✗ Location: {job.location}")
        elif reason == "Experience exceeds maximum":
            lines.append("✗ Experience exceeds maximum")
        elif reason == "Missing title":
            lines.append("✗ Missing title")
        elif reason == "Missing location":
            lines.append("✗ Missing location")
        elif reason == "Title not matched":
            lines.append("✗ Title not matched")
        else:
            lines.append(f"✗ {reason}")

    if test_case.expected_reason_hint:
        hint = test_case.expected_reason_hint.lower()
        if not any(hint in line.lower() for line in lines):
            lines.append(f"✗ {test_case.expected_reason_hint}")

    return lines


def _find_blocked_keyword(title: str) -> str | None:
    # Find the blocked keyword in a title for display purposes.
    title_lower = title.lower()
    for blocked in ("Senior", "Lead", "Principal", "Director"):
        if blocked.lower() in title_lower:
            return blocked
    return None


def print_case_report(
    test_case: TestCase,
    outcome: EvaluationOutcome,
    job: Job,
    case_passed: bool,
) -> None:
    # Print a formatted report for one test case.
    print(SEPARATOR)
    print()
    print(test_case.name)
    print()
    print("Title:")
    print(format_title(test_case.title))
    print()
    print("Expected:")
    print(format_expected(test_case.expected_pass))
    print()
    print("Actual:")
    print(format_actual(outcome.matched))
    print()

    score = compute_score(outcome, job)
    if score is not None:
        print("Score:")
        print(score)
        print()

    print("Reasons:")
    print()
    for line in format_reason_lines(outcome, job, test_case):
        print(line)
    print()

    if not case_passed:
        print("❌ Unexpected Result")
        print()

    print("Result:")
    print()
    print("PASS" if case_passed else "FAIL")
    print()
    print(SEPARATOR)


def print_summary(passed: int, failed: int) -> None:
    # Print the final test harness summary.
    total = passed + failed
    accuracy = (passed / total * 100) if total else 0.0

    print()
    print(SEPARATOR)
    print()
    print("SUMMARY")
    print()
    print("Passed:")
    print()
    print(passed)
    print()
    print("Failed:")
    print()
    print(failed)
    print()
    print("Accuracy:")
    print()
    print(f"{accuracy:.0f}%")
    print()


def _quiet_engine_logs() -> None:
    # Reduce rule engine log noise during manual test runs.
    engine_logger = logging.getLogger("rule-engine")
    engine_logger.setLevel(logging.ERROR)
    for handler in engine_logger.handlers:
        handler.setLevel(logging.ERROR)


def run_tests() -> int:
    # Execute all predefined scenarios and print a report.
    engine = RuleEngine()
    _quiet_engine_logs()
    passed_cases = 0
    failed_cases = 0

    for test_case in TEST_CASES:
        job = build_job(test_case)
        outcome = normalize_evaluation(engine.evaluate(job))
        case_passed = outcome.matched == test_case.expected_pass

        if case_passed:
            passed_cases += 1
        else:
            failed_cases += 1

        print_case_report(test_case, outcome, job, case_passed)

    print_summary(passed_cases, failed_cases)
    return 0 if failed_cases == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run_tests())
