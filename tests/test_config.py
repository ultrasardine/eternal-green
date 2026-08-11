"""Tests for configuration management."""

import json
import tempfile
from pathlib import Path
from hypothesis import given, strategies as st, settings
from eternal_green.config import EternalGreenConfig, ConfigManager, VALID_MOVEMENT_PATTERNS


# Feature: eternal-green, Property 4: Configuration Serialization Round-Trip
# **Validates: Requirements 2.1**
@settings(max_examples=100, deadline=None)
@given(
    interval_seconds=st.integers(min_value=10, max_value=3600),
    movement_pixels=st.integers(min_value=1, max_value=100),
    silent_mode=st.booleans(),
    log_file_path=st.text(min_size=1, max_size=50).filter(lambda x: x.strip())
)
def test_config_serialization_round_trip(
    interval_seconds,
    movement_pixels,
    silent_mode,
    log_file_path
):
    """For any valid EternalGreenConfig, saving to JSON and loading should produce equivalent config."""
    original = EternalGreenConfig(
        interval_seconds=interval_seconds,
        movement_pixels=movement_pixels,
        silent_mode=silent_mode,
        log_file_path=log_file_path
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        manager = ConfigManager(config_path=config_path)
        manager.save(original)
        loaded = manager.load()
        
        assert loaded.interval_seconds == original.interval_seconds
        assert loaded.movement_pixels == original.movement_pixels
        assert loaded.silent_mode == original.silent_mode
        assert loaded.log_file_path == original.log_file_path



# Feature: eternal-green, Property 5: Configuration Validation Rejects Invalid Values
# **Validates: Requirements 2.5, 2.6**
@settings(max_examples=100)
@given(
    interval_seconds=st.integers().filter(lambda x: x < 10 or x > 3600),
)
def test_config_validation_rejects_invalid_interval(interval_seconds):
    """For any interval_seconds outside valid range, validate() should return errors."""
    config = EternalGreenConfig(interval_seconds=interval_seconds)
    errors = config.validate()
    assert len(errors) > 0
    assert any("interval_seconds" in e for e in errors)


@settings(max_examples=100)
@given(
    movement_pixels=st.integers().filter(lambda x: x < 1 or x > 100),
)
def test_config_validation_rejects_invalid_movement_pixels(movement_pixels):
    """For any movement_pixels outside valid range, validate() should return errors."""
    config = EternalGreenConfig(movement_pixels=movement_pixels)
    errors = config.validate()
    assert len(errors) > 0
    assert any("movement_pixels" in e for e in errors)


@settings(max_examples=100)
@given(
    interval_seconds=st.integers().filter(lambda x: x < 10 or x > 3600),
)
def test_config_save_raises_on_invalid_values(interval_seconds):
    """For any invalid config, save() should raise ValueError."""
    import pytest
    config = EternalGreenConfig(interval_seconds=interval_seconds)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        manager = ConfigManager(config_path=config_path)
        
        with pytest.raises(ValueError):
            manager.save(config)


# Feature: movement-patterns, Property 1: Pattern validation rejects invalid values with descriptive error
# **Validates: Requirements 1.2, 1.3**
@settings(max_examples=100, deadline=None)
@given(
    pattern=st.text(min_size=1, max_size=50).filter(
        lambda x: x not in VALID_MOVEMENT_PATTERNS
    )
)
def test_config_validation_rejects_invalid_movement_pattern(pattern):
    """For any string NOT in the valid set, validate() returns non-empty errors mentioning allowed values."""
    config = EternalGreenConfig(movement_pattern=pattern)
    errors = config.validate()
    assert len(errors) > 0
    assert any("movement_pattern" in e for e in errors)
    # Error message should mention the allowed values
    assert any(str(VALID_MOVEMENT_PATTERNS) in e for e in errors)


# Feature: movement-patterns, Property 2: Backward-compatible default for missing field
# **Validates: Requirements 1.4**
@settings(max_examples=100, deadline=None)
@given(
    interval_seconds=st.integers(min_value=10, max_value=3600),
    movement_pixels=st.integers(min_value=1, max_value=100),
    silent_mode=st.booleans(),
    random_interval=st.booleans(),
    interval_range_min=st.integers(min_value=10, max_value=1799),
    interval_range_max=st.integers(min_value=1800, max_value=3600),
)
def test_config_backward_compatible_default_movement_pattern(
    interval_seconds,
    movement_pixels,
    silent_mode,
    random_interval,
    interval_range_min,
    interval_range_max,
):
    """For any valid config dict without movement_pattern key, loading defaults to 'random_direction'."""
    config_data = {
        "interval_seconds": interval_seconds,
        "movement_pixels": movement_pixels,
        "silent_mode": silent_mode,
        "log_file_path": "~/.eternal_green.log",
        "random_interval": random_interval,
        "interval_range_min": interval_range_min,
        "interval_range_max": interval_range_max,
    }
    # Ensure movement_pattern is NOT in the dict
    assert "movement_pattern" not in config_data

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        with open(config_path, "w") as f:
            json.dump(config_data, f)

        manager = ConfigManager(config_path=config_path)
        loaded = manager.load()
        assert loaded.movement_pattern == "random_direction"


# Feature: movement-patterns, Property 7: Configuration round-trip preserves movement pattern
# **Validates: Requirements 7.1, 7.2, 7.3**
@settings(max_examples=100, deadline=None)
@given(
    pattern=st.sampled_from(list(VALID_MOVEMENT_PATTERNS)),
)
def test_config_round_trip_preserves_movement_pattern(pattern):
    """For any valid movement_pattern value, save/load round-trip preserves the value."""
    config = EternalGreenConfig(movement_pattern=pattern)

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        manager = ConfigManager(config_path=config_path)
        manager.save(config)
        loaded = manager.load()
        assert loaded.movement_pattern == pattern
