"""System tray interface for eternal-green.

Cross-platform tray icon using pystray with start/stop controls,
silent mode toggle, settings window, and status indicator.
"""

import threading
from typing import Optional

from PIL import Image, ImageDraw
import pystray

from eternal_green.config import ConfigManager, EternalGreenConfig
from eternal_green.logger import ActivityLogger
from eternal_green.simulator import ActivitySimulator


class TrayIcon:
    """System tray icon with idle prevention controls.

    The ``run()`` method enters a loop that alternates between the
    pystray event loop and (optionally) a tkinter settings window.
    When the user clicks *Settings…*, pystray is stopped so that
    tkinter can take over the main thread — a macOS requirement.
    After the settings window closes, pystray is restarted.
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

        # Flags checked after pystray's run loop exits
        self._wants_settings = False
        self._app_running = True

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
        """Request the settings window.

        Sets a flag and stops pystray so that ``run()`` can open the
        tkinter settings window on the main thread.
        """
        self._wants_settings = True
        icon.stop()

    def _show_settings_window(self) -> None:
        """Open the tkinter settings window on the main thread.

        Called by ``run()`` after pystray has released the main thread.
        """
        from eternal_green.settings_window import SettingsWindow

        old_config = self.config

        window = SettingsWindow(self.config_manager)
        window.open()  # blocks until the window is closed

        # Reload config — the user may have saved changes
        new_config = self.config_manager.load()
        if new_config != old_config:
            self._apply_config(new_config)

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
        self._app_running = False
        icon.stop()

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the system tray icon (blocking).

        Runs in a loop: pystray handles the menu bar icon until the
        user clicks *Settings…* (which stops pystray), then tkinter
        takes over the main thread for the settings window, and
        finally pystray is restarted.  The loop exits when the user
        clicks *Quit*.
        """
        while self._app_running:
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

            # pystray stopped — check why
            if self._wants_settings:
                self._wants_settings = False
                self._show_settings_window()
                # Loop back to restart pystray
            # else: _quit was called, _app_running is False → exit loop


def main() -> None:
    """Entry point for the tray application."""
    config_manager = ConfigManager()
    config = config_manager.load()
    logger = ActivityLogger(config.log_file_path)
    simulator = ActivitySimulator(config, logger)
    tray = TrayIcon(config_manager, simulator, logger)
    tray.run()


if __name__ == "__main__":
    main()
