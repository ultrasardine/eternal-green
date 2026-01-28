"""Tests for activity simulator."""

from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings

from eternal_green.config import EternalGreenConfig
from eternal_green.simulator import ActivitySimulator


# Feature: eternal-green, Property 1: Mouse Movement Round-Trip
# **Validates: Requirements 1.3**
@settings(max_examples=100)
@given(
    start_x=st.integers(min_value=100, max_value=1000),
    start_y=st.integers(min_value=100, max_value=1000),
    movement_pixels=st.integers(min_value=1, max_value=100)
)
def test_mouse_movement_round_trip(start_x, start_y, movement_pixels):
    """For any mouse position and valid movement_pixels, cursor returns to original position."""
    config = EternalGreenConfig(movement_pixels=movement_pixels)
    simulator = ActivitySimulator(config)
    
    with patch('eternal_green.simulator.pyautogui') as mock_pyautogui:
        # Set up mock to return starting position
        mock_pyautogui.position.return_value = (start_x, start_y)
        
        # Call move_mouse
        simulator.move_mouse(movement_pixels)
        
        # Verify position was captured
        mock_pyautogui.position.assert_called_once()
        
        # Verify moveRel was called with the pixels
        mock_pyautogui.moveRel.assert_called_once_with(movement_pixels, movement_pixels, duration=0)
        
        # Verify moveTo was called to return to original position
        mock_pyautogui.moveTo.assert_called_once_with(start_x, start_y, duration=0)



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
        mock_pyautogui.position.return_value = (500, 500)
        
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
@settings(max_examples=100)
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
