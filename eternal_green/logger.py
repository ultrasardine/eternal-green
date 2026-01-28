"""Logging module for eternal-green."""

import logging
from pathlib import Path
from typing import Optional


def setup_logger(log_file_path: str, name: str = "eternal_green") -> logging.Logger:
    """Configure and return a logger instance.
    
    Args:
        log_file_path: Path to the log file (supports ~ expansion)
        name: Logger name
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Expand path and ensure parent directory exists
    expanded_path = Path(log_file_path).expanduser()
    expanded_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create file handler
    file_handler = logging.FileHandler(expanded_path)
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
    
    def log_activity(self, message: str) -> None:
        """Log an activity event with INFO level.
        
        Args:
            message: Activity description
        """
        self.logger.info(message)
    
    def log_error(self, message: str) -> None:
        """Log an error with ERROR level.
        
        Args:
            message: Error description
        """
        self.logger.error(message)
    
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
