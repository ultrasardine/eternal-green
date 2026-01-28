"""Tests for CLI interface."""

import tempfile
from pathlib import Path
from hypothesis import given, strategies as st, settings

from eternal_green.config import EternalGreenConfig, ConfigManager
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
