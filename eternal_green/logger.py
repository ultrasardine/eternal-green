"""Logging module for eternal-green."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Rotate the activity log so it never grows without bound.
MAX_LOG_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3


def setup_logger(log_file_path: str, name: str = "eternal_green") -> logging.Logger:
    """Configure and return a logger instance.

    Each call returns a new, independent logger (it is not registered in the
    global ``logging`` hierarchy), so several loggers writing to different
    files never interfere with each other.

    Args:
        log_file_path: Path to the log file (supports ~ expansion)
        name: Logger name

    Returns:
        Configured logger instance
    """
    logger = logging.Logger(name, level=logging.DEBUG)
    logger.propagate = False

    # Expand path and ensure parent directory exists
    expanded_path = Path(log_file_path).expanduser()
    expanded_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        expanded_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)

    # Create formatter matching the design spec format:
    # [TIMESTAMP] [LEVEL] [COMPONENT] MESSAGE
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    return logger


class ActivityLogger:
    """Wrapper for logging activity simulation events."""

    def __init__(self, log_file_path: str):
        """Initialize logger with file path.

        Args:
            log_file_path: Path to the log file (supports ~ expansion)
        """
        self.log_file_path = log_file_path
        self._logger: Optional[logging.Logger] = None

    @property
    def logger(self) -> logging.Logger:
        """Lazy initialization of the logger."""
        if self._logger is None:
            self._logger = setup_logger(self.log_file_path)
        return self._logger

    def close(self) -> None:
        """Close the log file. Logging again reopens it."""
        if self._logger is None:
            return
        for handler in self._logger.handlers[:]:
            handler.close()
            self._logger.removeHandler(handler)
        self._logger = None

    def log_activity(self, message: str) -> None:
        """Log an activity event with INFO level.

        Args:
            message: Activity description
        """
        self.logger.info(message)

    def log_error(self, message: str, exc_info: bool = False) -> None:
        """Log an error with ERROR level.

        Args:
            message: Error description
            exc_info: Include the traceback of the exception being handled
        """
        self.logger.error(message, exc_info=exc_info)

    def log_warning(self, message: str) -> None:
        """Log a warning with WARNING level.

        Args:
            message: Warning description
        """
        self.logger.warning(message)

    def log_config_change(self, param: str, old_value, new_value) -> None:
        """Log a configuration change.

        Args:
            param: Parameter name that changed
            old_value: Previous value
            new_value: New value
        """
        self.logger.info(f"Configuration updated: {param} {old_value} -> {new_value}")

    def log_shutdown(self) -> None:
        """Log application shutdown."""
        self.logger.info("Graceful shutdown initiated")
