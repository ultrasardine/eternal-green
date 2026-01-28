"""Tests for configuration management."""

import tempfile
from pathlib import Path
from hypothesis import given, strategies as st, settings
from eternal_green.config import EternalGreenConfig, ConfigManager


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
