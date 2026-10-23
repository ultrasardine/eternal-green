"""Tests for activity simulator."""

import random
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings, assume
import pytest
import pyautogui

from eternal_green.config import EternalGreenConfig
from eternal_green.simulator import (
    ActivitySimulator,
    MAX_CONSECUTIVE_FAILURES,
    SAFE_MARGIN,
)


def _safe(width, height, margin):
    """Safe area of a single display at the origin, as the simulator computes it."""
    m = max(margin, SAFE_MARGIN)
    return (m, m, width - 1 - m, height - 1 - m)


# Feature: eternal-green, Property: Bounce Movement Cursor Persists
# **Validates: Requirements 3.1, 3.2**
@settings(max_examples=100)
@given(
    start_x=st.integers(min_value=100, max_value=1000),
    start_y=st.integers(min_value=100, max_value=1000),
    movement_pixels=st.integers(min_value=1, max_value=100)
)
def test_standard_movement_cursor_persists(start_x, start_y, movement_pixels):
    """After move_mouse, cursor stays at the computed target (no return to original)."""
    config = EternalGreenConfig(movement_pixels=movement_pixels, movement_pattern="standard")
    simulator = ActivitySimulator(config)

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui:
        mock_pyautogui.size.return_value = (1920, 1080)
        mock_pyautogui.position.side_effect = [
            (start_x, start_y),
            (start_x + movement_pixels, start_y + movement_pixels),
        ]

        simulator.move_mouse(movement_pixels)

        mock_pyautogui.moveTo.assert_called_once()
        _, kwargs = mock_pyautogui.moveTo.call_args
        assert kwargs.get('duration', 0) == 0
        # No pyautogui.PAUSE after each call
        assert kwargs.get('_pause') is False
        mock_pyautogui.moveRel.assert_not_called()


# Feature: eternal-green, Property 2: Silent Mode Conditional Keystroke
# **Validates: Requirements 1.2**
@settings(max_examples=100)
@given(
    silent_mode=st.booleans(),
    movement_pixels=st.integers(min_value=1, max_value=100)
)
def test_silent_mode_conditional_keystroke(silent_mode, movement_pixels):
    """Keystroke should be triggered if and only if silent_mode is False."""
    config = EternalGreenConfig(silent_mode=silent_mode, movement_pixels=movement_pixels)
    simulator = ActivitySimulator(config)

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui:
        mock_pyautogui.position.side_effect = [
            (500, 500),
            (500 + movement_pixels, 500 + movement_pixels),
        ]
        mock_pyautogui.size.return_value = (1920, 1080)

        simulator.simulate_activity()

        if silent_mode:
            mock_pyautogui.press.assert_not_called()
        else:
            mock_pyautogui.press.assert_called_once_with('shift', _pause=False)


# Feature: eternal-green, Property 3: Error Resilience
# **Validates: Requirements 1.5**
@settings(max_examples=100, deadline=None)
@given(
    error_message=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
    movement_pixels=st.integers(min_value=1, max_value=100)
)
def test_error_resilience(error_message, movement_pixels):
    """For any error during simulation, the simulator should log error and continue (is_running stays True)."""
    config = EternalGreenConfig(movement_pixels=movement_pixels)
    mock_logger = MagicMock()
    simulator = ActivitySimulator(config, logger=mock_logger)
    simulator._running = True

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui:
        mock_pyautogui.position.side_effect = Exception(error_message)

        result = simulator.simulate_activity()

        assert result is False
        mock_logger.log_error.assert_called_once()
        assert simulator.is_running is True


def test_repeated_failures_stop_the_loop():
    """After MAX_CONSECUTIVE_FAILURES failed cycles the simulator gives up."""
    mock_logger = MagicMock()
    simulator = ActivitySimulator(EternalGreenConfig(), logger=mock_logger)
    simulator._running = True

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui:
        mock_pyautogui.position.side_effect = RuntimeError("Mouse did not move")
        for _ in range(MAX_CONSECUTIVE_FAILURES - 1):
            simulator.simulate_activity()
            assert simulator.is_running
        simulator.simulate_activity()

    assert not simulator.is_running
    assert "consecutive failures" in mock_logger.log_error.call_args_list[-1].args[0]


def test_success_resets_failure_count():
    simulator = ActivitySimulator(EternalGreenConfig())
    simulator._running = True
    simulator._consecutive_failures = MAX_CONSECUTIVE_FAILURES - 1

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui:
        mock_pyautogui.size.return_value = (1920, 1080)
        mock_pyautogui.position.side_effect = [(500, 500), (502, 502)]
        assert simulator.simulate_activity() is True

    assert simulator._consecutive_failures == 0


# Feature: eternal-green, Property 4: Random Interval Generation
# **Validates: Random interval feature**
@settings(max_examples=100)
@given(
    min_interval=st.integers(min_value=10, max_value=100),
    max_interval=st.integers(min_value=101, max_value=3600)
)
def test_random_interval_generation(min_interval, max_interval):
    """When random_interval is enabled, _get_next_interval returns value within configured range."""
    config = EternalGreenConfig(
        random_interval=True,
        interval_range_min=min_interval,
        interval_range_max=max_interval
    )
    simulator = ActivitySimulator(config)

    intervals = [simulator._get_next_interval() for _ in range(10)]

    for interval in intervals:
        assert min_interval <= interval <= max_interval

    if max_interval - min_interval > 1:
        assert len(set(intervals)) > 1, "Random intervals should vary"


def test_fixed_interval_when_random_disabled():
    """When random_interval is False, _get_next_interval returns fixed interval_seconds."""
    config = EternalGreenConfig(
        random_interval=False,
        interval_seconds=120,
        interval_range_min=10,
        interval_range_max=60
    )
    simulator = ActivitySimulator(config)

    for _ in range(10):
        assert simulator._get_next_interval() == 120


# Feature: eternal-green, Property 1: Bounce Target Remains Within Safe Area
@settings(max_examples=200)
@given(
    margin=st.integers(min_value=1, max_value=100),
    data=st.data(),
)
def test_bounce_target_within_safe_area(margin, data):
    """From any cursor position — including corners and points outside the safe
    area — _compute_bounce_target lands inside the safe area."""
    left = data.draw(st.integers(min_value=-4000, max_value=4000), label="left")
    top = data.draw(st.integers(min_value=-2000, max_value=2000), label="top")
    width = data.draw(st.integers(min_value=2 * margin + 1, max_value=4000), label="width")
    height = data.draw(st.integers(min_value=2 * margin + 1, max_value=4000), label="height")
    bounds = (left + margin, top + margin, left + width - margin, top + height - margin)

    x = data.draw(st.integers(min_value=left, max_value=left + width), label="x")
    y = data.draw(st.integers(min_value=top, max_value=top + height), label="y")
    dx = data.draw(st.sampled_from([-margin, margin]), label="dx")
    dy = data.draw(st.sampled_from([-margin, margin]), label="dy")

    target_x, target_y = ActivitySimulator._compute_bounce_target(x, y, dx, dy, bounds)

    assert bounds[0] <= target_x <= bounds[2]
    assert bounds[1] <= target_y <= bounds[3]


# Feature: eternal-green, Property 2: Cursor Persists at Computed Target
@settings(max_examples=200)
@given(
    movement_pixels=st.integers(min_value=1, max_value=100),
    data=st.data(),
)
def test_cursor_persists_at_target(movement_pixels, data):
    """move_mouse calls moveTo exactly once with the _compute_bounce_target result."""
    screen_width = data.draw(st.integers(min_value=400, max_value=4000), label="screen_width")
    screen_height = data.draw(st.integers(min_value=400, max_value=4000), label="screen_height")
    bounds = _safe(screen_width, screen_height, movement_pixels)
    start_x = data.draw(st.integers(min_value=bounds[0], max_value=bounds[2]), label="start_x")
    start_y = data.draw(st.integers(min_value=bounds[1], max_value=bounds[3]), label="start_y")
    dx = data.draw(st.sampled_from([-movement_pixels, movement_pixels]), label="dx")
    dy = data.draw(st.sampled_from([-movement_pixels, movement_pixels]), label="dy")

    expected = ActivitySimulator._compute_bounce_target(start_x, start_y, dx, dy, bounds)
    assume(expected != (start_x, start_y))

    simulator = ActivitySimulator(EternalGreenConfig(movement_pixels=movement_pixels))

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui, \
         patch('eternal_green.simulator.random.choice', side_effect=[dx, dy]):
        mock_pyautogui.size.return_value = (screen_width, screen_height)
        mock_pyautogui.position.side_effect = [(start_x, start_y), expected]

        simulator.move_mouse(movement_pixels)

        mock_pyautogui.moveTo.assert_called_once()
        call_args, _ = mock_pyautogui.moveTo.call_args
        assert call_args == expected


@settings(max_examples=100)
@given(movement_pixels=st.integers(min_value=1, max_value=100))
def test_standard_moves_exactly_configured_pixels_mid_screen(movement_pixels):
    """Away from the edges, a standard move displaces by exactly movement_pixels."""
    simulator = ActivitySimulator(EternalGreenConfig(movement_pixels=movement_pixels))

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui:
        mock_pyautogui.size.return_value = (1920, 1080)
        mock_pyautogui.position.side_effect = [(960, 540), (0, 0)]
        simulator.move_mouse(movement_pixels)

    (x, y), _ = mock_pyautogui.moveTo.call_args
    assert abs(x - 960) == movement_pixels
    assert abs(y - 540) == movement_pixels


# Feature: eternal-green, Property 3: Movement Vector Is a Valid Diagonal
@settings(max_examples=200)
@given(movement_pixels=st.integers(min_value=1, max_value=100))
def test_movement_vector_valid_diagonal(movement_pixels):
    """The movement vector is one of the 4 diagonals with magnitude movement_pixels."""
    simulator = ActivitySimulator(EternalGreenConfig(movement_pixels=movement_pixels))

    chosen_values: list[int] = []
    original_choice = random.choice

    def capturing_choice(seq):
        result = original_choice(seq)
        chosen_values.append(result)
        return result

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui, \
         patch('eternal_green.simulator.random.choice', side_effect=capturing_choice):
        mock_pyautogui.size.return_value = (1920, 1080)
        mock_pyautogui.position.side_effect = [
            (500, 500),
            (500 + movement_pixels, 500 + movement_pixels),
        ]
        simulator.move_mouse(movement_pixels)

    assert len(chosen_values) == 2
    dx, dy = chosen_values
    assert abs(dx) == movement_pixels
    assert abs(dy) == movement_pixels


# Feature: eternal-green, Property 5: Movement Verification Detects No-Move
@settings(max_examples=200)
@given(
    start_x=st.integers(min_value=100, max_value=1000),
    start_y=st.integers(min_value=100, max_value=1000),
    movement_pixels=st.integers(min_value=1, max_value=100),
)
def test_movement_verification_detects_no_move(start_x, start_y, movement_pixels):
    """When cursor position does not change after moveTo, move_mouse raises RuntimeError."""
    simulator = ActivitySimulator(EternalGreenConfig(movement_pixels=movement_pixels))

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui:
        mock_pyautogui.size.return_value = (1920, 1080)
        mock_pyautogui.position.return_value = (start_x, start_y)

        with pytest.raises(RuntimeError, match="Accessibility permissions"):
            simulator.move_mouse(movement_pixels)

        mock_pyautogui.moveTo.assert_called_once()


# -----------------------------------------------------------------------------
# Corners and the pyautogui fail-safe
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("corner", [(0, 0), (1919, 0), (0, 1079), (1919, 1079)])
@pytest.mark.parametrize("pattern", ["standard", "return_to_source", "bounce"])
def test_cursor_in_corner_is_moved_to_safe_spot(corner, pattern):
    """A cursor parked in a corner is moved out instead of stopping the app."""
    mock_logger = MagicMock()
    simulator = ActivitySimulator(EternalGreenConfig(movement_pattern=pattern), logger=mock_logger)
    bounds = _safe(1920, 1080, 2)

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui, \
         patch('eternal_green.simulator.time.sleep'):
        mock_pyautogui.size.return_value = (1920, 1080)
        mock_pyautogui.position.side_effect = [corner, (960, 540)]
        simulator.move_mouse(2)

    for call in mock_pyautogui.moveTo.call_args_list:
        x, y = call.args
        assert bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]
    if pattern != "bounce":
        assert any("corner" in c.args[0] for c in mock_logger.log_activity.call_args_list)


def test_failsafe_disabled_during_moves_and_restored():
    """pyautogui's corner kill-switch is off while acting and restored afterwards."""
    simulator = ActivitySimulator(EternalGreenConfig())
    seen = []

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui:
        mock_pyautogui.FAILSAFE = True
        mock_pyautogui.size.return_value = (1920, 1080)
        mock_pyautogui.position.side_effect = [(0, 0), (12, 12)]
        mock_pyautogui.moveTo.side_effect = lambda *a, **k: seen.append(mock_pyautogui.FAILSAFE)
        simulator.move_mouse(2)
        assert mock_pyautogui.FAILSAFE is True

    assert seen == [False]


def test_real_pyautogui_corner_does_not_raise():
    """With pyautogui's real fail-safe check, a cursor parked in a corner is
    moved out and the cycle succeeds (only the OS backend is faked)."""
    simulator = ActivitySimulator(EternalGreenConfig(silent_mode=False))
    pos = [0, 0]

    def fake_move(x, y):
        pos[0], pos[1] = x, y

    with patch('pyautogui.position', side_effect=lambda *a: pyautogui.Point(*pos)), \
         patch('pyautogui.size', return_value=pyautogui.Size(1920, 1080)), \
         patch('pyautogui.platformModule._moveTo', side_effect=fake_move), \
         patch('pyautogui.platformModule._keyDown'), \
         patch('pyautogui.platformModule._keyUp'):
        assert pyautogui.FAILSAFE is True
        assert (0, 0) in pyautogui.FAILSAFE_POINTS
        assert simulator.simulate_activity() is True
        assert pyautogui.FAILSAFE is True

    assert pos != [0, 0]


# -----------------------------------------------------------------------------
# Return to source
# -----------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    movement_pixels=st.integers(min_value=1, max_value=100),
    data=st.data(),
)
def test_return_to_source_round_trip(movement_pixels, data):
    """From any position in the safe area, return_to_source glides back to it."""
    screen_width = data.draw(st.integers(min_value=400, max_value=4000), label="screen_width")
    screen_height = data.draw(st.integers(min_value=400, max_value=4000), label="screen_height")
    bounds = _safe(screen_width, screen_height, 0)
    start_x = data.draw(st.integers(min_value=bounds[0], max_value=bounds[2]), label="start_x")
    start_y = data.draw(st.integers(min_value=bounds[1], max_value=bounds[3]), label="start_y")

    simulator = ActivitySimulator(EternalGreenConfig(movement_pixels=movement_pixels))

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui, \
         patch('eternal_green.simulator.time.sleep') as mock_sleep:
        mock_pyautogui.position.return_value = (start_x, start_y)
        mock_pyautogui.size.return_value = (screen_width, screen_height)

        simulator._move_return_to_source(movement_pixels)

        mock_sleep.assert_called_once()
        assert 0.3 <= mock_sleep.call_args[0][0] <= 0.5
        assert mock_pyautogui.moveTo.call_count == 2
        final_args, final_kwargs = mock_pyautogui.moveTo.call_args_list[-1]
        assert final_args == (start_x, start_y)
        assert final_kwargs.get('duration', 0) == 0.3


# -----------------------------------------------------------------------------
# Bounce
# -----------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    movement_pixels=st.integers(min_value=1, max_value=50),
    dx_sign=st.sampled_from([-1, 1]),
    dy_sign=st.sampled_from([-1, 1]),
    data=st.data(),
)
def test_bounce_direction_persists_no_collision(movement_pixels, dx_sign, dy_sign, data):
    """Away from the edges, a bounce step keeps its direction."""
    screen_width = data.draw(st.integers(min_value=400, max_value=4000), label="screen_width")
    screen_height = data.draw(st.integers(min_value=400, max_value=4000), label="screen_height")
    min_x, min_y, max_x, max_y = _safe(screen_width, screen_height, movement_pixels)
    start_x = data.draw(st.integers(min_value=min_x + movement_pixels, max_value=max_x - movement_pixels), label="start_x")
    start_y = data.draw(st.integers(min_value=min_y + movement_pixels, max_value=max_y - movement_pixels), label="start_y")

    simulator = ActivitySimulator(EternalGreenConfig(movement_pixels=movement_pixels, movement_pattern="bounce"))
    simulator._bounce_direction = (dx_sign, dy_sign)

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui:
        mock_pyautogui.size.return_value = (screen_width, screen_height)
        mock_pyautogui.position.side_effect = [
            (start_x, start_y),
            (start_x + dx_sign * movement_pixels, start_y + dy_sign * movement_pixels),
        ]
        simulator._move_bounce(movement_pixels)

    assert simulator._bounce_direction == (dx_sign, dy_sign)


@settings(max_examples=100, deadline=None)
@given(
    movement_pixels=st.integers(min_value=1, max_value=50),
    collide_x=st.booleans(),
    collide_y=st.booleans(),
    x_direction=st.sampled_from([-1, 1]),
    y_direction=st.sampled_from([-1, 1]),
)
def test_bounce_reverses_offending_axis_on_collision(
    movement_pixels, collide_x, collide_y, x_direction, y_direction
):
    """A bounce step reverses exactly the axes that would leave the safe area."""
    assume(collide_x or collide_y)
    screen_width, screen_height = 1920, 1080
    min_x, min_y, max_x, max_y = _safe(screen_width, screen_height, movement_pixels)

    def start(collide, direction, low, high):
        if not collide:
            return (low + high) // 2
        return high if direction == 1 else low

    start_x = start(collide_x, x_direction, min_x, max_x)
    start_y = start(collide_y, y_direction, min_y, max_y)

    simulator = ActivitySimulator(EternalGreenConfig(movement_pixels=movement_pixels, movement_pattern="bounce"))
    simulator._bounce_direction = (x_direction, y_direction)

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui:
        mock_pyautogui.size.return_value = (screen_width, screen_height)
        mock_pyautogui.position.side_effect = [(start_x, start_y), (start_x + 1, start_y + 1)]
        simulator._move_bounce(movement_pixels)

    new_dx, new_dy = simulator._bounce_direction
    assert new_dx == (-x_direction if collide_x else x_direction)
    assert new_dy == (-y_direction if collide_y else y_direction)


def _glide_harness(simulator, interfere_at=None):
    """Patch pyautogui so the cursor follows moveTo, optionally with a user grab."""
    pos = [960, 540]
    calls = {"n": 0}

    def position():
        calls["n"] += 1
        if interfere_at is not None and calls["n"] == interfere_at:
            pos[0] += 50  # the user moves the mouse
        return tuple(pos)

    def move_to(x, y, **_kwargs):
        pos[0], pos[1] = x, y

    return pos, position, move_to


def test_bounce_glide_stops_when_user_takes_over():
    simulator = ActivitySimulator(EternalGreenConfig(movement_pattern="bounce"))
    simulator._bounce_direction = (1, 1)
    _, position, move_to = _glide_harness(simulator, interfere_at=5)

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui, \
         patch('eternal_green.simulator.time.sleep'):
        mock_pyautogui.size.return_value = (1920, 1080)
        mock_pyautogui.position.side_effect = position
        mock_pyautogui.moveTo.side_effect = move_to
        assert simulator._move_bounce(2, duration=3600) is False

    # Stopped right after the grab instead of gliding for an hour
    assert mock_pyautogui.moveTo.call_count < 5


def test_bounce_glide_stops_when_user_types():
    simulator = ActivitySimulator(EternalGreenConfig(movement_pattern="bounce"))
    simulator._bounce_direction = (1, 1)
    _, position, move_to = _glide_harness(simulator)

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui, \
         patch('eternal_green.simulator.time.sleep'), \
         patch('eternal_green.simulator.screen.seconds_since_key_input', return_value=0.0):
        mock_pyautogui.size.return_value = (1920, 1080)
        mock_pyautogui.position.side_effect = position
        mock_pyautogui.moveTo.side_effect = move_to
        # A key pressed "0s ago", after the glide started
        # glide start, loop check, then the key-idle comparison
        with patch('eternal_green.simulator.time.monotonic', side_effect=[0, 0, 5]):
            assert simulator._move_bounce(2, duration=3600) is False


def test_bounce_does_not_press_key_after_stop():
    """Stopping mid-glide must not send a trailing Shift press."""
    simulator = ActivitySimulator(EternalGreenConfig(movement_pattern="bounce", silent_mode=False))

    def glide(*_args, **_kwargs):
        simulator.stop()
        return True

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui, \
         patch('eternal_green.simulator._check_accessibility', return_value=True), \
         patch('eternal_green.simulator._start_caffeinate', return_value=None), \
         patch.object(simulator, '_idle_seconds', return_value=10_000), \
         patch.object(simulator, '_move_bounce', side_effect=glide):
        simulator.start_loop()

    mock_pyautogui.press.assert_not_called()


# -----------------------------------------------------------------------------
# Yielding to the user
# -----------------------------------------------------------------------------


def _run_loop_with_idle(simulator, idle_values):
    """Run start_loop with scripted idle times; stop when they run out."""
    idle_iter = iter(idle_values)

    def idle():
        try:
            return next(idle_iter)
        except StopIteration:
            simulator.stop()
            return 0.0

    with patch('eternal_green.simulator.pyautogui'), \
         patch('eternal_green.simulator._check_accessibility', return_value=True), \
         patch('eternal_green.simulator._start_caffeinate', return_value=None), \
         patch.object(simulator, '_idle_seconds', side_effect=idle), \
         patch.object(simulator._stop_event, 'wait', return_value=False) as wait, \
         patch.object(simulator, 'simulate_activity', return_value=True) as act:
        simulator.start_loop()
    return act, wait


def test_no_action_while_user_is_active():
    simulator = ActivitySimulator(EternalGreenConfig(interval_seconds=60))
    act, wait = _run_loop_with_idle(simulator, [5.0, 20.0])

    act.assert_not_called()
    assert wait.call_args_list[0].kwargs["timeout"] == 55.0
    assert wait.call_args_list[1].kwargs["timeout"] == 40.0


def test_acts_once_idle_for_the_interval():
    simulator = ActivitySimulator(EternalGreenConfig(interval_seconds=60))
    act, _ = _run_loop_with_idle(simulator, [5.0, 60.0])

    act.assert_called_once()


def test_fallback_idle_detects_user_mouse_movement():
    """Without OS idle time, unexplained cursor movement counts as user input."""
    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui, \
         patch('eternal_green.simulator.time.monotonic', side_effect=[0, 0, 100, 200, 300]):
        simulator = ActivitySimulator(EternalGreenConfig())  # t=0
        mock_pyautogui.position.return_value = (500, 500)
        simulator._mark_action()                     # t=0, we left the cursor at 500,500
        assert simulator._idle_seconds() == 100      # untouched since
        mock_pyautogui.position.return_value = (700, 650)
        assert simulator._idle_seconds() == 0        # t=200, the user moved it
        assert simulator._idle_seconds() == 100      # t=300, untouched since t=200


def test_os_idle_time_is_used_when_available():
    simulator = ActivitySimulator(EternalGreenConfig())
    with patch('eternal_green.simulator.screen.seconds_since_input', return_value=42.0):
        assert simulator._idle_seconds() == 42.0


# -----------------------------------------------------------------------------
# caffeinate
# -----------------------------------------------------------------------------


def test_caffeinate_started_and_terminated():
    """caffeinate runs for the duration of the loop and is stopped on exit."""
    simulator = ActivitySimulator(EternalGreenConfig())
    caffeinate = MagicMock()

    def stop_after_first_cycle(**_kwargs):
        simulator.stop()
        return True

    with patch('eternal_green.simulator.pyautogui'), \
         patch('eternal_green.simulator._check_accessibility', return_value=True), \
         patch('eternal_green.simulator._start_caffeinate', return_value=caffeinate), \
         patch.object(simulator, '_idle_seconds', return_value=10_000), \
         patch.object(simulator, 'simulate_activity', side_effect=stop_after_first_cycle):
        simulator.start_loop()

    caffeinate.terminate.assert_called_once()
    caffeinate.wait.assert_called_once()
    assert not simulator.is_running


def test_start_caffeinate_skipped_off_macos():
    """No caffeinate process is spawned on non-macOS platforms."""
    from eternal_green.simulator import _start_caffeinate

    with patch('eternal_green.simulator.platform.system', return_value="Linux"), \
         patch('eternal_green.simulator.subprocess.Popen') as mock_popen:
        assert _start_caffeinate() is None
    mock_popen.assert_not_called()
