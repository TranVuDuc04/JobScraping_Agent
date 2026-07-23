"""Application logging utilities."""

import logging
import sys


class Logger:
    """Simple wrapper around Python's built-in logging module.

    Provides info, warning, and error logging methods.
    """

    def __init__(self, name: str = "ai-job-agent", level: int = logging.INFO) -> None:
        """Initialize the logger.

        Args:
            name: Logger name.
            level: Logging level.
        """
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)

        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            self._logger.addHandler(handler)

    def info(self, message: str) -> None:
        """Log an informational message.

        Args:
            message: Message to log.
        """
        self._logger.info(message)

    def warning(self, message: str) -> None:
        """Log a warning message.

        Args:
            message: Message to log.
        """
        self._logger.warning(message)

    def error(self, message: str) -> None:
        """Log an error message.

        Args:
            message: Message to log.
        """
        self._logger.error(message)
