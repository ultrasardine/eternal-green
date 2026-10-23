"""Display geometry and input-idle helpers for eternal-green.

On macOS these use Quartz (shipped with pyautogui's pyobjc dependencies) so
that multi-display setups and real user input are handled correctly. On other
platforms they fall back to conservative behaviour.
"""

import platform
from typing import Optional

# Half-size of the box used when the cursor is on a display we cannot query
# (non-macOS secondary monitors). Movements stay inside this box, so the
# cursor is nudged in place instead of being dragged onto the primary display.
FALLBACK_HALF_SIZE = 100

Bounds = tuple[int, int, int, int]


def _quartz():
    """Return the Quartz module on macOS, or ``None`` if unavailable."""
    if platform.system() != "Darwin":
        return None
    try:
        import Quartz
    except ImportError:
        return None
    return Quartz


def _quartz_display_bounds(x: int, y: int) -> Optional[Bounds]:
    """Return the bounds of the macOS display containing (x, y), if any."""
    quartz = _quartz()
    if quartz is None:
        return None
    try:
        err, displays, count = quartz.CGGetDisplaysWithPoint((x, y), 1, None, None)
        if err or not count:
            return None
        rect = quartz.CGDisplayBounds(displays[0])
    except Exception:
        return None
    left, top = int(rect.origin.x), int(rect.origin.y)
    return (left, top, left + int(rect.size.width), top + int(rect.size.height))


def display_bounds_at(x: int, y: int, primary_size: tuple[int, int]) -> Bounds:
    """Return the bounds of the display containing the point (x, y).

    Coordinates are global, with the origin at the top-left of the main
    display (the same space pyautogui uses).

    Args:
        x: Cursor x position.
        y: Cursor y position.
        primary_size: ``pyautogui.size()`` of the primary display, used when
            the platform cannot be queried directly.

    Returns:
        ``(left, top, right, bottom)`` with ``right``/``bottom`` exclusive.
    """
    bounds = _quartz_display_bounds(x, y)
    if bounds is not None:
        return bounds

    width, height = primary_size
    if 0 <= x < width and 0 <= y < height:
        return (0, 0, width, height)
    return (
        x - FALLBACK_HALF_SIZE,
        y - FALLBACK_HALF_SIZE,
        x + FALLBACK_HALF_SIZE + 1,
        y + FALLBACK_HALF_SIZE + 1,
    )


def _seconds_since(event_type_name: str) -> Optional[float]:
    quartz = _quartz()
    if quartz is None:
        return None
    try:
        return float(
            quartz.CGEventSourceSecondsSinceLastEventType(
                quartz.kCGEventSourceStateHIDSystemState,
                getattr(quartz, event_type_name),
            )
        )
    except Exception:
        return None


def seconds_since_input() -> Optional[float]:
    """Seconds since the last mouse/keyboard input, or ``None`` if unknown."""
    return _seconds_since("kCGAnyInputEventType")


def seconds_since_key_input() -> Optional[float]:
    """Seconds since the last key press, or ``None`` if unknown."""
    return _seconds_since("kCGEventKeyDown")
