"""Tests for CLI interface."""

import tempfile
from pathlib import Path
from unittest.mock import patch
from hypothesis import given, strategies as st, settings, assume

from eternal_green.config import EternalGreenConfig, ConfigManager, VALID_MOVEMENT_PATTERNS
from eternal_green.cli import CLIInterface


# Feature: eternal-green, Property 6: Configuration Display Completeness
# **Validates: Requirements 3.4**
@settings(max_examples=100, deadline=None)
@given(
    interval_seconds=st.integers(min_value=10, max_value=3600),
    movement_pixels=st.integers(min_value=1, max_value=100),
    silent_mode=st.booleans(),
    log_file_path=st.text(min_size=1, max_size=50).filter(lambda x: x.strip())
)
def test_config_display_completeness(
    interval_seconds,
    movement_pixels,
    silent_mode,
    log_file_path
):
    """For any EternalGreenConfig, display_config() output should contain all four parameters."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        manager = ConfigManager(config_path=config_path)
        
        config = EternalGreenConfig(
            interval_seconds=interval_seconds,
            movement_pixels=movement_pixels,
            silent_mode=silent_mode,
            log_file_path=log_file_path
        )
        manager.save(config)
        
        cli = CLIInterface(config_manager=manager)
        output = cli.display_config()
        
        # Verify all four parameters are present in the output
        assert f"interval_seconds: {interval_seconds}" in output
        assert f"movement_pixels: {movement_pixels}" in output
        assert f"silent_mode: {silent_mode}" in output
        assert f"log_file_path: {log_file_path}" in output


# Feature: movement-patterns, Property 8: CLI rejects invalid pattern and preserves current config
# **Validates: Requirements 5.3, 5.4**
@settings(max_examples=100, deadline=None)
@given(
    invalid_pattern=st.text(min_size=0, max_size=50).filter(
        lambda x: x.strip() not in VALID_MOVEMENT_PATTERNS
    ),
    initial_pattern=st.sampled_from(VALID_MOVEMENT_PATTERNS),
)
def test_edit_movement_pattern_rejects_invalid_and_preserves_config(
    invalid_pattern,
    initial_pattern,
):
    """For any string NOT in VALID_MOVEMENT_PATTERNS, edit_movement_pattern returns False
    and the stored movement_pattern remains unchanged."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        manager = ConfigManager(config_path=config_path)

        config = EternalGreenConfig(movement_pattern=initial_pattern)
        manager.save(config)

        cli = CLIInterface(config_manager=manager)
        # Force load so the internal config is populated
        cli._config = manager.load()

        with patch("builtins.input", return_value=invalid_pattern):
            result = cli.edit_movement_pattern()

        assert result is False
        # Config value must be unchanged
        reloaded = manager.load()
        assert reloaded.movement_pattern == initial_pattern


def test_edit_movement_pattern_accepts_valid_patterns():
    """For each valid pattern, calling edit_movement_pattern persists the value and returns True."""
    for target_pattern in VALID_MOVEMENT_PATTERNS:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            manager = ConfigManager(config_path=config_path)

            # Start with a different pattern so we can observe the change
            other_patterns = [p for p in VALID_MOVEMENT_PATTERNS if p != target_pattern]
            initial_pattern = other_patterns[0] if other_patterns else target_pattern

            config = EternalGreenConfig(movement_pattern=initial_pattern)
            manager.save(config)

            cli = CLIInterface(config_manager=manager)
            cli._config = manager.load()

            with patch("builtins.input", return_value=target_pattern):
                result = cli.edit_movement_pattern()

            assert result is True
            reloaded = manager.load()
            assert reloaded.movement_pattern == target_pattern
