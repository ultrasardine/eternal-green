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
        assert loaded.movement_pattern == "standard"


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


# -----------------------------------------------------------------------------
# Loading repairs bad files instead of running with invalid values
# -----------------------------------------------------------------------------


def _write(path, data):
    path.write_text(json.dumps(data) if not isinstance(data, str) else data)


def test_load_repairs_invalid_fields_and_keeps_backup(temp_config_path):
    _write(temp_config_path, {
        "interval_seconds": 5,            # out of range
        "movement_pixels": True,          # bool is not an int here
        "silent_mode": True,              # valid, must be kept
        "movement_pattern": "zigzag",
    })
    manager = ConfigManager(temp_config_path)
    config = manager.load()

    assert config.interval_seconds == 300
    assert config.movement_pixels == 2
    assert config.silent_mode is True
    assert config.movement_pattern == "standard"
    assert config.validate() == []
    assert len(manager.load_warnings) == 3
    # Repaired file on disk, original kept next to it
    assert json.loads(temp_config_path.read_text())["interval_seconds"] == 300
    assert json.loads(temp_config_path.with_name("config.json.bak").read_text())["interval_seconds"] == 5


def test_load_resets_inconsistent_interval_range(temp_config_path):
    _write(temp_config_path, {"interval_range_min": 3000, "interval_range_max": 5000})
    config = ConfigManager(temp_config_path).load()
    assert (config.interval_range_min, config.interval_range_max) == (10, 60)


def test_load_handles_non_object_and_corrupt_json(temp_config_path):
    for content in ("[1, 2, 3]", "{not json"):
        _write(temp_config_path, content)
        manager = ConfigManager(temp_config_path)
        assert manager.load() == EternalGreenConfig()
        assert manager.load_warnings


def test_legacy_random_direction_loads_as_standard(temp_config_path):
    _write(temp_config_path, {"movement_pattern": "random_direction"})
    manager = ConfigManager(temp_config_path)
    assert manager.load().movement_pattern == "standard"
    assert json.loads(temp_config_path.read_text())["movement_pattern"] == "standard"


def test_valid_file_is_not_rewritten(temp_config_path):
    manager = ConfigManager(temp_config_path)
    manager.save(EternalGreenConfig(interval_seconds=42))
    manager.load()
    assert manager.load_warnings == []
    assert not temp_config_path.with_name("config.json.bak").exists()


def test_save_is_atomic_and_leaves_no_temp_files(temp_config_path):
    manager = ConfigManager(temp_config_path)
    manager.save(EternalGreenConfig(interval_seconds=42))
    assert [p.name for p in temp_config_path.parent.iterdir()] == ["config.json"]


def test_update_does_not_clobber_changes_from_another_process(temp_config_path):
    """The tray and the settings window each have a ConfigManager."""
    tray = ConfigManager(temp_config_path)
    tray.load()
    ConfigManager(temp_config_path).update(interval_seconds=120)  # settings window

    tray.update(silent_mode=True)
    reloaded = ConfigManager(temp_config_path).load()
    assert reloaded.interval_seconds == 120
    assert reloaded.silent_mode is True


def test_validate_rejects_bool_for_int_fields():
    errors = EternalGreenConfig(interval_range_min=True).validate()
    assert any("interval_range_min" in e for e in errors)
