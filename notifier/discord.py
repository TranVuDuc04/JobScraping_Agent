"""Discord notification handler."""

import requests

from models.job import Job


class DiscordNotifier:
    """Sends job notifications to a Discord channel via webhook."""

    def __init__(self, webhook_url: str) -> None:
        """Initialize the Discord notifier.

        Args:
            webhook_url: Discord webhook URL for posting messages.
        """
        self.webhook_url = webhook_url

    def send(self, job: Job, reasons: list[str] | None = None) -> None:
        """Send a plain-text job notification to Discord.

        Args:
            job: Job to notify about.
            reasons: Optional rule engine match reasons.

        Raises:
            ValueError: If the webhook URL is not configured.
            requests.RequestException: If the Discord request fails.
        """
        if not self.webhook_url:
            raise ValueError("DISCORD_WEBHOOK is not configured")

        message = self._format_message(job, reasons or [])
        response = requests.post(
            self.webhook_url,
            json={"content": message},
            timeout=30,
        )
        response.raise_for_status()

    def _format_message(self, job: Job, reasons: list[str]) -> str:
        """Build the plain-text Discord notification body."""
        reason_lines = self._format_reasons(job, reasons)
        posted = job.posted_date or "Unknown"
        salary = job.salary or "Unknown"
        location = job.location or "Unknown"

        return (
            "🔥 New Job\n\n"
            f"{job.title}\n\n"
            f"{job.company}\n\n"
            f"{location}\n\n"
            f"{salary}\n\n"
            f"{posted}\n\n"
            f"{job.source}\n\n"
            "Reasons\n\n"
            f"{reason_lines}\n\n"
            "Apply\n\n"
            f"{job.url}"
        )

    def _format_reasons(self, job: Job, reasons: list[str]) -> str:
        """Format rule engine reasons as bullet points."""
        if not reasons:
            return "• Matched"

        lines: list[str] = []
        for reason in reasons:
            if reason == "Matched title":
                lines.append("• Title matched")
            elif reason == "Matched location":
                location = job.location or "Location"
                lines.append(f"• {location} matched")
            else:
                lines.append(f"• {reason}")
        return "\n".join(lines)
