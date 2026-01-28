"""Activity simulator for eternal-green."""

import signal
import threading
from typing import Optional

import pyautogui

from eternal_green.config import EternalGreenConfig
from eternal_green.logger import ActivityLogger


class ActivitySimulator:
    """Simulates user activity to prevent idle state."""
    
    def __init__(self, config: EternalGreenConfig, logger: Optional[ActivityLogger] = None):
        """Initialize simulator with configuration.
        
        Args:
            config: Configuration object with simulation parameters
            logger: Optional logger for activity events
        """
        self.config = config
        self.logger = logger
        self._running = False
        self._stop_event = threading.Event()
        self._original_sigint_handler = None
    
    def move_mouse(self, pixels: int) -> None:
        """Move mouse by specified pixels and return to original position.
        
        Args:
            pixels: Number of pixels to move
        """
        # Get current position
        original_x, original_y = pyautogui.position()
        
        # Move mouse by specified pixels
        pyautogui.moveRel(pixels, pixels, duration=0)
        
        # Return to original position
        pyautogui.moveTo(original_x, original_y, duration=0)
    
    def press_key(self) -> None:
        """Press a neutral key (shift) that doesn't affect applications."""
        pyautogui.press('shift')
    
    def simulate_activity(self) -> bool:
        """Perform one activity simulation cycle.
        
        Returns:
            True if simulation completed successfully, False otherwise
        """
        try:
            # Always move mouse
            self.move_mouse(self.config.movement_pixels)
            
            # Press key only if not in silent mode
            if not self.config.silent_mode:
                self.press_key()
            
            mode_str = "silent mode" if self.config.silent_mode else "with keystroke"
            message = f"Activity simulation completed - mouse moved {self.config.movement_pixels}px ({mode_str})"
            
            # Print to console
            print(f"✓ {message}")
            
            # Log to file
            if self.logger:
                self.logger.log_activity(message)
            
            return True
            
        except Exception as e:
            error_msg = f"Error during activity simulation: {e}"
            print(f"✗ {error_msg}")
            if self.logger:
                self.logger.log_error(error_msg)
            return False

    def start_loop(self) -> None:
        """Start the idle prevention loop.
        
        Runs activity simulation at configured intervals until stop() is called
        or SIGINT is received.
        """
        self._running = True
        self._stop_event.clear()
        
        # Set up signal handler for graceful shutdown
        self._original_sigint_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._handle_sigint)
        
        start_msg = f"Starting idle prevention loop (interval: {self.config.interval_seconds}s)"
        print(f"▶ {start_msg}")
        if self.logger:
            self.logger.log_activity(start_msg)
        
        try:
            while self._running:
                self.simulate_activity()
                
                # Wait for interval or stop event
                if self._stop_event.wait(timeout=self.config.interval_seconds):
                    break
        finally:
            self._cleanup()
    
    def stop(self) -> None:
        """Stop the loop gracefully."""
        self._running = False
        self._stop_event.set()
        
        print("■ Graceful shutdown initiated")
        if self.logger:
            self.logger.log_shutdown()
    
    def _handle_sigint(self, signum, frame) -> None:
        """Handle SIGINT signal for graceful shutdown.
        
        Args:
            signum: Signal number
            frame: Current stack frame
        """
        self.stop()
    
    def _cleanup(self) -> None:
        """Restore original signal handler."""
        if self._original_sigint_handler is not None:
            signal.signal(signal.SIGINT, self._original_sigint_handler)
            self._original_sigint_handler = None
    
    @property
    def is_running(self) -> bool:
        """Check if the simulation loop is currently running.
        
        Returns:
            True if the loop is running, False otherwise
        """
        return self._running
