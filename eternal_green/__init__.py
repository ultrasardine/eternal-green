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

__version__ = "0.1.0"

from eternal_green.config import EternalGreenConfig, ConfigManager
from eternal_green.logger import ActivityLogger, setup_logger
from eternal_green.simulator import ActivitySimulator
from eternal_green.cli import CLIInterface, main

__all__ = [
    "EternalGreenConfig",
    "ConfigManager",
    "ActivityLogger",
    "setup_logger",
    "ActivitySimulator",
    "CLIInterface",
    "main",
]
