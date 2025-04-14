import logging
from typing import Optional

from rich.logging import RichHandler


def setup_logger(name: str, level: str, log_file: Optional[str] = None):
    """Set up a logger with optional file logging and rich console output."""

    logger = logging.getLogger(name)

    # Convert string level to logging level (e.g., "DEBUG" → logging.DEBUG)
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Formatter for file logs (plain text)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    )

    # Rich handler for beautiful console logs
    console_handler = RichHandler(rich_tracebacks=True,
                                  show_time=True,
                                  show_level=True,
                                  show_path=True)
    console_handler.setLevel(log_level)

    logger.addHandler(console_handler)
 """
 If log_file is provided:
Creates a logging.FileHandler to write logs to the specified file.
Sets the file handler's level.
Sets the file handler's formatter.
Adds the file handler to the logger.
Returns the configured logger.
 """
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger