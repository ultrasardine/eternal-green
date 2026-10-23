"""System tray interface for eternal-green.

Cross-platform tray icon using pystray with start/stop controls,
silent mode toggle, settings window, and status indicator.
"""

import subprocess
import sys
import threading
from typing import Callable, Optional

from PIL import Image, ImageDraw
import pystray

from eternal_green.config import ConfigManager, EternalGreenConfig
from eternal_green.logger import ActivityLogger
from eternal_green.simulator import ActivitySimulator


def _on_ui_thread(fn: Callable[[], None]) -> None:
    """Run ``fn`` on the UI thread (AppKit must only be touched from there)."""
    if sys.platform == "darwin":
        try:
            from PyObjCTools import AppHelper
        except ImportError:
            pass
        else:
            AppHelper.callAfter(fn)
            return
    fn()


class TrayIcon:
    """System tray icon with idle prevention controls.

    The settings window is launched as a **subprocess** so that tkinter
    gets its own ``NSApplication`` and does not conflict with pystray's.
    """

    ICON_SIZE = 64
    COLOR_STOPPED = "#808080"
    COLOR_RUNNING = "#00C853"

    def __init__(
        self,
        config_manager: ConfigManager,
        simulator: Optional[ActivitySimulator] = None,
        logger: Optional[ActivityLogger] = None,
    ):
        self.config_manager = config_manager
        self.config = config_manager.load()
        self.logger = logger or ActivityLogger(self.config.log_file_path)
        self._log_load_warnings()
        self.simulator = simulator or ActivitySimulator(self.config, self.logger)
        self._sim_thread: Optional[threading.Thread] = None
        self._icon: Optional[pystray.Icon] = None
        # Serialises start/stop/apply, which run on the UI and settings threads
        self._lock = threading.RLock()
        self._settings_process: Optional[subprocess.Popen] = None

    def _log_load_warnings(self) -> None:
        for warning in self.config_manager.load_warnings:
            self.logger.log_warning(f"Config: {warning}")

    # ------------------------------------------------------------------
    # Icon helpers
    # ------------------------------------------------------------------

    def _create_icon_image(self, color: str) -> Image.Image:
        """Create a filled circle icon with the given color."""
        img = Image.new("RGBA", (self.ICON_SIZE, self.ICON_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        margin = 4
        draw.ellipse(
            [margin, margin, self.ICON_SIZE - margin, self.ICON_SIZE - margin],
            fill=color,
        )
        return img

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> pystray.Menu:
        """Build the tray context menu."""
        running = self.simulator.is_running

        return pystray.Menu(
            pystray.MenuItem(
                "Status: Running" if running else "Status: Stopped",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Stop" if running else "Start",
                self._toggle,
            ),
            pystray.MenuItem(
                lambda item: f"Silent Mode: {'On' if self.config.silent_mode else 'Off'}",
                self._toggle_silent,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings…", self._open_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    def _update_icon(self) -> None:
        """Update icon color and menu based on current state."""
        if self._icon is None:
            return
        color = self.COLOR_RUNNING if self.simulator.is_running else self.COLOR_STOPPED
        self._icon.icon = self._create_icon_image(color)
        self._icon.menu = self._build_menu()

    # ------------------------------------------------------------------
    # Simulator lifecycle
    # ------------------------------------------------------------------

    def _run_simulator(self, simulator: ActivitySimulator) -> None:
        """Thread target: run the loop and refresh the tray when it ends.

        The loop can end on its own (repeated failures, unexpected errors), so
        the icon must not keep claiming it is running.
        """
        try:
            simulator.start_loop()
        except Exception as e:
            self.logger.log_error(f"Idle prevention failed: {e}", exc_info=True)
        finally:
            # The loop is over however it ended (see the flag set in _start)
            simulator._running = False
            _on_ui_thread(self._update_icon)

    def _start(self) -> None:
        """Start a fresh simulator with the latest configuration."""
        self.simulator = ActivitySimulator(self.config, self.logger)
        # Mark as running before the thread starts so the menu is correct
        # immediately; start_loop() sets the same flag itself.
        self.simulator._running = True
        self._sim_thread = threading.Thread(
            target=self._run_simulator, args=(self.simulator,), daemon=True
        )
        self._sim_thread.start()

    def _stop(self) -> None:
        """Stop the simulator and wait for its thread."""
        if self.simulator.is_running:
            self.simulator.stop()
        if self._sim_thread:
            self._sim_thread.join(timeout=5)
            self._sim_thread = None

    def _replace_logger(self, log_file_path: str) -> None:
        if self.logger.log_file_path != log_file_path:
            self.logger.close()
            self.logger = ActivityLogger(log_file_path)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _toggle(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """Start or stop idle prevention."""
        with self._lock:
            if self.simulator.is_running:
                self._stop()
            else:
                # Reload config in case it changed
                self.config = self.config_manager.load()
                self._replace_logger(self.config.log_file_path)
                self._log_load_warnings()
                self._start()
        self._update_icon()

    def _toggle_silent(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """Toggle silent mode."""
        with self._lock:
            self.config = self.config_manager.update(
                silent_mode=not self.config_manager.load().silent_mode
            )
            # Apply to running simulator
            self.simulator.config = self.config
        self._update_icon()

    def _open_settings(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """Launch the settings window as a separate subprocess.

        tkinter needs its own ``NSApplication`` on macOS, so we run it
        in a child process.  When the subprocess exits we reload the
        config in case the user saved changes.  Only one window is open
        at a time.
        """
        if self._settings_process is not None and self._settings_process.poll() is None:
            return

        if getattr(sys, "frozen", False):
            # PyInstaller bundle: re-invoke ourselves with --settings
            cmd = [sys.executable, "--settings"]
        else:
            cmd = [sys.executable, "-m", "eternal_green.settings_window"]
        process = self._settings_process = subprocess.Popen(cmd)

        def _wait() -> None:
            process.wait()
            # Reload config — the user may have saved changes
            new_config = self.config_manager.load()
            if new_config != self.config:
                self._apply_config(new_config)
                _on_ui_thread(self._update_icon)

        threading.Thread(target=_wait, daemon=True).start()

    def _apply_config(self, new_config: EternalGreenConfig) -> None:
        """Apply a new configuration, restarting the simulator if needed."""
        with self._lock:
            self.config = new_config
            self._log_load_warnings()
            was_running = self.simulator.is_running
            self._stop()
            self._replace_logger(new_config.log_file_path)
            if was_running:
                self._start()
            else:
                self.simulator = ActivitySimulator(new_config, self.logger)

    def _quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """Stop simulator and exit tray."""
        with self._lock:
            self._stop()
        if self._settings_process is not None and self._settings_process.poll() is None:
            self._settings_process.terminate()
        self.logger.close()
        icon.stop()

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the system tray icon (blocking)."""
        self._icon = pystray.Icon(
            name="eternal-green",
            icon=self._create_icon_image(
                self.COLOR_RUNNING
                if self.simulator.is_running
                else self.COLOR_STOPPED
            ),
            title="Eternal Green",
            menu=self._build_menu(),
        )
        self._icon.run()


def main() -> None:
    """Entry point for the tray application."""
    if "--settings" in sys.argv:
        from eternal_green.settings_window import _run_standalone
        _run_standalone()
        return

    tray = TrayIcon(ConfigManager())
    tray.run()


if __name__ == "__main__":
    main()
