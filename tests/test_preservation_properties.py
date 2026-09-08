"""Preservation property tests for simulator stale config bugfix.

These tests verify behavior that must remain UNCHANGED after the fix is applied.
They run on UNFIXED code and are expected to PASS, establishing the baseline
behavior that the fix must preserve.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
"""

import random
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


# =============================================================================
# Preservation tests for the "standard movement ignores config" bugfix.
#
# These tests establish the baseline behavior that the standard-pattern fix
# (switching _move_standard from an absolute pyautogui.moveTo to a relative
# pyautogui.move) MUST preserve. They follow the observation-first methodology:
# the exact pyautogui call sequences and the standard edge-clamp behavior were
# observed on the UNFIXED code, recorded here as expected values, and asserted.
#
# On UNFIXED code these tests PASS (they encode current behavior). After the fix
# they must STILL pass, because:
#   - The other patterns (random_direction, return_to_source, bounce) are out of
#     scope and must make byte-for-byte identical pyautogui calls (Req 3.1-3.3).
#   - The standard edge-clamp assertion is written against the *resulting
#     cursor position within the usable area*, not the absolute moveTo target,
#     so it holds whether the code issues moveTo(target) or move(effective_delta)
#     (Req 3.4).
#
# **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
# =============================================================================


class _RecordingPyautoguiHarness:
    """Records the sequence of pyautogui write calls and reports position/size.

    ``position()`` returns queued positions in order (falling back to the last
    one) so that ``_verify_moved`` observes movement. Every write call
    (``moveTo``/``move``) is appended to ``calls`` as a normalized tuple so two
    runs can be compared byte-for-byte.
    """

    def __init__(self, positions, screen_w, screen_h):
        self._positions = list(positions)
        self._idx = 0
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.calls = []

    def position(self):
        if self._idx < len(self._positions):
            pos = self._positions[self._idx]
            self._idx += 1
            return pos
        return self._positions[-1]

    def size(self):
        return (self.screen_w, self.screen_h)

    def moveTo(self, x, y, duration=0):
        self.calls.append(("moveTo", x, y, duration))

    def move(self, dx, dy, duration=0):
        self.calls.append(("move", dx, dy, duration))


def _capture_pattern_calls(pattern, pixels, positions, screen_w, screen_h, seed):
    """Run a movement pattern handler once and return the recorded call list.

    Seeds ``random`` deterministically and patches the pyautogui surface with a
    recording harness. Also patches ``time.sleep`` so return_to_source does not
    actually pause. Returns the ordered list of write calls.
    """
    harness = _RecordingPyautoguiHarness(positions, screen_w, screen_h)
    config = EternalGreenConfig(movement_pattern=pattern, movement_pixels=pixels)
    simulator = ActivitySimulator(config)

    with patch("eternal_green.simulator.pyautogui.position", side_effect=harness.position), \
         patch("eternal_green.simulator.pyautogui.size", side_effect=harness.size), \
         patch("eternal_green.simulator.pyautogui.moveTo", side_effect=harness.moveTo), \
         patch("eternal_green.simulator.pyautogui.move", side_effect=harness.move, create=True), \
         patch("eternal_green.simulator.time.sleep", return_value=None):
        random.seed(seed)
        handler = simulator._pattern_dispatch[pattern]
        handler(pixels)

    return harness.calls


# Strategies for interior start positions on a fixed screen and seeded randomness.
interior_x = st.integers(min_value=200, max_value=1200)
interior_y = st.integers(min_value=200, max_value=700)
random_seed = st.integers(min_value=0, max_value=2**32 - 1)


# -----------------------------------------------------------------------------
# Property 2: Preservation - random_direction call sequence unchanged (Req 3.1)
# -----------------------------------------------------------------------------


@settings(max_examples=50, deadline=None)
@given(
    start_x=interior_x,
    start_y=interior_y,
    pixels=valid_movement_pixels,
    seed=random_seed,
)
def test_preservation_random_direction_call_sequence(start_x, start_y, pixels, seed):
    """random_direction produces a deterministic pyautogui call sequence for a
    given seed/start, and that sequence is the baseline the fix must preserve.

    Observed on UNFIXED code: a single absolute moveTo to the bounce-clamped
    target with duration=0. Recomputing the expected target with the same seed
    and asserting the exact call list captures the byte-for-byte contract.

    **Validates: Requirements 3.1**
    """
    screen_w, screen_h = 1920, 1080
    # After the move the cursor is at the target, so _verify_moved sees movement.
    # Compute the expected target using the same seeded random draw order.
    random.seed(seed)
    dx = random.choice([-pixels, pixels])
    dy = random.choice([-pixels, pixels])
    target_x, target_y = ActivitySimulator._compute_bounce_target(
        start_x, start_y, dx, dy, pixels, screen_w, screen_h
    )

    calls = _capture_pattern_calls(
        "random_direction",
        pixels,
        positions=[(start_x, start_y), (target_x, target_y)],
        screen_w=screen_w,
        screen_h=screen_h,
        seed=seed,
    )

    assert calls == [("moveTo", target_x, target_y, 0)], (
        f"random_direction call sequence changed: {calls}"
    )


# -----------------------------------------------------------------------------
# Property 2: Preservation - return_to_source call sequence unchanged (Req 3.2)
# -----------------------------------------------------------------------------


@settings(max_examples=50, deadline=None)
@given(
    start_x=interior_x,
    start_y=interior_y,
    pixels=valid_movement_pixels,
    seed=random_seed,
)
def test_preservation_return_to_source_call_sequence(start_x, start_y, pixels, seed):
    """return_to_source makes a visible outward excursion then glides back to the
    origin, and the exact two-moveTo sequence must be preserved.

    Observed on UNFIXED code: moveTo(target, duration=0.3) then
    moveTo(origin, duration=0.3), with the excursion magnitude min(pixels*20, 100).

    **Validates: Requirements 3.2**
    """
    screen_w, screen_h = 1920, 1080
    excursion = min(pixels * 20, 100)

    # Reproduce the seeded random draw order used by the handler.
    random.seed(seed)
    dx = random.choice([-excursion, excursion])
    dy = random.choice([-excursion, excursion])
    target_x, target_y = ActivitySimulator._compute_bounce_target(
        start_x, start_y, dx, dy, excursion, screen_w, screen_h
    )
    # The handler also draws random.uniform(0.3, 0.5) for the sleep between moves.

    calls = _capture_pattern_calls(
        "return_to_source",
        pixels,
        positions=[(start_x, start_y)],
        screen_w=screen_w,
        screen_h=screen_h,
        seed=seed,
    )

    assert calls == [
        ("moveTo", target_x, target_y, 0.3),
        ("moveTo", start_x, start_y, 0.3),
    ], f"return_to_source call sequence changed: {calls}"


# -----------------------------------------------------------------------------
# Property 2: Preservation - bounce (single-step) call sequence unchanged (Req 3.3)
# -----------------------------------------------------------------------------


@settings(max_examples=50, deadline=None)
@given(
    start_x=interior_x,
    start_y=interior_y,
    pixels=valid_movement_pixels,
    seed=random_seed,
)
def test_preservation_bounce_single_step_call_sequence(start_x, start_y, pixels, seed):
    """bounce single-step mode (duration=0) makes one discrete moveTo in the
    current direction, reversing an axis at an edge. The call sequence must be
    preserved.

    Observed on UNFIXED code: a single moveTo(target, duration=0) where target is
    derived from the seeded initial bounce direction, with edge reversal/clamp.

    **Validates: Requirements 3.3**
    """
    screen_w, screen_h = 1920, 1080
    margin = pixels

    # Reproduce the seeded bounce-direction draw (two random.choice([-1, 1])).
    random.seed(seed)
    dx_sign = random.choice([-1, 1])
    dy_sign = random.choice([-1, 1])

    # Reproduce the single-step target math from _move_bounce (duration<=0 path).
    target_x = start_x + dx_sign * pixels
    target_y = start_y + dy_sign * pixels
    if target_x < margin or target_x > screen_w - margin:
        dx_sign = -dx_sign
        target_x = start_x + dx_sign * pixels
    if target_y < margin or target_y > screen_h - margin:
        dy_sign = -dy_sign
        target_y = start_y + dy_sign * pixels
    target_x = max(margin, min(target_x, screen_w - margin))
    target_y = max(margin, min(target_y, screen_h - margin))

    harness = _RecordingPyautoguiHarness(
        [(start_x, start_y), (target_x, target_y)], screen_w, screen_h
    )
    config = EternalGreenConfig(movement_pattern="bounce", movement_pixels=pixels)
    simulator = ActivitySimulator(config)

    with patch("eternal_green.simulator.pyautogui.position", side_effect=harness.position), \
         patch("eternal_green.simulator.pyautogui.size", side_effect=harness.size), \
         patch("eternal_green.simulator.pyautogui.moveTo", side_effect=harness.moveTo), \
         patch("eternal_green.simulator.pyautogui.move", side_effect=harness.move, create=True):
        random.seed(seed)
        simulator._move_bounce(pixels, duration=0)

    assert harness.calls == [("moveTo", target_x, target_y, 0)], (
        f"bounce single-step call sequence changed: {harness.calls}"
    )


# -----------------------------------------------------------------------------
# Property 2: Preservation - standard edge clamping keeps cursor in usable area
# (Req 3.4). Asserted on the RESULTING position, not the absolute moveTo target,
# so it holds after the fix switches to a relative pyautogui.move.
# -----------------------------------------------------------------------------


def _resulting_position_after_standard(harness):
    """Derive the resulting cursor position from whichever write path was used.

    Absolute moveTo -> the target coordinates. Relative move -> start + delta.
    This lets the same assertion validate both the unfixed (moveTo) and fixed
    (move) implementations.
    """
    start_x, start_y = harness._positions[0]
    if harness.calls:
        kind = harness.calls[-1][0]
        if kind == "moveTo":
            _, x, y, _ = harness.calls[-1]
            return (x, y)
        if kind == "move":
            _, dx, dy, _ = harness.calls[-1]
            return (start_x + dx, start_y + dy)
    return (start_x, start_y)


# Small screen so edge/corner starts are meaningful.
edge_pixels = st.integers(min_value=1, max_value=20)


@settings(max_examples=50, deadline=None)
@given(
    pixels=edge_pixels,
    seed=random_seed,
    corner=st.sampled_from(["tl", "tr", "bl", "br"]),
)
def test_preservation_standard_edge_clamp_stays_in_usable_area(pixels, seed, corner):
    """A standard move starting at a usable-area corner keeps the cursor within
    the usable area [margin, dim - margin] on each axis (margin = movement_pixels).

    This is asserted on the resulting position (not the absolute moveTo target)
    so the assertion survives the fix's switch to a relative pyautogui.move.

    **Validates: Requirements 3.4**
    """
    screen_w, screen_h = 400, 300
    margin = pixels
    corners = {
        "tl": (margin, margin),
        "tr": (screen_w - margin, margin),
        "bl": (margin, screen_h - margin),
        "br": (screen_w - margin, screen_h - margin),
    }
    start_x, start_y = corners[corner]

    # Predict the target so _verify_moved (position() second call) sees movement.
    random.seed(seed)
    dx = random.choice([-pixels, pixels])
    dy = random.choice([-pixels, pixels])
    target_x, target_y = ActivitySimulator._compute_bounce_target(
        start_x, start_y, dx, dy, pixels, screen_w, screen_h
    )

    harness = _RecordingPyautoguiHarness(
        [(start_x, start_y), (target_x, target_y)], screen_w, screen_h
    )
    config = EternalGreenConfig(movement_pattern="standard", movement_pixels=pixels)
    simulator = ActivitySimulator(config)

    with patch("eternal_green.simulator.pyautogui.position", side_effect=harness.position), \
         patch("eternal_green.simulator.pyautogui.size", side_effect=harness.size), \
         patch("eternal_green.simulator.pyautogui.moveTo", side_effect=harness.moveTo), \
         patch("eternal_green.simulator.pyautogui.move", side_effect=harness.move, create=True):
        random.seed(seed)
        simulator._move_standard(pixels)

    result_x, result_y = _resulting_position_after_standard(harness)
    assert margin <= result_x <= screen_w - margin, (
        f"standard move x={result_x} left usable area "
        f"[{margin}, {screen_w - margin}] (corner={corner}, calls={harness.calls})"
    )
    assert margin <= result_y <= screen_h - margin, (
        f"standard move y={result_y} left usable area "
        f"[{margin}, {screen_h - margin}] (corner={corner}, calls={harness.calls})"
    )


# -----------------------------------------------------------------------------
# Property 2: Preservation - _verify_moved fail-safe after a standard move
# -----------------------------------------------------------------------------


@settings(max_examples=50, deadline=None)
@given(
    start_x=interior_x,
    start_y=interior_y,
    pixels=valid_movement_pixels,
    seed=random_seed,
)
def test_preservation_standard_verify_moved_invoked(start_x, start_y, pixels, seed):
    """After a standard move, _verify_moved(original_x, original_y) is invoked
    with the pre-move position (fail-safe preservation).

    **Validates: Requirements 3.4**
    """
    screen_w, screen_h = 1920, 1080
    random.seed(seed)
    dx = random.choice([-pixels, pixels])
    dy = random.choice([-pixels, pixels])
    target_x, target_y = ActivitySimulator._compute_bounce_target(
        start_x, start_y, dx, dy, pixels, screen_w, screen_h
    )

    harness = _RecordingPyautoguiHarness(
        [(start_x, start_y), (target_x, target_y)], screen_w, screen_h
    )
    config = EternalGreenConfig(movement_pattern="standard", movement_pixels=pixels)
    simulator = ActivitySimulator(config)

    with patch("eternal_green.simulator.pyautogui.position", side_effect=harness.position), \
         patch("eternal_green.simulator.pyautogui.size", side_effect=harness.size), \
         patch("eternal_green.simulator.pyautogui.moveTo", side_effect=harness.moveTo), \
         patch("eternal_green.simulator.pyautogui.move", side_effect=harness.move, create=True), \
         patch.object(ActivitySimulator, "_verify_moved", autospec=True) as mock_verify:
        random.seed(seed)
        simulator._move_standard(pixels)

    mock_verify.assert_called_once_with(simulator, start_x, start_y)


def test_preservation_standard_verify_moved_raises_when_no_movement():
    """_verify_moved raises RuntimeError when position() reports no movement
    after a standard move (missing Accessibility permissions fail-safe).

    **Validates: Requirements 3.4**
    """
    import pytest

    screen_w, screen_h = 1920, 1080
    start_x, start_y = 500, 500
    pixels = 5

    # position() reports the SAME coordinates before and after the move, so
    # _verify_moved must raise. The harness returns the last position on repeat.
    harness = _RecordingPyautoguiHarness([(start_x, start_y)], screen_w, screen_h)
    config = EternalGreenConfig(movement_pattern="standard", movement_pixels=pixels)
    simulator = ActivitySimulator(config)

    with patch("eternal_green.simulator.pyautogui.position", side_effect=harness.position), \
         patch("eternal_green.simulator.pyautogui.size", side_effect=harness.size), \
         patch("eternal_green.simulator.pyautogui.moveTo", side_effect=harness.moveTo), \
         patch("eternal_green.simulator.pyautogui.move", side_effect=harness.move, create=True):
        random.seed(0)
        with pytest.raises(RuntimeError, match="Mouse did not move"):
            simulator._move_standard(pixels)
