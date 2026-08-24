"""Preservation property tests for simulator stale config bugfix.

These tests verify behavior that must remain UNCHANGED after the fix is applied.
They run on UNFIXED code and are expected to PASS, establishing the baseline
behavior that the fix must preserve.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from hypothesis import given, strategies as st, settings, assume

from eternal_green.config import ConfigManager, EternalGreenConfig, VALID_MOVEMENT_PATTERNS
from eternal_green.cli import CLIInterface
from eternal_green.logger import ActivityLogger
from eternal_green.simulator import ActivitySimulator


# --- Strategies for valid config values ---

valid_interval_seconds = st.integers(min_value=10, max_value=3600)
valid_movement_pixels = st.integers(min_value=1, max_value=100)
valid_movement_patterns = st.sampled_from(VALID_MOVEMENT_PATTERNS)
valid_silent_mode = st.booleans()
valid_random_interval = st.booleans()
valid_interval_range_min = st.integers(min_value=10, max_value=1799)
valid_interval_range_max = st.integers(min_value=1800, max_value=3600)


# =============================================================================
# Property 2: Preservation - Non-Edit Simulator Start
# =============================================================================


@settings(max_examples=50, deadline=None)
@given(
    interval_seconds=valid_interval_seconds,
    movement_pixels=valid_movement_pixels,
    movement_pattern=valid_movement_patterns,
    silent_mode=valid_silent_mode,
)
def test_preservation_no_edit_start_uses_disk_config(
    interval_seconds,
    movement_pixels,
    movement_pattern,
    silent_mode,
):
    """For any valid EternalGreenConfig, starting the simulator WITHOUT prior edits
    (self.simulator=None) creates a simulator with the correct disk config.

    This is the preservation case: when no pre-existing simulator is set,
    _start_simulator() loads from disk and creates a fresh simulator.

    **Validates: Requirements 3.1**
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        log_path = Path(tmpdir) / "test.log"

        # Save a config to disk
        manager = ConfigManager(config_path=config_path)
        config = EternalGreenConfig(
            interval_seconds=interval_seconds,
            movement_pixels=movement_pixels,
            movement_pattern=movement_pattern,
            silent_mode=silent_mode,
            log_file_path=str(log_path),
        )
        manager.save(config)

        # Create CLI WITHOUT a pre-existing simulator (self.simulator=None)
        cli = CLIInterface(config_manager=manager, simulator=None, logger=None)

        # Mock start_loop to prevent actual simulation
        with patch.object(ActivitySimulator, "start_loop", return_value=None):
            cli._start_simulator()

        # Verify the simulator was created with the disk config values
        assert cli.simulator is not None
        assert cli.simulator.config.interval_seconds == interval_seconds
        assert cli.simulator.config.movement_pixels == movement_pixels
        assert cli.simulator.config.movement_pattern == movement_pattern
        assert cli.simulator.config.silent_mode == silent_mode


# =============================================================================
# Property 2: Preservation - ConfigManager.update() persists and retrieves
# =============================================================================


@settings(max_examples=50, deadline=None)
@given(
    initial_interval=valid_interval_seconds,
    new_interval=valid_interval_seconds,
    initial_pixels=valid_movement_pixels,
    new_pixels=valid_movement_pixels,
    new_pattern=valid_movement_patterns,
)
def test_preservation_config_update_persists_and_loads(
    initial_interval,
    new_interval,
    initial_pixels,
    new_pixels,
    new_pattern,
):
    """For any valid config update kwargs, ConfigManager.update() persists them
    to disk and they are retrievable via load().

    **Validates: Requirements 3.2**
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        log_path = Path(tmpdir) / "test.log"

        # Save initial config
        manager = ConfigManager(config_path=config_path)
        initial_config = EternalGreenConfig(
            interval_seconds=initial_interval,
            movement_pixels=initial_pixels,
            log_file_path=str(log_path),
        )
        manager.save(initial_config)

        # Update config via ConfigManager.update()
        updated = manager.update(
            interval_seconds=new_interval,
            movement_pixels=new_pixels,
            movement_pattern=new_pattern,
        )

        # Verify the returned config has updated values
        assert updated.interval_seconds == new_interval
        assert updated.movement_pixels == new_pixels
        assert updated.movement_pattern == new_pattern

        # Verify a fresh load() retrieves the updated values from disk
        fresh_manager = ConfigManager(config_path=config_path)
        loaded = fresh_manager.load()
        assert loaded.interval_seconds == new_interval
        assert loaded.movement_pixels == new_pixels
        assert loaded.movement_pattern == new_pattern


# =============================================================================
# Property 2: Preservation - Constructor dependency injection
# =============================================================================


def test_preservation_constructor_injection_simulator_used():
    """CLIInterface accepts explicit simulator/logger via constructor and
    _start_simulator() creates a fresh simulator with the latest disk config.

    The constructor still accepts simulator/logger for initialization, but
    _start_simulator() always creates a fresh simulator to ensure the latest
    persisted config is used.

    **Validates: Requirements 3.4**
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        log_path = Path(tmpdir) / "test.log"

        manager = ConfigManager(config_path=config_path)
        config = EternalGreenConfig(
            interval_seconds=30,
            movement_pixels=5,
            log_file_path=str(log_path),
        )
        manager.save(config)

        # Create explicit logger and simulator
        logger = ActivityLogger(str(log_path))
        simulator = MagicMock(spec=ActivitySimulator)
        simulator.config = config
        simulator.start_loop = MagicMock(return_value=None)

        # Inject via constructor - verifies CLIInterface still accepts these
        cli = CLIInterface(config_manager=manager, simulator=simulator, logger=logger)

        # Verify constructor injection works
        assert cli.simulator is simulator
        assert cli.logger is logger

        # _start_simulator() creates a fresh simulator with latest disk config
        with patch.object(ActivitySimulator, "start_loop", return_value=None):
            cli._start_simulator()

        # Verify a fresh simulator was created (not the injected mock)
        assert cli.simulator is not simulator
        assert isinstance(cli.simulator, ActivitySimulator)

        # Verify the fresh simulator has the correct disk config values
        assert cli.simulator.config.interval_seconds == 30
        assert cli.simulator.config.movement_pixels == 5
        assert cli.simulator.config.log_file_path == str(log_path)


# =============================================================================
# Property 2: Preservation - Graceful shutdown via KeyboardInterrupt
# =============================================================================


def test_preservation_graceful_shutdown_keyboard_interrupt():
    """When KeyboardInterrupt is raised during start_loop, _start_simulator()
    catches it gracefully and does not propagate the exception.

    **Validates: Requirements 3.3**
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        log_path = Path(tmpdir) / "test.log"

        manager = ConfigManager(config_path=config_path)
        config = EternalGreenConfig(log_file_path=str(log_path))
        manager.save(config)

        # Create CLI without pre-existing simulator
        cli = CLIInterface(config_manager=manager, simulator=None, logger=None)

        # Mock start_loop to raise KeyboardInterrupt (simulates Ctrl+C)
        with patch.object(ActivitySimulator, "start_loop", side_effect=KeyboardInterrupt):
            # Should NOT propagate the exception
            cli._start_simulator()

        # If we reach here, graceful shutdown worked
        assert cli.simulator is not None


# =============================================================================
# Property 2: Preservation - Validation errors still rejected
# =============================================================================


@settings(max_examples=30, deadline=None)
@given(
    bad_interval=st.integers().filter(lambda x: x < 10 or x > 3600),
)
def test_preservation_validation_errors_rejected(bad_interval):
    """When invalid configuration values are entered via ConfigManager,
    validation errors are raised and changes are rejected.

    **Validates: Requirements 3.5**
    """
    import pytest

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        log_path = Path(tmpdir) / "test.log"

        manager = ConfigManager(config_path=config_path)
        config = EternalGreenConfig(log_file_path=str(log_path))
        manager.save(config)

        # Attempting to update with invalid values should raise ValueError
        with pytest.raises(ValueError, match="Invalid configuration"):
            manager.update(interval_seconds=bad_interval)

        # Original config should be unchanged on disk
        loaded = manager.load()
        assert loaded.interval_seconds == config.interval_seconds
