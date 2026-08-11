"""Tests for activity simulator."""

import random
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings, assume
import pytest
import pyautogui

from eternal_green.config import EternalGreenConfig
from eternal_green.simulator import ActivitySimulator


# Feature: eternal-green, Property: Bounce Movement Cursor Persists
# **Validates: Requirements 3.1, 3.2**
@settings(max_examples=100)
@given(
    start_x=st.integers(min_value=100, max_value=1000),
    start_y=st.integers(min_value=100, max_value=1000),
    movement_pixels=st.integers(min_value=1, max_value=100)
)
def test_bounce_movement_cursor_persists(start_x, start_y, movement_pixels):
    """After move_mouse, cursor stays at computed bounce target (no return to original)."""
    config = EternalGreenConfig(movement_pixels=movement_pixels)
    simulator = ActivitySimulator(config)
    
    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui:
        # Preserve real FailSafeException so except clause works
        mock_pyautogui.FailSafeException = pyautogui.FailSafeException
        mock_pyautogui.size.return_value = (1920, 1080)
        # position() returns start pos first, then a different pos after move
        mock_pyautogui.position.side_effect = [
            (start_x, start_y),
            (start_x + movement_pixels, start_y + movement_pixels),
        ]
        
        # Call move_mouse
        simulator.move_mouse(movement_pixels)
        
        # Verify moveTo was called exactly once (cursor stays at target, no return)
        mock_pyautogui.moveTo.assert_called_once()
        
        # Verify the moveTo call uses duration=0
        _, kwargs = mock_pyautogui.moveTo.call_args
        assert kwargs.get('duration', 0) == 0
        
        # Verify moveRel was NOT called (old round-trip behavior removed)
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
        # Preserve real FailSafeException so except clause works
        mock_pyautogui.FailSafeException = pyautogui.FailSafeException
        mock_pyautogui.position.side_effect = [
            (500, 500),
            (500 + movement_pixels, 500 + movement_pixels),
        ]
        mock_pyautogui.size.return_value = (1920, 1080)
        
        # Call simulate_activity
        simulator.simulate_activity()
        
        # Verify keystroke behavior based on silent_mode
        if silent_mode:
            # In silent mode, press should NOT be called
            mock_pyautogui.press.assert_not_called()
        else:
            # Not in silent mode, press should be called with 'shift'
            mock_pyautogui.press.assert_called_once_with('shift')



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
    
    # Set simulator as running (simulating being in the loop)
    simulator._running = True
    
    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui:
        # Preserve real FailSafeException so except clause works
        mock_pyautogui.FailSafeException = pyautogui.FailSafeException
        # Make pyautogui raise an exception
        mock_pyautogui.position.side_effect = Exception(error_message)
        
        # Call simulate_activity - should not raise
        result = simulator.simulate_activity()
        
        # Should return False indicating failure
        assert result is False
        
        # Error should be logged
        mock_logger.log_error.assert_called_once()
        
        # is_running should still be True (loop continues)
        assert simulator.is_running is True



# Feature: eternal-green, Property: FailSafeException Propagates
# **Validates: Requirements 5.3**
@settings(max_examples=100)
@given(
    movement_pixels=st.integers(min_value=1, max_value=100)
)
def test_failsafe_exception_propagates(movement_pixels):
    """FailSafeException raised during movement SHALL propagate out of simulate_activity uncaught."""
    config = EternalGreenConfig(movement_pixels=movement_pixels)
    mock_logger = MagicMock()
    simulator = ActivitySimulator(config, logger=mock_logger)

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui:
        mock_pyautogui.FailSafeException = pyautogui.FailSafeException
        # Make position() raise FailSafeException (simulating cursor at corner)
        mock_pyautogui.position.side_effect = pyautogui.FailSafeException(
            "PyAutoGUI fail-safe triggered"
        )

        # FailSafeException must propagate — simulate_activity should NOT catch it
        with pytest.raises(pyautogui.FailSafeException):
            simulator.simulate_activity()

        # Error logger should NOT have been called (exception was not handled)
        mock_logger.log_error.assert_not_called()



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
    
    # Generate multiple intervals to test randomness
    intervals = [simulator._get_next_interval() for _ in range(10)]
    
    # All intervals should be within the configured range
    for interval in intervals:
        assert min_interval <= interval <= max_interval
    
    # With enough samples, we should see some variation (not all the same)
    # This is probabilistic but with 10 samples from a range of at least 2, 
    # the chance of all being identical is extremely low
    if max_interval - min_interval > 1:
        assert len(set(intervals)) > 1, "Random intervals should vary"


# Feature: eternal-green, Property 1: Bounce Target Remains Within Usable Area
# **Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2**
@settings(max_examples=200)
@given(
    margin=st.integers(min_value=1, max_value=100),
    data=st.data(),
)
def test_bounce_target_within_usable_area(margin, data):
    """For any cursor position within the usable area and any diagonal direction,
    _compute_bounce_target SHALL produce a target within [margin, dim - margin]."""
    # Generate screen dimensions ensuring width > 2*margin and height > 2*margin
    screen_width = data.draw(
        st.integers(min_value=2 * margin + 1, max_value=4000),
        label="screen_width",
    )
    screen_height = data.draw(
        st.integers(min_value=2 * margin + 1, max_value=4000),
        label="screen_height",
    )

    # Generate cursor position within the usable area
    x = data.draw(
        st.integers(min_value=margin, max_value=screen_width - margin),
        label="x",
    )
    y = data.draw(
        st.integers(min_value=margin, max_value=screen_height - margin),
        label="y",
    )

    # Direction is one of the 4 valid diagonals with magnitude = margin
    dx = data.draw(st.sampled_from([-margin, margin]), label="dx")
    dy = data.draw(st.sampled_from([-margin, margin]), label="dy")

    # Call the pure static method
    target_x, target_y = ActivitySimulator._compute_bounce_target(
        x, y, dx, dy, margin, screen_width, screen_height
    )

    # Assert target remains within usable area
    assert margin <= target_x <= screen_width - margin, (
        f"target_x={target_x} outside usable area [{margin}, {screen_width - margin}]"
    )
    assert margin <= target_y <= screen_height - margin, (
        f"target_y={target_y} outside usable area [{margin}, {screen_height - margin}]"
    )


# Feature: eternal-green, Property 2: Cursor Persists at Computed Bounce Target
# **Validates: Requirements 3.1, 3.2**
@settings(max_examples=200)
@given(
    movement_pixels=st.integers(min_value=1, max_value=100),
    data=st.data(),
)
def test_cursor_persists_at_target(movement_pixels, data):
    """After move_mouse, moveTo is called exactly once with the _compute_bounce_target result.

    No second moveTo call returns the cursor to the original position.
    """
    # Generate screen dimensions large enough for movement to produce a distinct target
    # Need at least 3*margin so there's room for the cursor to actually move
    screen_width = data.draw(
        st.integers(min_value=3 * movement_pixels + 1, max_value=4000),
        label="screen_width",
    )
    screen_height = data.draw(
        st.integers(min_value=3 * movement_pixels + 1, max_value=4000),
        label="screen_height",
    )

    # Generate cursor position within the usable area (excluding exact boundary)
    start_x = data.draw(
        st.integers(min_value=movement_pixels, max_value=screen_width - movement_pixels),
        label="start_x",
    )
    start_y = data.draw(
        st.integers(min_value=movement_pixels, max_value=screen_height - movement_pixels),
        label="start_y",
    )

    # Generate a random diagonal direction
    dx = data.draw(st.sampled_from([-movement_pixels, movement_pixels]), label="dx")
    dy = data.draw(st.sampled_from([-movement_pixels, movement_pixels]), label="dy")

    # Compute expected target using the pure static method
    expected_x, expected_y = ActivitySimulator._compute_bounce_target(
        start_x, start_y, dx, dy, movement_pixels, screen_width, screen_height
    )

    # Skip degenerate case where bounce produces same position (no actual movement)
    assume(not (expected_x == start_x and expected_y == start_y))

    config = EternalGreenConfig(movement_pixels=movement_pixels)
    simulator = ActivitySimulator(config)

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui, \
         patch('eternal_green.simulator.random.choice', side_effect=[dx, dy]):
        mock_pyautogui.FailSafeException = pyautogui.FailSafeException
        mock_pyautogui.size.return_value = (screen_width, screen_height)
        # position() returns start pos first, then the target pos after move
        mock_pyautogui.position.side_effect = [
            (start_x, start_y),
            (expected_x, expected_y),
        ]

        simulator.move_mouse(movement_pixels)

        # 1. moveTo called exactly once (cursor stays at target, no return trip)
        mock_pyautogui.moveTo.assert_called_once()

        # 2. The moveTo arguments match the output of _compute_bounce_target
        call_args, call_kwargs = mock_pyautogui.moveTo.call_args
        assert call_args == (expected_x, expected_y), (
            f"moveTo called with {call_args}, expected ({expected_x}, {expected_y})"
        )
        assert call_kwargs.get('duration', 0) == 0

        # 3. No call returned cursor to original position
        for call in mock_pyautogui.moveTo.call_args_list:
            args, _ = call
            assert args != (start_x, start_y) or (start_x == expected_x and start_y == expected_y), (
                f"moveTo returned cursor to original position ({start_x}, {start_y})"
            )

        # 4. moveRel was NOT called (old round-trip behavior removed)
        mock_pyautogui.moveRel.assert_not_called()


# Feature: eternal-green, Property 3: Movement Vector Is a Valid Diagonal with Correct Magnitude
# **Validates: Requirements 4.1, 4.3**
@settings(max_examples=200)
@given(
    movement_pixels=st.integers(min_value=1, max_value=100),
)
def test_movement_vector_valid_diagonal(movement_pixels):
    """For any invocation of move_mouse(pixels), the movement vector (dx, dy) SHALL satisfy
    abs(dx) == pixels and abs(dy) == pixels, and SHALL be one of the 4 valid diagonals."""
    config = EternalGreenConfig(movement_pixels=movement_pixels)
    simulator = ActivitySimulator(config)

    # Track what random.choice returns for dx and dy
    chosen_values: list[int] = []
    original_choice = random.choice

    def capturing_choice(seq):
        result = original_choice(seq)
        chosen_values.append(result)
        return result

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui, \
         patch('eternal_green.simulator.random.choice', side_effect=capturing_choice):
        mock_pyautogui.FailSafeException = pyautogui.FailSafeException
        mock_pyautogui.size.return_value = (1920, 1080)
        mock_pyautogui.position.side_effect = [
            (500, 500),
            (500 + movement_pixels, 500 + movement_pixels),
        ]

        simulator.move_mouse(movement_pixels)

    # random.choice is called exactly twice: once for dx, once for dy
    assert len(chosen_values) == 2, (
        f"Expected 2 random.choice calls (dx, dy), got {len(chosen_values)}"
    )

    dx, dy = chosen_values

    # Each component has magnitude equal to pixels
    assert abs(dx) == movement_pixels, (
        f"abs(dx)={abs(dx)} != movement_pixels={movement_pixels}"
    )
    assert abs(dy) == movement_pixels, (
        f"abs(dy)={abs(dy)} != movement_pixels={movement_pixels}"
    )

    # The direction is one of the 4 valid diagonals
    valid_diagonals = [
        (movement_pixels, movement_pixels),
        (movement_pixels, -movement_pixels),
        (-movement_pixels, movement_pixels),
        (-movement_pixels, -movement_pixels),
    ]
    assert (dx, dy) in valid_diagonals, (
        f"Direction ({dx}, {dy}) is not a valid diagonal for pixels={movement_pixels}"
    )


def test_fixed_interval_when_random_disabled():
    """When random_interval is False, _get_next_interval returns fixed interval_seconds."""
    config = EternalGreenConfig(
        random_interval=False,
        interval_seconds=120,
        interval_range_min=10,
        interval_range_max=60
    )
    simulator = ActivitySimulator(config)
    
    # Should always return the fixed interval
    for _ in range(10):
        assert simulator._get_next_interval() == 120


# Feature: eternal-green, Property 5: Movement Verification Detects No-Move
# **Validates: Requirements 6.1, 6.2**
@settings(max_examples=200)
@given(
    start_x=st.integers(min_value=100, max_value=1000),
    start_y=st.integers(min_value=100, max_value=1000),
    movement_pixels=st.integers(min_value=1, max_value=100),
)
def test_movement_verification_detects_no_move(start_x, start_y, movement_pixels):
    """When cursor position does not change after moveTo, move_mouse SHALL raise
    RuntimeError indicating Accessibility permissions may not be granted."""
    config = EternalGreenConfig(movement_pixels=movement_pixels)
    simulator = ActivitySimulator(config)

    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui:
        mock_pyautogui.FailSafeException = pyautogui.FailSafeException
        mock_pyautogui.size.return_value = (1920, 1080)
        # position() returns the SAME value both before and after moveTo,
        # simulating that the cursor did not actually move (Accessibility denied)
        mock_pyautogui.position.return_value = (start_x, start_y)

        with pytest.raises(RuntimeError, match="Accessibility permissions"):
            simulator.move_mouse(movement_pixels)

        # moveTo should still have been called (the move was attempted)
        mock_pyautogui.moveTo.assert_called_once()
