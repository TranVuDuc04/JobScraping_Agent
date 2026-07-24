"""Discord notification handler."""

import requests

from models.job import Job
from rules.filters import get_matched_keywords

EMBED_COLOR_GREEN = 0x57F287


class DiscordNotifier:
    """Sends job notifications to a Discord channel via webhook."""

    def __init__(self, webhook_url: str) -> None:
        """Initialize the Discord notifier.

        Args:
            webhook_url: Discord webhook URL for posting messages.
        """
        self.webhook_url = webhook_url

    def send(self, job: Job, reasons: list[str] | None = None) -> None:
        """Send a compact embed notification to Discord.

        Args:
            job: Job to notify about.
            reasons: Optional rule engine match reasons (unused in embed display).

        Raises:
            ValueError: If the webhook URL is not configured.
            requests.RequestException: If the Discord request fails.
        """
        if not self.webhook_url:
            raise ValueError("DISCORD_WEBHOOK is not configured")

        embed = self._build_embed(job)
        response = requests.post(
            self.webhook_url,
            json={"embeds": [embed]},
            timeout=30,
        )
        response.raise_for_status()

    def _build_embed(self, job: Job) -> dict[str, object]:
        """Build a compact Discord embed for a job listing."""
        keywords = get_matched_keywords(job, limit=3)
        keyword_text = " • ".join(keywords) if keywords else "N/A"
        location = job.location or "N/A"
        salary = job.salary or "N/A"
        posted = job.posted_date or "N/A"
        employment_type = job.employment_type or "N/A"

        return {
            "title": f"🟢 {job.title}",
            "url": job.url,
            "color": EMBED_COLOR_GREEN,
            "description": (
                f"🏢 {job.company}\n\n"
                f"🏷 {keyword_text}\n\n"
                f"🔗 [Apply]({job.url})"
            ),
            "fields": [
                {"name": "📍 Location", "value": location, "inline": True},
                {"name": "💰 Salary", "value": salary, "inline": True},
                {"name": "🕒 Posted", "value": posted, "inline": True},
                {"name": "💼 Type", "value": employment_type, "inline": True},
            ],
        }
