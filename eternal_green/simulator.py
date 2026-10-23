"""Activity simulator for eternal-green."""

import ctypes
import os
import platform
import random
import signal
import subprocess
import threading
import time
from contextlib import contextmanager
from typing import Iterator, Optional

import pyautogui

from eternal_green import screen
from eternal_green.config import EternalGreenConfig
from eternal_green.logger import ActivityLogger

# Minimum distance (px) kept from every display edge, so the cursor never
# rests in a corner (macOS hot corners) or on an edge (auto-hiding Dock/menu bar).
SAFE_MARGIN = 10

# Seconds of slack when comparing idle time against the interval.
IDLE_TOLERANCE = 0.5

# A cursor further than this (px) from where the bounce glide left it means
# the user has taken over the mouse.
TAKEOVER_TOLERANCE = 3

# Consecutive failed cycles before giving up (e.g. Accessibility not granted).
MAX_CONSECUTIVE_FAILURES = 5


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


def _start_caffeinate() -> Optional[subprocess.Popen]:
    """Start macOS ``caffeinate`` to keep the display and system awake.

    ``-d`` prevents display sleep (and the screen lock that follows it),
    ``-i`` prevents idle system sleep, and ``-w`` ties the assertion to this
    process so it is released even if we crash.

    Returns:
        The running process, or ``None`` on non-macOS platforms or if
        ``caffeinate`` is unavailable.
    """
    if platform.system() != "Darwin":
        return None
    try:
        return subprocess.Popen(
            ["caffeinate", "-di", "-w", str(os.getpid())],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None


@contextmanager
def _failsafe_disabled() -> Iterator[None]:
    """Temporarily disable pyautogui's corner fail-safe.

    pyautogui raises ``FailSafeException`` before *any* action whenever the
    cursor rests in a screen corner, which would stop idle prevention just
    because the cursor was parked there. The simulator keeps the cursor out
    of corners itself and yields to the user instead, so the kill-switch is
    not needed. The previous setting is restored afterwards.
    """
    previous = pyautogui.FAILSAFE
    pyautogui.FAILSAFE = False
    try:
        yield
    finally:
        pyautogui.FAILSAFE = previous


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
        self._caffeinate: Optional[subprocess.Popen] = None
        self._consecutive_failures = 0
        self._bounce_direction: tuple[int, int] | None = None
        # User-activity tracking (see _idle_seconds)
        self._last_action_at = time.monotonic()
        self._last_input_at = self._last_action_at
        self._last_seen_pos: tuple[int, int] | None = None
        self._pattern_dispatch: dict[str, callable] = {
            "standard": self._move_standard,
            "return_to_source": self._move_return_to_source,
            "bounce": self._move_bounce,
        }

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _report(self, symbol: str, message: str, level: str = "info", exc_info: bool = False) -> None:
        """Print a message to the console and write it to the activity log."""
        print(f"{symbol} {message}")
        if self.logger:
            if level == "error":
                self.logger.log_error(message, exc_info=exc_info)
            elif level == "warning":
                self.logger.log_warning(message)
            else:
                self.logger.log_activity(message)

    def _record_failure(self, message: str) -> bool:
        """Report a failed cycle; stop the loop after too many in a row.

        Returns:
            True if the loop has been stopped.
        """
        self._consecutive_failures += 1
        self._report("✗", message, level="error", exc_info=True)
        if self._consecutive_failures < MAX_CONSECUTIVE_FAILURES:
            return False
        self._running = False
        self._report(
            "■",
            f"Stopping idle prevention after {self._consecutive_failures} "
            f"consecutive failures. Last error: {message}",
            level="error",
        )
        return True

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_bounce_target(
        x: int,
        y: int,
        dx: int,
        dy: int,
        bounds: screen.Bounds,
    ) -> tuple[int, int]:
        """Compute target position with bounce logic.

        If the naive target (x+dx, y+dy) would fall outside the safe area,
        the offending component is reversed (bounced), then clamped.

        Args:
            x: Current cursor x position.
            y: Current cursor y position.
            dx: Horizontal movement (positive = right, negative = left).
            dy: Vertical movement (positive = down, negative = up).
            bounds: Safe area ``(min_x, min_y, max_x, max_y)``, inclusive.

        Returns:
            Tuple of (target_x, target_y) guaranteed to be within the safe area.
        """
        min_x, min_y, max_x, max_y = bounds
        target_x = x + dx
        target_y = y + dy

        if target_x < min_x or target_x > max_x:
            target_x = x - dx  # reverse direction
        if target_y < min_y or target_y > max_y:
            target_y = y - dy  # reverse direction

        # Clamp (handles a cursor that started outside the safe area)
        target_x = max(min_x, min(target_x, max_x))
        target_y = max(min_y, min(target_y, max_y))

        return (target_x, target_y)

    def _safe_bounds(self, x: int, y: int, margin: int) -> screen.Bounds:
        """Return the safe area of the display the cursor is on.

        Args:
            x: Cursor x position.
            y: Cursor y position.
            margin: Desired distance from the display edges (at least
                ``SAFE_MARGIN``).

        Returns:
            ``(min_x, min_y, max_x, max_y)``, inclusive.
        """
        left, top, right, bottom = screen.display_bounds_at(x, y, pyautogui.size())
        margin = max(margin, SAFE_MARGIN)
        # Keep the safe area non-empty on very small displays
        margin = min(margin, (right - left - 1) // 2, (bottom - top - 1) // 2)
        return (left + margin, top + margin, right - 1 - margin, bottom - 1 - margin)

    @staticmethod
    def _clamp(x: int, y: int, bounds: screen.Bounds) -> tuple[int, int]:
        min_x, min_y, max_x, max_y = bounds
        return (max(min_x, min(x, max_x)), max(min_y, min(y, max_y)))

    def _note_if_cornered(self, x: int, y: int, bounds: screen.Bounds) -> None:
        """Report when the cursor starts in a screen corner and gets moved out."""
        min_x, min_y, max_x, max_y = bounds
        if (x < min_x or x > max_x) and (y < min_y or y > max_y):
            self._report("↗", "Cursor was in a screen corner — moved it to a safe spot.")

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

    # ------------------------------------------------------------------
    # Movement patterns
    # ------------------------------------------------------------------

    def _move_standard(self, pixels: int) -> None:
        """Nudge the mouse by ``pixels`` on each axis in a random diagonal.

        The target is computed on the display the cursor is on and kept
        inside its safe area, bouncing off edges.

        Args:
            pixels: Number of pixels to move in each axis.
        """
        original_x, original_y = pyautogui.position()
        dx = random.choice([-pixels, pixels])
        dy = random.choice([-pixels, pixels])
        bounds = self._safe_bounds(original_x, original_y, pixels)
        self._note_if_cornered(original_x, original_y, bounds)

        target_x, target_y = self._compute_bounce_target(
            original_x, original_y, dx, dy, bounds
        )
        pyautogui.moveTo(target_x, target_y, duration=0, _pause=False)
        self._verify_moved(original_x, original_y)

    def _move_return_to_source(self, pixels: int) -> None:
        """Move cursor away visibly then smoothly glide back to origin.

        Uses a larger excursion (20x movement_pixels, capped at 100px) so the
        movement is clearly visible. Animates outward over 0.3s, pauses 0.3-0.5s,
        then glides back over 0.3s. A cursor that started in a corner returns
        to the nearest safe spot instead.

        Args:
            pixels: Base movement magnitude in pixels.
        """
        # Use a larger excursion so the motion is actually visible
        excursion = min(pixels * 20, 100)

        original_x, original_y = pyautogui.position()
        home_bounds = self._safe_bounds(original_x, original_y, 0)
        self._note_if_cornered(original_x, original_y, home_bounds)
        home_x, home_y = self._clamp(original_x, original_y, home_bounds)

        dx = random.choice([-excursion, excursion])
        dy = random.choice([-excursion, excursion])
        target_x, target_y = self._compute_bounce_target(
            home_x, home_y, dx, dy, self._safe_bounds(home_x, home_y, excursion)
        )

        # Animate outward (visible glide)
        pyautogui.moveTo(target_x, target_y, duration=0.3, _pause=False)

        # Pause so the excursion is perceptible
        time.sleep(random.uniform(0.3, 0.5))

        # Smoothly glide back to the starting position
        pyautogui.moveTo(home_x, home_y, duration=0.3, _pause=False)

    def _move_bounce(self, pixels: int, duration: float = 0) -> bool:
        """Continuously glide the cursor like a DVD screensaver, bouncing off edges.

        When ``duration > 0``, runs a tight animation loop moving 1px per step
        at ~50fps for the given number of seconds, within the display the
        cursor started on. The glide ends early as soon as the user moves the
        mouse or presses a key.

        When ``duration == 0`` (single-step mode, used by tests), performs one
        discrete move of ``pixels`` in the current direction.

        Args:
            pixels: Movement magnitude per step (used as margin for edge detection).
            duration: How long to animate in seconds. 0 = single step.

        Returns:
            False if the glide was interrupted by the user, True otherwise.
        """
        if self._bounce_direction is None:
            self._bounce_direction = (
                random.choice([-1, 1]),
                random.choice([-1, 1]),
            )

        if duration <= 0:
            # Single-step mode (backward compat for tests)
            original_x, original_y = pyautogui.position()
            bounds = self._safe_bounds(original_x, original_y, pixels)
            target_x, target_y = self._next_bounce_position(
                original_x, original_y, pixels, bounds
            )
            pyautogui.moveTo(target_x, target_y, duration=0, _pause=False)
            self._verify_moved(original_x, original_y)
            return True

        # Continuous animation mode — smooth DVD-screensaver motion
        step_delay = 0.02  # ~50fps
        glide_start = time.monotonic()
        end_time = glide_start + duration
        x, y = pyautogui.position()
        bounds = self._safe_bounds(x, y, pixels)
        expected: tuple[int, int] | None = None

        while time.monotonic() < end_time and not self._stop_event.is_set():
            x, y = pyautogui.position()
            if expected is not None and (
                abs(x - expected[0]) > TAKEOVER_TOLERANCE
                or abs(y - expected[1]) > TAKEOVER_TOLERANCE
            ):
                return False  # user moved the mouse
            key_idle = screen.seconds_since_key_input()
            if key_idle is not None and key_idle < time.monotonic() - glide_start:
                return False  # user pressed a key

            expected = self._next_bounce_position(x, y, 1, bounds)
            pyautogui.moveTo(expected[0], expected[1], duration=0, _pause=False)
            time.sleep(step_delay)
        return True

    def _next_bounce_position(
        self, x: int, y: int, step: int, bounds: screen.Bounds
    ) -> tuple[int, int]:
        """Advance one bounce step from (x, y), reversing on edge collisions."""
        min_x, min_y, max_x, max_y = bounds
        dx_sign, dy_sign = self._bounce_direction

        new_x = x + dx_sign * step
        new_y = y + dy_sign * step
        if new_x < min_x or new_x > max_x:
            dx_sign = -dx_sign
            new_x = x + dx_sign * step
        if new_y < min_y or new_y > max_y:
            dy_sign = -dy_sign
            new_y = y + dy_sign * step

        self._bounce_direction = (dx_sign, dy_sign)
        return self._clamp(new_x, new_y, bounds)

    def move_mouse(self, pixels: int) -> None:
        """Move mouse according to the configured movement pattern.

        Dispatches to the pattern-specific handler based on
        ``self.config.movement_pattern``.

        Args:
            pixels: Number of pixels to move in each axis.

        Raises:
            RuntimeError: If the mouse did not actually move (e.g. missing
                Accessibility permissions on macOS).
        """
        handler = self._pattern_dispatch[self.config.movement_pattern]
        with _failsafe_disabled():
            handler(pixels)

    def press_key(self) -> None:
        """Press a neutral key (shift) that doesn't affect applications."""
        with _failsafe_disabled():
            pyautogui.press('shift', _pause=False)

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
            if pattern == "return_to_source":
                excursion = min(self.config.movement_pixels * 20, 100)
                detail = f"excursion {excursion}px and returned"
            else:
                detail = f"moved {self.config.movement_pixels}px"

            if next_interval is not None:
                message = f"[{pattern}] {detail} ({mode_str}), next in {next_interval}s"
            else:
                message = f"[{pattern}] {detail} ({mode_str})"

            self._report("✓", message)
            self._consecutive_failures = 0
            return True

        except Exception as e:
            self._record_failure(f"Error during activity simulation: {e}")
            return False

    # ------------------------------------------------------------------
    # User activity
    # ------------------------------------------------------------------

    def _mark_action(self) -> None:
        """Remember when (and where) the simulator last acted."""
        self._last_action_at = time.monotonic()
        try:
            self._last_seen_pos = tuple(pyautogui.position())
        except Exception:
            self._last_seen_pos = None

    def _idle_seconds(self) -> float:
        """Return how long the user (or the simulator) has been inactive.

        On macOS this is the system HID idle time. Elsewhere it is estimated
        from cursor movement the simulator did not cause.
        """
        idle = screen.seconds_since_input()
        if idle is not None:
            return idle

        now = time.monotonic()
        try:
            pos = tuple(pyautogui.position())
        except Exception:
            return now - self._last_action_at
        if self._last_seen_pos is not None and pos != self._last_seen_pos:
            self._last_input_at = now
        self._last_seen_pos = pos
        return now - max(self._last_input_at, self._last_action_at)

    def _wait_for_idle(self, threshold: float) -> bool:
        """Block until there has been no input for ``threshold`` seconds.

        The simulator's own input counts too, so in steady state this simply
        waits one interval after each action. If the user is active the wait
        is extended, so the simulator never acts while they work.

        Returns:
            False if the loop was stopped while waiting.
        """
        reported = False
        while self._running:
            idle = self._idle_seconds()
            if idle >= threshold - IDLE_TOLERANCE:
                return True
            if not reported and idle + 1 < time.monotonic() - self._last_action_at:
                self._report(
                    "⏸", f"You're active — waiting for {threshold}s of inactivity."
                )
                reported = True
            if self._stop_event.wait(timeout=threshold - idle):
                return False
        return False

    def _get_next_interval(self) -> int:
        """Get the next interval duration based on configuration.

        Returns:
            Interval in seconds (random if enabled, fixed otherwise)
        """
        if self.config.random_interval:
            return random.randint(self.config.interval_range_min, self.config.interval_range_max)
        return self.config.interval_seconds

    # ------------------------------------------------------------------
    # Loop
    # ------------------------------------------------------------------

    def start_loop(self) -> None:
        """Start the idle prevention loop.

        Runs activity simulation whenever the computer has been idle for the
        configured interval, until stop() is called or SIGINT is received.
        """
        self._running = True
        self._stop_event.clear()
        self._consecutive_failures = 0
        self._last_action_at = self._last_input_at = time.monotonic()
        self._last_seen_pos = None

        try:
            # Set up signal handler for graceful shutdown (only works in main thread)
            if threading.current_thread() is threading.main_thread():
                self._original_sigint_handler = signal.getsignal(signal.SIGINT)
                signal.signal(signal.SIGINT, self._handle_sigint)

            # Warn early if Accessibility permissions are missing
            if not _check_accessibility():
                self._report(
                    "⚠",
                    "Accessibility permissions not granted — mouse/keyboard "
                    "simulation will not work. Go to System Settings → Privacy "
                    "& Security → Accessibility and add Eternal Green.",
                    level="warning",
                )

            if self.config.random_interval:
                timing = f"random interval: {self.config.interval_range_min}-{self.config.interval_range_max}s"
            else:
                timing = f"interval: {self.config.interval_seconds}s"
            self._report(
                "▶",
                f"Starting idle prevention ({self.config.movement_pattern}, {timing}) "
                f"— acts only while you're idle",
            )

            # Initialize bounce direction for "bounce" pattern
            if self.config.movement_pattern == "bounce":
                self._bounce_direction = (
                    random.choice([-1, 1]),
                    random.choice([-1, 1]),
                )

            self._caffeinate = _start_caffeinate()

            with _failsafe_disabled():
                if self.config.movement_pattern == "bounce":
                    self._run_bounce_loop()
                else:
                    self._run_standard_loop()
        finally:
            self._running = False
            self._cleanup()

    def _run_standard_loop(self) -> None:
        """Act once per interval of inactivity (standard and return_to_source)."""
        interval = self._get_next_interval()
        while self._running:
            if not self._wait_for_idle(interval):
                break
            next_interval = self._get_next_interval()
            self.simulate_activity(next_interval=next_interval)
            self._mark_action()
            interval = next_interval

    def _run_bounce_loop(self) -> None:
        """Continuous bounce loop — the cursor glides while you're away.

        Gliding starts after an interval of inactivity and continues cycle
        after cycle (optionally pressing a key between cycles). As soon as the
        user touches the mouse or keyboard the glide stops, and it resumes only
        after another interval of inactivity.
        """
        pixels = self.config.movement_pixels
        wait_for_idle = True
        while self._running:
            if wait_for_idle and not self._wait_for_idle(self._get_next_interval()):
                break

            next_interval = self._get_next_interval()
            try:
                completed = self._move_bounce(pixels, duration=next_interval)
                if self._stop_event.is_set():
                    break
                if completed and not self.config.silent_mode:
                    self.press_key()
                self._mark_action()
                self._consecutive_failures = 0
            except Exception as e:
                self._mark_action()
                if self._record_failure(f"Error during bounce simulation: {e}"):
                    break
                # Wait a bit before retrying to avoid tight error loop
                if self._stop_event.wait(timeout=1):
                    break
                continue

            if completed:
                mode_str = "silent" if self.config.silent_mode else "with keystroke"
                self._report(
                    "✓",
                    f"[bounce] continuous glide {next_interval}s ({mode_str}), "
                    f"next cycle starting",
                )
                wait_for_idle = False
            else:
                self._report("⏸", "You took over — bounce paused until you're idle again.")
                wait_for_idle = True

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
        """Stop caffeinate and restore the original signal handler."""
        if self._caffeinate is not None:
            self._caffeinate.terminate()
            self._caffeinate.wait()
            self._caffeinate = None
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
