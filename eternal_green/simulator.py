"""Activity simulator for eternal-green."""

import ctypes
import ctypes.util
import logging
import platform
import random
import signal
import threading
from typing import Optional

import pyautogui

from eternal_green.config import EternalGreenConfig
from eternal_green.logger import ActivityLogger

_log = logging.getLogger(__name__)


def _check_accessibility() -> bool:
    """Check if the process has macOS Accessibility permissions.

    Returns ``True`` on non-macOS platforms or when permissions are granted.
    """
    if platform.system() != "Darwin":
        return True
    try:
        lib = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework"
            "/ApplicationServices"
        )
        return bool(lib.AXIsProcessTrusted())
    except OSError:
        return True  # can't check — assume OK


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
        self._consecutive_failures = 0
    
    @staticmethod
    def _compute_bounce_target(
        x: int,
        y: int,
        dx: int,
        dy: int,
        margin: int,
        screen_width: int,
        screen_height: int,
    ) -> tuple[int, int]:
        """Compute target position with bounce logic.

        The usable area is defined as:
            x in [margin, screen_width - margin]
            y in [margin, screen_height - margin]

        If the naive target (x+dx, y+dy) would fall outside the usable area,
        the offending component is reversed (bounced).

        Args:
            x: Current cursor x position.
            y: Current cursor y position.
            dx: Horizontal movement (positive = right, negative = left).
            dy: Vertical movement (positive = down, negative = up).
            margin: Safe margin in pixels (equal to movement_pixels).
            screen_width: Total screen width from pyautogui.size().
            screen_height: Total screen height from pyautogui.size().

        Returns:
            Tuple of (target_x, target_y) guaranteed to be within usable area.
        """
        target_x = x + dx
        target_y = y + dy

        # Bounce horizontal component
        if target_x < margin or target_x > screen_width - margin:
            target_x = x - dx  # reverse direction

        # Bounce vertical component
        if target_y < margin or target_y > screen_height - margin:
            target_y = y - dy  # reverse direction

        # Clamp to usable area (handles edge cases where bounce still overshoots)
        target_x = max(margin, min(target_x, screen_width - margin))
        target_y = max(margin, min(target_y, screen_height - margin))

        return (target_x, target_y)

    def move_mouse(self, pixels: int) -> None:
        """Move mouse in a random diagonal direction with bounce logic.

        The cursor stays at its new position (no return to original).

        Args:
            pixels: Number of pixels to move in each axis.

        Raises:
            RuntimeError: If the mouse did not actually move (e.g. missing
                Accessibility permissions on macOS).
            pyautogui.FailSafeException: Propagated if triggered.
        """
        # Read current position
        original_x, original_y = pyautogui.position()

        # Select random diagonal direction
        dx = random.choice([-pixels, pixels])
        dy = random.choice([-pixels, pixels])

        # Get screen dimensions
        screen_width, screen_height = pyautogui.size()

        # Compute target with bounce
        target_x, target_y = self._compute_bounce_target(
            original_x, original_y, dx, dy, pixels, screen_width, screen_height
        )

        # Move cursor to target (cursor stays there)
        pyautogui.moveTo(target_x, target_y, duration=0)

        # Verify the mouse actually moved
        new_x, new_y = pyautogui.position()
        if new_x == original_x and new_y == original_y:
            raise RuntimeError(
                "Mouse did not move — Accessibility permissions may not be "
                "granted. Go to System Settings → Privacy & Security → "
                "Accessibility and add Eternal Green."
            )
    
    def press_key(self) -> None:
        """Press a neutral key (shift) that doesn't affect applications."""
        pyautogui.press('shift')
    
    def simulate_activity(self, next_interval: int = None) -> bool:
        """Perform one activity simulation cycle.
        
        Args:
            next_interval: Optional next interval duration to include in logs
        
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
            
            # Build message with interval info
            if next_interval is not None:
                message = f"Activity simulation completed - mouse moved {self.config.movement_pixels}px ({mode_str}), next in {next_interval}s"
            else:
                message = f"Activity simulation completed - mouse moved {self.config.movement_pixels}px ({mode_str})"
            
            # Print to console
            print(f"✓ {message}")
            
            # Log to file
            if self.logger:
                self.logger.log_activity(message)
            
            self._consecutive_failures = 0
            return True
            
        except pyautogui.FailSafeException:
            raise  # propagate fail-safe, never suppress
        except Exception as e:
            self._consecutive_failures += 1
            error_msg = f"Error during activity simulation: {e}"
            print(f"✗ {error_msg}")
            if self.logger:
                self.logger.log_error(error_msg)
            _log.exception("Activity simulation failed")
            return False

    def _get_next_interval(self) -> int:
        """Get the next interval duration based on configuration.
        
        Returns:
            Interval in seconds (random if enabled, fixed otherwise)
        """
        if self.config.random_interval:
            return random.randint(self.config.interval_range_min, self.config.interval_range_max)
        return self.config.interval_seconds
    
    def start_loop(self) -> None:
        """Start the idle prevention loop.
        
        Runs activity simulation at configured intervals until stop() is called
        or SIGINT is received.
        """
        self._running = True
        self._stop_event.clear()
        
        # Set up signal handler for graceful shutdown (only works in main thread)
        if threading.current_thread() is threading.main_thread():
            self._original_sigint_handler = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, self._handle_sigint)
        
        # Warn early if Accessibility permissions are missing
        if not _check_accessibility():
            warn_msg = (
                "Accessibility permissions not granted — mouse/keyboard "
                "simulation will not work. Go to System Settings → Privacy "
                "& Security → Accessibility and add Eternal Green."
            )
            print(f"⚠ {warn_msg}")
            if self.logger:
                self.logger.log_warning(warn_msg)
        
        if self.config.random_interval:
            start_msg = f"Starting idle prevention loop (random interval: {self.config.interval_range_min}-{self.config.interval_range_max}s)"
        else:
            start_msg = f"Starting idle prevention loop (interval: {self.config.interval_seconds}s)"
        
        print(f"▶ {start_msg}")
        if self.logger:
            self.logger.log_activity(start_msg)
        
        try:
            while self._running:
                # Get next interval (random or fixed)
                next_interval = self._get_next_interval()
                
                # Simulate activity with interval info
                self.simulate_activity(next_interval=next_interval)
                
                # Wait for interval or stop event
                if self._stop_event.wait(timeout=next_interval):
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
        if self._original_sigint_handler is not None and threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, self._original_sigint_handler)
            self._original_sigint_handler = None
    
    @property
    def is_running(self) -> bool:
        """Check if the simulation loop is currently running.
        
        Returns:
            True if the loop is running, False otherwise
        """
        return self._running
