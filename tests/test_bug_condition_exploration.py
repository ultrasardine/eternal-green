"""Bug condition exploration test for simulator stale config.

This test surfaces counterexamples proving the stale config bug exists.
It is EXPECTED TO FAIL on unfixed code because _start_simulator() does not
reload config when self.simulator is already set.

**Validates: Requirements 1.1, 1.2, 1.3**
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from hypothesis import given, strategies as st, settings

from eternal_green.config import ConfigManager, EternalGreenConfig, VALID_MOVEMENT_PATTERNS
from eternal_green.cli import CLIInterface
from eternal_green.logger import ActivityLogger
from eternal_green.simulator import ActivitySimulator


# Strategies for valid config values
valid_interval_seconds = st.integers(min_value=10, max_value=3600)
valid_movement_pixels = st.integers(min_value=1, max_value=100)
valid_movement_patterns = st.sampled_from(VALID_MOVEMENT_PATTERNS)


@settings(max_examples=50, deadline=None)
@given(
    new_interval=valid_interval_seconds,
    new_pixels=valid_movement_pixels,
)
def test_bug_condition_interval_and_pixels_stale_after_edit(
    new_interval,
    new_pixels,
):
    """After updating interval_seconds and movement_pixels via ConfigManager,
    _start_simulator() should use the new values. On unfixed code, the
    pre-existing simulator retains stale config values.

    Bug Condition: configWasEditedViaMenu AND self.simulator IS NOT None
    AND self.simulator.config != latestPersistedConfig()
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        log_path = Path(tmpdir) / "test.log"

        # Set up initial config (defaults)
        manager = ConfigManager(config_path=config_path)
        initial_config = EternalGreenConfig(log_file_path=str(log_path))
        manager.save(initial_config)

        # Pre-create simulator with initial config (mimics main())
        logger = ActivityLogger(str(log_path))
        simulator = ActivitySimulator(initial_config, logger)

        # Create CLI with pre-existing simulator (like main() does)
        cli = CLIInterface(config_manager=manager, simulator=simulator, logger=logger)

        # Simulate config edits via menu (persists to disk)
        manager.update(interval_seconds=new_interval, movement_pixels=new_pixels)

        # Mock start_loop to prevent actual simulation
        with patch.object(ActivitySimulator, "start_loop", return_value=None):
            cli._start_simulator()

        # Assert simulator uses the UPDATED config values
        # On unfixed code, these will FAIL because the stale simulator is reused
        assert cli.simulator.config.interval_seconds == new_interval, (
            f"Expected interval_seconds={new_interval}, "
            f"got {cli.simulator.config.interval_seconds} (stale config)"
        )
        assert cli.simulator.config.movement_pixels == new_pixels, (
            f"Expected movement_pixels={new_pixels}, "
            f"got {cli.simulator.config.movement_pixels} (stale config)"
        )


@settings(max_examples=50, deadline=None)
@given(
    new_pattern=valid_movement_patterns,
)
def test_bug_condition_movement_pattern_stale_after_edit(
    new_pattern,
):
    """After updating movement_pattern via ConfigManager, _start_simulator()
    should use the new pattern. On unfixed code, the pre-existing simulator
    retains the original pattern.

    Bug Condition: configWasEditedViaMenu AND self.simulator IS NOT None
    AND self.simulator.config != latestPersistedConfig()
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        log_path = Path(tmpdir) / "test.log"

        # Start with a known different pattern to ensure we see a change
        # Use "return_to_source" as initial so any other pattern is a change
        initial_pattern = "return_to_source"

        manager = ConfigManager(config_path=config_path)
        initial_config = EternalGreenConfig(
            movement_pattern=initial_pattern,
            log_file_path=str(log_path),
        )
        manager.save(initial_config)

        # Pre-create simulator with initial config (mimics main())
        logger = ActivityLogger(str(log_path))
        simulator = ActivitySimulator(initial_config, logger)

        # Create CLI with pre-existing simulator
        cli = CLIInterface(config_manager=manager, simulator=simulator, logger=logger)

        # Simulate pattern edit via menu
        manager.update(movement_pattern=new_pattern)

        # Mock start_loop to prevent actual simulation
        with patch.object(ActivitySimulator, "start_loop", return_value=None):
            cli._start_simulator()

        # Assert simulator uses the UPDATED pattern
        # On unfixed code, this will FAIL because the stale simulator is reused
        assert cli.simulator.config.movement_pattern == new_pattern, (
            f"Expected movement_pattern='{new_pattern}', "
            f"got '{cli.simulator.config.movement_pattern}' (stale config)"
        )


@settings(max_examples=20, deadline=None)
@given(
    log_suffix=st.text(
        alphabet=st.characters(whitelist_categories=("Ll",)),
        min_size=3,
        max_size=10,
    ),
)
def test_bug_condition_log_file_path_stale_after_edit(
    log_suffix,
):
    """After updating log_file_path via ConfigManager, _start_simulator()
    should create a logger with the new path. On unfixed code, the logger
    retains the original path.

    Bug Condition: configWasEditedViaMenu AND self.simulator IS NOT None
    AND self.simulator.config != latestPersistedConfig()
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        initial_log_path = str(Path(tmpdir) / "initial.log")
        new_log_path = str(Path(tmpdir) / f"{log_suffix}.log")

        manager = ConfigManager(config_path=config_path)
        initial_config = EternalGreenConfig(log_file_path=initial_log_path)
        manager.save(initial_config)

        # Pre-create simulator with initial config (mimics main())
        logger = ActivityLogger(initial_log_path)
        simulator = ActivitySimulator(initial_config, logger)

        # Create CLI with pre-existing simulator
        cli = CLIInterface(config_manager=manager, simulator=simulator, logger=logger)

        # Simulate log_file_path edit via menu
        manager.update(log_file_path=new_log_path)

        # Mock start_loop to prevent actual simulation
        with patch.object(ActivitySimulator, "start_loop", return_value=None):
            cli._start_simulator()

        # Assert logger uses the UPDATED path
        # On unfixed code, this will FAIL because the logger is never refreshed
        assert cli.logger.log_file_path == new_log_path, (
            f"Expected log_file_path='{new_log_path}', "
            f"got '{cli.logger.log_file_path}' (stale logger)"
        )
