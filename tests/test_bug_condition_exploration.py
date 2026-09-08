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


# ---------------------------------------------------------------------------
# Bug condition exploration: standard movement ignores configured pixels on a
# simulated scaled (Retina / HiDPI) display.
#
# This test surfaces counterexamples proving the coordinate-space bug exists.
# It is EXPECTED TO FAIL on unfixed code because _move_standard computes an
# absolute target from pyautogui.position()/size() (the READ space, logical
# points) and passes it to pyautogui.moveTo() (the WRITE space, backing-scaled
# physical pixels). On a scaled display these spaces differ by the backing
# scale factor, so a 2px intent lands a large fraction of the screen away.
#
# **Validates: Requirements 2.1, 2.2**
# ---------------------------------------------------------------------------


class _ScaledDisplayHarness:
    """Simulates a Retina / HiDPI display coordinate-space mismatch.

    The READ space (``position()``/``size()``) is expressed in logical points.
    The WRITE space (what ``moveTo``/``move`` actually consume) is a physical
    space that is ``scale`` times denser. We model the physical cursor position
    as ``logical * scale`` and record what the write path does so a caller can
    compute the *effective physical per-axis displacement* the cursor really
    experiences.

    - Absolute ``moveTo(target)``: the backend interprets ``target`` in the
      write space, so the physical position becomes ``target * scale``. Because
      the cursor started at logical ``start`` (physical ``start * scale``), the
      physical displacement is ``(target - start) * scale`` -- inflated by the
      scale factor (the bug).
    - Relative ``move(dx, dy)``: the backend displaces the cursor by ``(dx, dy)``
      directly, so the physical displacement is exactly ``(dx, dy)`` regardless
      of scale (the fix).
    """

    def __init__(self, start_x, start_y, screen_w, screen_h, scale):
        self.start_x = start_x
        self.start_y = start_y
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.scale = scale
        # Logical position reported by position(); moveTo may update it.
        self._logical_x = start_x
        self._logical_y = start_y
        self.moveto_calls = []
        self.move_calls = []

    def position(self):
        return (self._logical_x, self._logical_y)

    def size(self):
        return (self.screen_w, self.screen_h)

    def moveTo(self, x, y, duration=0):
        # Absolute write: target reinterpreted in the write space. Record it and
        # advance the logical position so _verify_moved sees movement.
        self.moveto_calls.append((x, y))
        self._logical_x = x
        self._logical_y = y

    def move(self, dx, dy, duration=0):
        # Relative write: displace by (dx, dy). Record and advance.
        self.move_calls.append((dx, dy))
        self._logical_x += dx
        self._logical_y += dy

    def effective_physical_displacement(self):
        """Physical per-axis displacement the cursor actually experienced.

        Returns (phys_dx, phys_dy). Works for whichever write path the code
        under test used (absolute moveTo or relative move).
        """
        if self.move_calls:
            # Relative move: physical displacement equals the requested delta.
            dx, dy = self.move_calls[-1]
            return (abs(dx), abs(dy))
        if self.moveto_calls:
            # Absolute moveTo: physical displacement is (target - start) * scale.
            tx, ty = self.moveto_calls[-1]
            return (
                abs(tx - self.start_x) * self.scale,
                abs(ty - self.start_y) * self.scale,
            )
        return (0, 0)


def _run_standard_move_on_scaled_display(start_x, start_y, screen_w, screen_h, pixels, scale):
    """Run _move_standard against a simulated scaled display.

    Seeds random so the diagonal choice is deterministic, patches the pyautogui
    surface with the harness, and returns the harness for inspection.
    """
    harness = _ScaledDisplayHarness(start_x, start_y, screen_w, screen_h, scale)
    config = EternalGreenConfig(
        movement_pattern="standard",
        movement_pixels=pixels,
    )
    simulator = ActivitySimulator(config)

    with patch("eternal_green.simulator.pyautogui.position", side_effect=harness.position), \
         patch("eternal_green.simulator.pyautogui.size", side_effect=harness.size), \
         patch("eternal_green.simulator.pyautogui.moveTo", side_effect=harness.moveTo), \
         patch("eternal_green.simulator.pyautogui.move", side_effect=harness.move, create=True), \
         patch("eternal_green.simulator.random.choice", side_effect=lambda seq: seq[-1]):
        # random.choice([-pixels, pixels]) -> pixels (positive diagonal, deterministic)
        simulator._move_standard(pixels)

    return harness


# Simulated backing scale factors: 2.0 (standard Retina), 1.5, 3.0 (HiDPI).
scaled_factors = st.sampled_from([2.0, 1.5, 3.0])
small_pixels = st.integers(min_value=1, max_value=5)


@settings(max_examples=50, deadline=None)
@given(
    start_x=st.integers(min_value=200, max_value=800),
    start_y=st.integers(min_value=200, max_value=600),
    pixels=small_pixels,
    scale=scaled_factors,
)
def test_bug_condition_standard_mid_screen_scaled_display(start_x, start_y, pixels, scale):
    """Case 1: mid-screen standard move on a simulated scaled display.

    The effective physical per-axis displacement SHALL equal movement_pixels.
    On unfixed code (absolute moveTo) the displacement is pixels * scale, so
    this assertion FAILS -- confirming the coordinate-space bug.
    """
    screen_w, screen_h = 1440, 900
    harness = _run_standard_move_on_scaled_display(
        start_x, start_y, screen_w, screen_h, pixels, scale
    )

    phys_dx, phys_dy = harness.effective_physical_displacement()
    assert phys_dx == pixels, (
        f"Expected physical x-displacement {pixels}px, got {phys_dx} "
        f"(scale={scale}, moveTo={harness.moveto_calls}, move={harness.move_calls})"
    )
    assert phys_dy == pixels, (
        f"Expected physical y-displacement {pixels}px, got {phys_dy} "
        f"(scale={scale}, moveTo={harness.moveto_calls}, move={harness.move_calls})"
    )


@settings(max_examples=50, deadline=None)
@given(
    pixels=small_pixels,
    scale=scaled_factors,
)
def test_bug_condition_standard_edge_adjacent_scaled_display(pixels, scale):
    """Case 2: edge-adjacent start on a simulated scaled display.

    Start just inside the left/top usable boundary (margin = pixels). The
    effective physical per-axis displacement SHALL equal movement_pixels and the
    cursor stays in the usable area. On unfixed code the displacement is
    pixels * scale -> FAILS.
    """
    screen_w, screen_h = 1440, 900
    # margin == pixels; start one pixel inside the usable area on both axes.
    start_x = pixels + 1
    start_y = pixels + 1

    harness = _run_standard_move_on_scaled_display(
        start_x, start_y, screen_w, screen_h, pixels, scale
    )

    phys_dx, phys_dy = harness.effective_physical_displacement()
    assert phys_dx == pixels, (
        f"Expected physical x-displacement {pixels}px near edge, got {phys_dx} "
        f"(scale={scale}, moveTo={harness.moveto_calls}, move={harness.move_calls})"
    )
    assert phys_dy == pixels, (
        f"Expected physical y-displacement {pixels}px near edge, got {phys_dy} "
        f"(scale={scale}, moveTo={harness.moveto_calls}, move={harness.move_calls})"
    )


@settings(max_examples=50, deadline=None)
@given(
    pixels=small_pixels,
    scale=scaled_factors,
)
def test_bug_condition_standard_corner_scaled_display(pixels, scale):
    """Case 3: corner start avoiding the fail-safe corner on a scaled display.

    Start at the top-left usable corner (margin, margin). The deterministic
    positive diagonal would push toward the interior (away from the (0,0)
    fail-safe corner). The effective physical per-axis displacement SHALL equal
    movement_pixels. On unfixed code the displacement is pixels * scale -> FAILS.
    """
    screen_w, screen_h = 1440, 900
    start_x = pixels  # top-left usable corner
    start_y = pixels

    harness = _run_standard_move_on_scaled_display(
        start_x, start_y, screen_w, screen_h, pixels, scale
    )

    phys_dx, phys_dy = harness.effective_physical_displacement()
    assert phys_dx == pixels, (
        f"Expected physical x-displacement {pixels}px from corner, got {phys_dx} "
        f"(scale={scale}, moveTo={harness.moveto_calls}, move={harness.move_calls})"
    )
    assert phys_dy == pixels, (
        f"Expected physical y-displacement {pixels}px from corner, got {phys_dy} "
        f"(scale={scale}, moveTo={harness.moveto_calls}, move={harness.move_calls})"
    )
