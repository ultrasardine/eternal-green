"""Eternal-green: Anti-idle application to prevent computer inactivity.

This package provides anti-idle functionality to prevent computer inactivity
by simulating minimal user input (mouse movements and optional keystrokes).

Example usage as a library:
    from eternal_green import ActivitySimulator, EternalGreenConfig, ActivityLogger
    
    config = EternalGreenConfig(interval_seconds=60, silent_mode=True)
    logger = ActivityLogger("~/my_app.log")
    simulator = ActivitySimulator(config, logger)
    
    # Simulate activity once
    simulator.simulate_activity()
    
    # Or start the loop
    simulator.start_loop()
"""

__version__ = "0.2.0"

from eternal_green.config import EternalGreenConfig, ConfigManager
from eternal_green.logger import ActivityLogger, setup_logger
from eternal_green.simulator import ActivitySimulator
from eternal_green.cli import CLIInterface, main


def __getattr__(name: str):
    # Imported lazily: the tray pulls in pystray/PIL (and AppKit on macOS),
    # which the CLI and library users should not have to load.
    if name == "TrayIcon":
        from eternal_green.tray import TrayIcon
        return TrayIcon
    if name == "SettingsWindow":
        from eternal_green.settings_window import SettingsWindow
        return SettingsWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "EternalGreenConfig",
    "ConfigManager",
    "ActivityLogger",
    "setup_logger",
    "ActivitySimulator",
    "CLIInterface",
    "TrayIcon",
    "SettingsWindow",
    "main",
]
