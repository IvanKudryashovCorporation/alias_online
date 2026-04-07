"""
Configure logging for the entire application.
Call setup_logging() at application startup.
"""

import logging
import logging.handlers
import sys
from pathlib import Path

import config


def setup_logging() -> None:
    """Configure logging for the application."""
    # Create logs directory if needed
    log_dir = Path(".claude/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(config.LOG_LEVEL)

    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Formatter
    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(config.LOG_LEVEL)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (rotating)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "alias_game.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )
    file_handler.setLevel(logging.DEBUG)  # Always log DEBUG to file
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Suppress verbose Kivy logging
    logging.getLogger("kivy").setLevel(logging.WARNING)
    logging.getLogger("kivy.core").setLevel(logging.WARNING)
    logging.getLogger("kivy.graphics").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured (level={config.LOG_LEVEL})")
