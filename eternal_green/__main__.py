"""Entry point for running eternal-green as a module.

Allows running the application via: python -m eternal_green
"""

from eternal_green.config import ConfigManager
from eternal_green.logger import ActivityLogger
from eternal_green.simulator import ActivitySimulator
from eternal_green.cli import CLIInterface


def main() -> None:
    """Main entry point that wires up all components and starts the CLI."""
    # Initialize configuration manager
    config_manager = ConfigManager()
    
    # Load configuration
    config = config_manager.load()
    
    # Initialize logger with configured path
    logger = ActivityLogger(config.log_file_path)
    
    # Initialize activity simulator
    simulator = ActivitySimulator(config, logger)
    
    # Initialize and run CLI
    cli = CLIInterface(config_manager, simulator, logger)
    cli.run()


if __name__ == "__main__":
    main()
