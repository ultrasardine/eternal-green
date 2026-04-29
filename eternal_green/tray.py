"""System tray interface for eternal-green.

Cross-platform tray icon using pystray with start/stop controls,
silent mode toggle, settings window, and status indicator.
"""

import subprocess
import sys
import threading
from typing import Optional

from PIL import Image, ImageDraw
import pystray

from eternal_green.config import ConfigManager, EternalGreenConfig
from eternal_green.logger import ActivityLogger
from eternal_green.simulator import ActivitySimulator


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
        self.simulator = simulator or ActivitySimulator(self.config, self.logger)
        self._sim_thread: Optional[threading.Thread] = None
        self._icon: Optional[pystray.Icon] = None

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
    # Actions
    # ------------------------------------------------------------------

    def _toggle(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """Start or stop idle prevention."""
        if self.simulator.is_running:
            self.simulator.stop()
            if self._sim_thread:
                self._sim_thread.join(timeout=5)
                self._sim_thread = None
        else:
            # Reload config in case it changed
            self.config = self.config_manager.load()
            self.simulator = ActivitySimulator(self.config, self.logger)
            self._sim_thread = threading.Thread(
                target=self.simulator.start_loop, daemon=True
            )
            self._sim_thread.start()
        self._update_icon()

    def _toggle_silent(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """Toggle silent mode."""
        self.config = self.config_manager.update(
            silent_mode=not self.config.silent_mode
        )
        # Apply to running simulator
        self.simulator.config = self.config
        self._update_icon()

    def _open_settings(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """Launch the settings window as a separate subprocess.

        tkinter needs its own ``NSApplication`` on macOS, so we run it
        in a child process.  When the subprocess exits we reload the
        config in case the user saved changes.
        """
        def _run() -> None:
            if getattr(sys, "frozen", False):
                # PyInstaller bundle: re-invoke ourselves with --settings
                subprocess.run([sys.executable, "--settings"])
            else:
                subprocess.run(
                    [sys.executable, "-m", "eternal_green.settings_window"],
                )
            # Reload config — the user may have saved changes
            new_config = self.config_manager.load()
            if new_config != self.config:
                self._apply_config(new_config)

        threading.Thread(target=_run, daemon=True).start()

    def _apply_config(self, new_config: EternalGreenConfig) -> None:
        """Apply a new configuration, restarting the simulator if needed."""
        self.config = new_config

        if self.simulator.is_running:
            self.simulator.stop()
            if self._sim_thread:
                self._sim_thread.join(timeout=5)

            self.logger = ActivityLogger(new_config.log_file_path)
            self.simulator = ActivitySimulator(new_config, self.logger)
            self._sim_thread = threading.Thread(
                target=self.simulator.start_loop, daemon=True
            )
            self._sim_thread.start()
        else:
            self.logger = ActivityLogger(new_config.log_file_path)
            self.simulator = ActivitySimulator(new_config, self.logger)

    def _quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """Stop simulator and exit tray."""
        if self.simulator.is_running:
            self.simulator.stop()
            if self._sim_thread:
                self._sim_thread.join(timeout=5)
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

    config_manager = ConfigManager()
    config = config_manager.load()
    logger = ActivityLogger(config.log_file_path)
    simulator = ActivitySimulator(config, logger)
    tray = TrayIcon(config_manager, simulator, logger)
    tray.run()


if __name__ == "__main__":
    main()
