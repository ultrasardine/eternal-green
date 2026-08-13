"""Activity simulator for eternal-green."""

import ctypes
import ctypes.util
import logging
import platform
import random
import signal
import threading
import time
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
        self._bounce_direction: tuple[int, int] | None = None
        self._pattern_dispatch: dict[str, callable] = {
            "standard": self._move_standard,
            "random_direction": self._move_random_direction,
            "return_to_source": self._move_return_to_source,
            "bounce": self._move_bounce,
        }
    
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

    def _verify_moved(self, original_x: int, original_y: int) -> None:
        """Verify the mouse actually moved from its original position.

        Args:
            original_x: The x-coordinate before the move attempt.
            original_y: The y-coordinate before the move attempt.

        Raises:
            RuntimeError: If the cursor is still at (original_x, original_y),
                indicating Accessibility permissions may not be granted.
        """
        new_x, new_y = pyautogui.position()
        if new_x == original_x and new_y == original_y:
            raise RuntimeError(
                "Mouse did not move — Accessibility permissions may not be "
                "granted. Go to System Settings → Privacy & Security → "
                "Accessibility and add Eternal Green."
            )

    def _move_standard(self, pixels: int) -> None:
        """Move mouse by the configured pixels using moveRel.

        This is the original pre-pattern behavior: a simple relative move
        in a random diagonal direction by exactly ``pixels`` on each axis.
        No bounce logic, no return-to-source — just a quick nudge.

        Args:
            pixels: Number of pixels to move in each axis.
        """
        dx = random.choice([-pixels, pixels])
        dy = random.choice([-pixels, pixels])
        original_x, original_y = pyautogui.position()
        pyautogui.moveRel(dx, dy, duration=0)
        self._verify_moved(original_x, original_y)

    def _move_random_direction(self, pixels: int) -> None:
        """Move mouse in a random diagonal direction with bounce logic.

        Equivalent to the current ``move_mouse`` behavior: selects a random
        diagonal, applies bounce-target computation, moves the cursor, and
        verifies it actually moved.

        Args:
            pixels: Number of pixels to move in each axis.
        """
        original_x, original_y = pyautogui.position()
        dx = random.choice([-pixels, pixels])
        dy = random.choice([-pixels, pixels])
        screen_width, screen_height = pyautogui.size()

        target_x, target_y = self._compute_bounce_target(
            original_x, original_y, dx, dy, pixels, screen_width, screen_height
        )
        pyautogui.moveTo(target_x, target_y, duration=0)
        self._verify_moved(original_x, original_y)

    def _move_return_to_source(self, pixels: int) -> None:
        """Move cursor away visibly then smoothly glide back to origin.

        Uses a larger excursion (20x movement_pixels, capped at 100px) so the
        movement is clearly visible. Animates outward over 0.3s, pauses 0.3-0.5s,
        then glides back over 0.3s.

        Args:
            pixels: Base movement magnitude in pixels.
        """
        # Use a larger excursion so the motion is actually visible
        excursion = min(pixels * 20, 100)

        original_x, original_y = pyautogui.position()
        dx = random.choice([-excursion, excursion])
        dy = random.choice([-excursion, excursion])
        screen_width, screen_height = pyautogui.size()

        target_x, target_y = self._compute_bounce_target(
            original_x, original_y, dx, dy, excursion, screen_width, screen_height
        )

        # Animate outward (visible glide)
        pyautogui.moveTo(target_x, target_y, duration=0.3)

        # Pause so the excursion is perceptible
        time.sleep(random.uniform(0.3, 0.5))

        # Smoothly glide back to original position
        pyautogui.moveTo(original_x, original_y, duration=0.3)

    def _move_bounce(self, pixels: int, duration: float = 0) -> None:
        """Continuously glide the cursor like a DVD screensaver, bouncing off edges.

        When ``duration > 0``, runs a tight animation loop moving 1px per step
        at ~50fps for the given number of seconds. The cursor moves diagonally
        and reverses the offending axis component when it hits a screen edge.

        When ``duration == 0`` (single-step mode, used by tests), performs one
        discrete move of ``pixels`` in the current direction.

        Args:
            pixels: Movement magnitude per step (used as margin for edge detection).
            duration: How long to animate in seconds. 0 = single step.
        """
        if self._bounce_direction is None:
            self._bounce_direction = (
                random.choice([-1, 1]),
                random.choice([-1, 1]),
            )

        screen_width, screen_height = pyautogui.size()
        margin = pixels

        if duration <= 0:
            # Single-step mode (backward compat for tests)
            original_x, original_y = pyautogui.position()
            dx_sign, dy_sign = self._bounce_direction

            target_x = original_x + dx_sign * pixels
            target_y = original_y + dy_sign * pixels

            if target_x < margin or target_x > screen_width - margin:
                dx_sign = -dx_sign
                target_x = original_x + dx_sign * pixels
            if target_y < margin or target_y > screen_height - margin:
                dy_sign = -dy_sign
                target_y = original_y + dy_sign * pixels

            target_x = max(margin, min(target_x, screen_width - margin))
            target_y = max(margin, min(target_y, screen_height - margin))

            self._bounce_direction = (dx_sign, dy_sign)
            pyautogui.moveTo(target_x, target_y, duration=0)
            self._verify_moved(original_x, original_y)
            return

        # Continuous animation mode — smooth DVD-screensaver motion
        step_delay = 0.02  # ~50fps
        end_time = time.monotonic() + duration

        while time.monotonic() < end_time and not self._stop_event.is_set():
            x, y = pyautogui.position()
            dx_sign, dy_sign = self._bounce_direction

            new_x = x + dx_sign
            new_y = y + dy_sign

            # Bounce off edges
            if new_x < margin or new_x > screen_width - margin:
                dx_sign = -dx_sign
                new_x = x + dx_sign
            if new_y < margin or new_y > screen_height - margin:
                dy_sign = -dy_sign
                new_y = y + dy_sign

            # Clamp (safety)
            new_x = max(margin, min(new_x, screen_width - margin))
            new_y = max(margin, min(new_y, screen_height - margin))

            self._bounce_direction = (dx_sign, dy_sign)
            pyautogui.moveTo(new_x, new_y, duration=0)
            time.sleep(step_delay)

    def move_mouse(self, pixels: int) -> None:
        """Move mouse according to the configured movement pattern.

        Dispatches to the pattern-specific handler based on
        ``self.config.movement_pattern``.

        Args:
            pixels: Number of pixels to move in each axis.

        Raises:
            RuntimeError: If the mouse did not actually move (e.g. missing
                Accessibility permissions on macOS).
            pyautogui.FailSafeException: Propagated if triggered.
        """
        handler = self._pattern_dispatch[self.config.movement_pattern]
        handler(pixels)
    
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
            
            mode_str = "silent" if self.config.silent_mode else "with keystroke"
            pattern = self.config.movement_pattern

            # Build pattern-specific message
            if pattern == "standard":
                detail = f"moved {self.config.movement_pixels}px"
            elif pattern == "random_direction":
                detail = f"moved {self.config.movement_pixels}px (bounce-clamped)"
            elif pattern == "return_to_source":
                excursion = min(self.config.movement_pixels * 20, 100)
                detail = f"excursion {excursion}px and returned"
            else:
                detail = f"moved {self.config.movement_pixels}px"

            if next_interval is not None:
                message = f"[{pattern}] {detail} ({mode_str}), next in {next_interval}s"
            else:
                message = f"[{pattern}] {detail} ({mode_str})"
            
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
            start_msg = f"Starting idle prevention ({self.config.movement_pattern}, random interval: {self.config.interval_range_min}-{self.config.interval_range_max}s)"
        else:
            start_msg = f"Starting idle prevention ({self.config.movement_pattern}, interval: {self.config.interval_seconds}s)"
        
        print(f"▶ {start_msg}")
        if self.logger:
            self.logger.log_activity(start_msg)
        
        # Initialize bounce direction for "bounce" pattern
        if self.config.movement_pattern == "bounce":
            self._bounce_direction = (
                random.choice([-1, 1]),
                random.choice([-1, 1]),
            )
        
        try:
            if self.config.movement_pattern == "bounce":
                self._run_bounce_loop()
            else:
                self._run_standard_loop()
        finally:
            self._cleanup()

    def _run_standard_loop(self) -> None:
        """Standard move-then-wait loop for random_direction and return_to_source."""
        while self._running:
            next_interval = self._get_next_interval()
            self.simulate_activity(next_interval=next_interval)
            if self._stop_event.wait(timeout=next_interval):
                break

    def _run_bounce_loop(self) -> None:
        """Continuous bounce loop — the cursor glides for the full interval duration.

        Each cycle: glide continuously for next_interval seconds, then
        optionally press a key and log. The mouse never stops moving
        (DVD screensaver style).
        """
        while self._running:
            next_interval = self._get_next_interval()

            try:
                # Continuous glide for the entire interval
                self._move_bounce(self.config.movement_pixels, duration=next_interval)

                # Press key if not silent (registers activity)
                if not self.config.silent_mode:
                    self.press_key()

                mode_str = "silent" if self.config.silent_mode else "with keystroke"
                message = (
                    f"[bounce] continuous glide {next_interval}s "
                    f"({mode_str}), next cycle starting"
                )
                print(f"✓ {message}")
                if self.logger:
                    self.logger.log_activity(message)

                self._consecutive_failures = 0

            except pyautogui.FailSafeException:
                raise
            except Exception as e:
                self._consecutive_failures += 1
                error_msg = f"Error during bounce simulation: {e}"
                print(f"✗ {error_msg}")
                if self.logger:
                    self.logger.log_error(error_msg)
                _log.exception("Bounce simulation failed")
                # Wait a bit before retrying to avoid tight error loop
                if self._stop_event.wait(timeout=1):
                    break

            if self._stop_event.is_set():
                break
    
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
