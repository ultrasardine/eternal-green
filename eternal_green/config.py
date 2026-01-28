"""Configuration management for eternal-green."""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
import json


@dataclass
class EternalGreenConfig:
    """Configuration data structure for eternal-green."""
    
    interval_seconds: int = 300
    movement_pixels: int = 2
    silent_mode: bool = False
    log_file_path: str = "~/.eternal_green.log"
    random_interval: bool = False
    interval_range_min: int = 10
    interval_range_max: int = 60
    
    def validate(self) -> list[str]:
        """Validate configuration values. Returns list of error messages."""
        errors = []
        
        if not isinstance(self.interval_seconds, int) or self.interval_seconds < 10 or self.interval_seconds > 3600:
            errors.append(f"interval_seconds must be an integer between 10 and 3600, got {self.interval_seconds}")
        
        if not isinstance(self.movement_pixels, int) or self.movement_pixels < 1 or self.movement_pixels > 100:
            errors.append(f"movement_pixels must be an integer between 1 and 100, got {self.movement_pixels}")
        
        if not isinstance(self.silent_mode, bool):
            errors.append(f"silent_mode must be a boolean, got {type(self.silent_mode).__name__}")
        
        if not isinstance(self.log_file_path, str) or not self.log_file_path:
            errors.append("log_file_path must be a non-empty string")
        
        if not isinstance(self.random_interval, bool):
            errors.append(f"random_interval must be a boolean, got {type(self.random_interval).__name__}")
        
        if not isinstance(self.interval_range_min, int) or self.interval_range_min < 10 or self.interval_range_min > 3600:
            errors.append(f"interval_range_min must be an integer between 10 and 3600, got {self.interval_range_min}")
        
        if not isinstance(self.interval_range_max, int) or self.interval_range_max < 10 or self.interval_range_max > 3600:
            errors.append(f"interval_range_max must be an integer between 10 and 3600, got {self.interval_range_max}")
        
        if self.interval_range_min >= self.interval_range_max:
            errors.append(f"interval_range_min ({self.interval_range_min}) must be less than interval_range_max ({self.interval_range_max})")
        
        return errors


class ConfigManager:
    """Manages configuration loading, saving, and validation."""
    
    DEFAULT_CONFIG_PATH = Path("~/.eternal_green_config.json")
    
    def __init__(self, config_path: Optional[Path] = None):
        """Initialize with optional custom config path."""
        self.config_path = Path(config_path).expanduser() if config_path else self.DEFAULT_CONFIG_PATH.expanduser()
        self._config: Optional[EternalGreenConfig] = None
    
    def load(self) -> EternalGreenConfig:
        """Load configuration from file, creating defaults if needed."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                self._config = EternalGreenConfig(**data)
            except (json.JSONDecodeError, TypeError):
                self._config = EternalGreenConfig()
                self.save(self._config)
        else:
            self._config = EternalGreenConfig()
            self.save(self._config)
        return self._config
    
    def save(self, config: EternalGreenConfig) -> None:
        """Save configuration to file after validation."""
        errors = config.validate()
        if errors:
            raise ValueError(f"Invalid configuration: {'; '.join(errors)}")
        
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(asdict(config), f, indent=2)
        self._config = config
    
    def update(self, **kwargs) -> EternalGreenConfig:
        """Update specific configuration values."""
        if self._config is None:
            self.load()
        
        current_data = asdict(self._config)
        current_data.update(kwargs)
        new_config = EternalGreenConfig(**current_data)
        self.save(new_config)
        return new_config
