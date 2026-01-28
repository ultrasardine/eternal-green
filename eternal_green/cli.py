"""Interactive CLI interface for eternal-green."""

from typing import Optional

from eternal_green.config import ConfigManager, EternalGreenConfig
from eternal_green.simulator import ActivitySimulator
from eternal_green.logger import ActivityLogger


class CLIInterface:
    """Interactive command-line interface for eternal-green."""
    
    def __init__(
        self,
        config_manager: ConfigManager,
        simulator: Optional[ActivitySimulator] = None,
        logger: Optional[ActivityLogger] = None
    ):
        """Initialize CLI with dependencies.
        
        Args:
            config_manager: Configuration manager instance
            simulator: Optional activity simulator instance
            logger: Optional logger instance
        """
        self.config_manager = config_manager
        self.simulator = simulator
        self.logger = logger
        self._config: Optional[EternalGreenConfig] = None
    
    @property
    def config(self) -> EternalGreenConfig:
        """Get current configuration, loading if needed."""
        if self._config is None:
            self._config = self.config_manager.load()
        return self._config
    
    def display_menu(self) -> None:
        """Display the main menu options."""
        print("\n=== Eternal Green ===")
        print("1. View current configuration")
        print("2. Edit interval (seconds)")
        print("3. Edit movement (pixels)")
        print("4. Toggle silent mode")
        print("5. Edit log file path")
        print("6. Toggle random interval")
        print("7. Edit random interval range")
        print("8. Start idle prevention")
        print("9. Exit")
        print()
    
    def display_config(self) -> str:
        """Display current configuration values.
        
        Returns:
            String representation of the configuration display
        """
        config = self.config
        output = []
        output.append("\n--- Current Configuration ---")
        output.append(f"interval_seconds: {config.interval_seconds}")
        output.append(f"movement_pixels: {config.movement_pixels}")
        output.append(f"silent_mode: {config.silent_mode}")
        output.append(f"log_file_path: {config.log_file_path}")
        output.append(f"random_interval: {config.random_interval}")
        if config.random_interval:
            output.append(f"interval_range: {config.interval_range_min}-{config.interval_range_max}s")
        output.append("-----------------------------")
        
        result = "\n".join(output)
        print(result)
        return result

    def edit_config(self, param: str) -> bool:
        """Prompt user to edit a configuration parameter.
        
        Args:
            param: Parameter name to edit
            
        Returns:
            True if edit was successful, False otherwise
        """
        config = self.config
        current_value = getattr(config, param)
        
        print(f"\nCurrent {param}: {current_value}")
        
        try:
            if param in ("silent_mode", "random_interval"):
                new_value = not current_value
                print(f"Toggling {param} to: {new_value}")
            else:
                user_input = input(f"Enter new value for {param}: ").strip()
                
                if not user_input:
                    print("No value entered. Keeping current value.")
                    return False
                
                if param in ("interval_seconds", "movement_pixels", "interval_range_min", "interval_range_max"):
                    new_value = int(user_input)
                else:
                    new_value = user_input
            
            old_value = current_value
            self._config = self.config_manager.update(**{param: new_value})
            
            if self.logger:
                self.logger.log_config_change(param, old_value, new_value)
            
            print(f"Updated {param}: {old_value} -> {new_value}")
            return True
            
        except ValueError as e:
            if "Invalid configuration" in str(e):
                print(f"Error: {e}")
            else:
                print("Invalid input. Please enter a valid value.")
            return False
        except Exception as e:
            print(f"Error updating configuration: {e}")
            return False
    
    def edit_interval_range(self) -> bool:
        """Prompt user to edit both min and max interval range values.
        
        Returns:
            True if edit was successful, False otherwise
        """
        config = self.config
        print(f"\nCurrent interval range: {config.interval_range_min}-{config.interval_range_max}s")
        
        try:
            min_input = input(f"Enter minimum interval (seconds, 10-3600): ").strip()
            if not min_input:
                print("No value entered. Keeping current values.")
                return False
            
            max_input = input(f"Enter maximum interval (seconds, 10-3600): ").strip()
            if not max_input:
                print("No value entered. Keeping current values.")
                return False
            
            new_min = int(min_input)
            new_max = int(max_input)
            
            old_min = config.interval_range_min
            old_max = config.interval_range_max
            
            self._config = self.config_manager.update(
                interval_range_min=new_min,
                interval_range_max=new_max
            )
            
            if self.logger:
                self.logger.log_config_change("interval_range", f"{old_min}-{old_max}", f"{new_min}-{new_max}")
            
            print(f"Updated interval range: {old_min}-{old_max}s -> {new_min}-{new_max}s")
            return True
            
        except ValueError as e:
            if "Invalid configuration" in str(e):
                print(f"Error: {e}")
            else:
                print("Invalid input. Please enter valid integer values.")
            return False
        except Exception as e:
            print(f"Error updating configuration: {e}")
            return False
    
    def handle_input(self, choice: str) -> bool:
        """Handle user menu selection.
        
        Args:
            choice: User's menu choice
            
        Returns:
            False to exit, True to continue
        """
        choice = choice.strip()
        
        if choice == "1":
            self.display_config()
        elif choice == "2":
            self.edit_config("interval_seconds")
        elif choice == "3":
            self.edit_config("movement_pixels")
        elif choice == "4":
            self.edit_config("silent_mode")
        elif choice == "5":
            self.edit_config("log_file_path")
        elif choice == "6":
            self.edit_config("random_interval")
        elif choice == "7":
            self.edit_interval_range()
        elif choice == "8":
            self._start_simulator()
        elif choice == "9":
            print("Exiting...")
            return False
        else:
            print("Invalid option. Please enter a number 1-9.")
        
        return True
    
    def _start_simulator(self) -> None:
        """Start the activity simulator."""
        if self.simulator is None:
            # Create simulator with current config
            self._config = self.config_manager.load()
            if self.logger is None:
                self.logger = ActivityLogger(self._config.log_file_path)
            self.simulator = ActivitySimulator(self._config, self.logger)
        
        print("\nStarting idle prevention... Press Ctrl+C to stop.")
        try:
            self.simulator.start_loop()
        except KeyboardInterrupt:
            pass
        finally:
            print("\nIdle prevention stopped.")
    
    def run(self) -> None:
        """Main loop for CLI interaction."""
        # Load config on startup
        self._config = self.config_manager.load()
        
        running = True
        while running:
            self.display_menu()
            try:
                choice = input("Select option: ")
                running = self.handle_input(choice)
            except KeyboardInterrupt:
                print("\nExiting...")
                running = False
            except EOFError:
                print("\nExiting...")
                running = False


def main() -> None:
    """CLI entry point for eternal-green.
    
    This function is called when running via the 'eternal-green' command
    installed by the package.
    """
    from eternal_green.config import ConfigManager
    from eternal_green.logger import ActivityLogger
    from eternal_green.simulator import ActivitySimulator
    
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
