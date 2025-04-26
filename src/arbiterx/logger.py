import logging
import os
from datetime import datetime
from typing import Optional, Union, Dict, Any

from rich.logging import RichHandler


class LoggerConfig:
    """Configuration constants for logging."""
    DEFAULT_LEVEL = logging.INFO
    DEFAULT_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(filename)s:%(lineno)d | %(message)s"
    DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    RICH_FORMAT = "%(message)s"


def setup_logger(
    name: str,
    level: Union[str, int] = "INFO",
    log_file: Optional[str] = None,
    log_rotation: bool = False,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    extra_handlers: Optional[list] = None,
    log_config: Optional[Dict[str, Any]] = None
) -> logging.Logger:
    """
    Set up a logger with configurable options.
    
    Args:
        name: The name of the logger
        level: Logging level (string or int)
        log_file: Optional path to log file
        log_rotation: Whether to use rotating file handler
        max_bytes: Maximum size of each log file for rotation
        backup_count: Number of backup files to keep
        extra_handlers: Additional handlers to attach
        log_config: Optional configuration overrides
        
    Returns:
        A configured logger instance
    """
    # Apply custom config if provided, otherwise use defaults
    config = log_config or {}
    log_format = config.get("format", LoggerConfig.DEFAULT_FORMAT)
    date_format = config.get("date_format", LoggerConfig.DEFAULT_DATE_FORMAT)
    
    # Get or create logger
    logger = logging.getLogger(name)
    
    # Clear existing handlers (to avoid duplication)
    if logger.handlers:
        logger.handlers.clear()
    
    # Set log level
    if isinstance(level, str):
        log_level = getattr(logging, level.upper(), LoggerConfig.DEFAULT_LEVEL)
    else:
        log_level = level
    logger.setLevel(log_level)
    
    # Create formatter for file logs
    file_formatter = logging.Formatter(
        fmt=log_format,
        datefmt=date_format
    )
    
    # Rich handler for console output
    console_handler = RichHandler(
        rich_tracebacks=True,
        show_time=True,
        show_level=True,
        show_path=True,
        markup=True,
        log_time_format=date_format
    )
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(LoggerConfig.RICH_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # Add file handler if specified
    if log_file:
        # Ensure log directory exists
        log_dir = os.path.dirname(os.path.abspath(log_file))
        os.makedirs(log_dir, exist_ok=True)
        
        if log_rotation:
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count
            )
        else:
            file_handler = logging.FileHandler(log_file)
            
        file_handler.setLevel(log_level)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # Add any extra handlers
    if extra_handlers:
        for handler in extra_handlers:
            logger.addHandler(handler)
    
    return logger


def get_timestamp_filename(base_name: str, extension: str = "log") -> str:
    """
    Generate a timestamp-based filename.
    
    Args:
        base_name: Base name for the file
        extension: File extension (without dot)
        
    Returns:
        A filename with timestamp
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base_name}_{timestamp}.{extension}"


# Example usage
if __name__ == "__main__":
    # Basic usage
    logger = setup_logger("app", "DEBUG")
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    
    # With file logging and rotation
    log_file = get_timestamp_filename("application")
    advanced_logger = setup_logger(
        "advanced_app",
        "INFO",
        log_file=f"logs/{log_file}",
        log_rotation=True
    )
    advanced_logger.info("Application started")
