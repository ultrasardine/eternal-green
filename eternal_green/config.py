"""Configuration management for eternal-green."""

from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Optional
import json
import os
import shutil
import tempfile

VALID_MOVEMENT_PATTERNS: tuple[str, ...] = ("standard", "return_to_source", "bounce")

# Patterns that were removed or renamed, mapped to their replacement.
LEGACY_PATTERN_ALIASES: dict[str, str] = {"random_direction": "standard"}

# Error key used when the min/max pair is inconsistent (both get reset).
_RANGE_ERROR_KEY = "interval_range"


def _is_int(value) -> bool:
    """True for real integers (``bool`` is an ``int`` subclass but not accepted)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _int_in_range(value, low: int, high: int) -> bool:
    return _is_int(value) and low <= value <= high


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
    movement_pattern: str = "standard"

    def field_errors(self) -> dict[str, str]:
        """Validate configuration values, keyed by the offending field."""
        errors: dict[str, str] = {}

        if not _int_in_range(self.interval_seconds, 10, 3600):
            errors["interval_seconds"] = f"interval_seconds must be an integer between 10 and 3600, got {self.interval_seconds!r}"

        if not _int_in_range(self.movement_pixels, 1, 100):
            errors["movement_pixels"] = f"movement_pixels must be an integer between 1 and 100, got {self.movement_pixels!r}"

        if not isinstance(self.silent_mode, bool):
            errors["silent_mode"] = f"silent_mode must be a boolean, got {type(self.silent_mode).__name__}"

        if not isinstance(self.log_file_path, str) or not self.log_file_path.strip():
            errors["log_file_path"] = "log_file_path must be a non-empty string"

        if not isinstance(self.random_interval, bool):
            errors["random_interval"] = f"random_interval must be a boolean, got {type(self.random_interval).__name__}"

        if not _int_in_range(self.interval_range_min, 10, 3600):
            errors["interval_range_min"] = f"interval_range_min must be an integer between 10 and 3600, got {self.interval_range_min!r}"

        if not _int_in_range(self.interval_range_max, 10, 3600):
            errors["interval_range_max"] = f"interval_range_max must be an integer between 10 and 3600, got {self.interval_range_max!r}"

        if (
            "interval_range_min" not in errors
            and "interval_range_max" not in errors
            and self.interval_range_min >= self.interval_range_max
        ):
            errors[_RANGE_ERROR_KEY] = f"interval_range_min ({self.interval_range_min}) must be less than interval_range_max ({self.interval_range_max})"

        if self.movement_pattern not in VALID_MOVEMENT_PATTERNS:
            errors["movement_pattern"] = (
                f"movement_pattern must be one of {VALID_MOVEMENT_PATTERNS}, "
                f"got '{self.movement_pattern}'"
            )

        return errors

    def validate(self) -> list[str]:
        """Validate configuration values. Returns list of error messages."""
        return list(self.field_errors().values())


class ConfigManager:
    """Manages configuration loading, saving, and validation."""

    DEFAULT_CONFIG_PATH = Path("~/.eternal_green_config.json")

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize with optional custom config path."""
        self.config_path = Path(config_path).expanduser() if config_path else self.DEFAULT_CONFIG_PATH.expanduser()
        self._config: Optional[EternalGreenConfig] = None
        # Problems found (and fixed) by the last load(), for the UI to show.
        self.load_warnings: list[str] = []

    def load(self) -> EternalGreenConfig:
        """Load configuration from file, creating defaults if needed.

        Invalid values are replaced by their defaults (the original file is
        kept as ``<name>.bak``) and described in ``load_warnings``.
        """
        self.load_warnings = []

        if not self.config_path.exists():
            self._config = EternalGreenConfig()
            self.save(self._config)
            return self._config

        data = None
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            self.load_warnings.append(f"Could not read {self.config_path} ({e}); using defaults")
        if data is not None and not isinstance(data, dict):
            self.load_warnings.append(f"{self.config_path} is not a JSON object; using defaults")
            data = None

        config = EternalGreenConfig() if data is None else self._repair(data)
        if self.load_warnings:
            self._backup_and_save(config)
        self._config = config
        return config

    def _repair(self, data: dict) -> EternalGreenConfig:
        """Build a config from raw data, replacing invalid fields with defaults."""
        # Filter to only known fields for forward/backward compat
        known_fields = {f.name for f in fields(EternalGreenConfig)}
        values = {k: v for k, v in data.items() if k in known_fields}

        pattern = values.get("movement_pattern")
        if isinstance(pattern, str) and pattern in LEGACY_PATTERN_ALIASES:
            values["movement_pattern"] = LEGACY_PATTERN_ALIASES[pattern]
            self.load_warnings.append(
                f"movement_pattern '{pattern}' is now '{values['movement_pattern']}'"
            )

        config = EternalGreenConfig(**values)
        defaults = EternalGreenConfig()
        # Resetting one end of the interval range can expose a min/max conflict,
        # so repeat until nothing is left to fix.
        while errors := config.field_errors():
            for key, message in errors.items():
                self.load_warnings.append(f"{message}; using the default")
                reset = ("interval_range_min", "interval_range_max") if key == _RANGE_ERROR_KEY else (key,)
                for name in reset:
                    setattr(config, name, getattr(defaults, name))
        return config

    def _backup_and_save(self, config: EternalGreenConfig) -> None:
        """Keep a copy of the problematic file, then write the repaired config."""
        try:
            shutil.copy2(self.config_path, self.config_path.with_name(self.config_path.name + ".bak"))
            self.save(config)
        except OSError as e:
            self.load_warnings.append(f"Could not rewrite {self.config_path}: {e}")

    def save(self, config: EternalGreenConfig) -> None:
        """Save configuration to file after validation.

        The file is written atomically (temp file + rename) so a crash or a
        concurrent writer never leaves a truncated config behind.
        """
        errors = config.validate()
        if errors:
            raise ValueError(f"Invalid configuration: {'; '.join(errors)}")

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=self.config_path.parent, prefix=f".{self.config_path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(asdict(config), f, indent=2)
            os.replace(tmp_path, self.config_path)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise
        self._config = config

    def update(self, **kwargs) -> EternalGreenConfig:
        """Update specific configuration values.

        Re-reads the file first so changes written by another process (the
        settings window, the CLI) are not overwritten with stale values.
        """
        current_data = asdict(self.load())
        current_data.update(kwargs)
        new_config = EternalGreenConfig(**current_data)
        self.save(new_config)
        return new_config
