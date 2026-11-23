# Tracks previously notified job URLs.

import json
from pathlib import Path

from utils.logger import Logger

DEFAULT_STORAGE_PATH = Path(__file__).resolve().parent / "sent_jobs.json"


class DuplicateChecker:
    # Checks and records job URLs that have already been notified.

    def __init__(self, file_path: Path | str | None = None) -> None:
        # Initialize the duplicate checker.
        self.file_path = Path(file_path) if file_path else DEFAULT_STORAGE_PATH
        self.logger = Logger("duplicate-checker")
        self._sent_urls: set[str] = set()

    def load(self) -> None:
        # Load sent job URLs from disk into memory.
        if not self.file_path.exists():
            self._sent_urls = set()
            return

        try:
            content = self.file_path.read_text(encoding="utf-8").strip()
            if not content:
                self._sent_urls = set()
                return

            data = json.loads(content)
            if not isinstance(data, list):
                raise ValueError("sent_jobs.json must contain a JSON array")

            self._sent_urls = {url for url in data if isinstance(url, str)}
        except json.JSONDecodeError as exc:
            self.logger.error(f"Invalid sent_jobs.json: {exc}")
            self._sent_urls = set()
        except OSError as exc:
            self.logger.error(f"Failed to read sent_jobs.json: {exc}")
            self._sent_urls = set()

    def save(self) -> None:
        # Persist sent job URLs to disk.
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(sorted(self._sent_urls), indent=2)
            self.file_path.write_text(f"{payload}\n", encoding="utf-8")
        except OSError as exc:
            self.logger.error(f"Failed to write sent_jobs.json: {exc}")

    def is_sent(self, url: str) -> bool:
        # Return True if the URL has already been notified.
        return url in self._sent_urls

    def mark_sent(self, url: str) -> None:
        # Record a URL as notified.
        self._sent_urls.add(url)
