# Eternal Green

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)

Anti-idle application that prevents computer inactivity by simulating minimal user input. Keep your system active without intrusive actions.

## Features

- 🖱️ **Configurable mouse movements** - Set custom movement distances
- ⏱️ **Adjustable intervals** - Control how often activity is simulated
- 🎲 **Random intervals** - Randomize timing between activities for more natural behavior
- 🔇 **Silent mode** - Mouse-only movements without keystrokes
- 📝 **Activity logging** - Track all simulations to a log file
- 💬 **Real-time feedback** - Console output with success/error indicators
- ⚙️ **Interactive CLI** - Easy configuration management
- 🔌 **Library integration** - Use as a Python package in your projects

## Installation

### As a Standalone Application

```bash
# Clone the repository
git clone https://github.com/ultrasardine/eternal-green.git
cd eternal-green

# Install with uv
uv sync
```

### As a Python Package

```bash
# Install from source
uv pip install git+https://github.com/ultrasardine/eternal-green.git
```

### Development Installation

```bash
# Clone and install with dev dependencies
git clone https://github.com/ultrasardine/eternal-green.git
cd eternal-green
uv sync --extra dev
```

## Usage

### Interactive CLI

Run the interactive command-line interface:

```bash
uv run eternal-green
```

Or as a module:

```bash
uv run python -m eternal_green
```

The CLI provides a menu with options to:
1. View current configuration
2. Edit interval (seconds between activities)
3. Edit movement (pixels for mouse movement)
4. Toggle silent mode (disable keystrokes)
5. Edit log file path
6. Toggle random interval (randomize timing for pattern prevention)
7. Edit random interval range (set min/max seconds)
8. Start idle prevention
9. Exit

### Console Output

The application provides real-time feedback during operation:
- `▶ Starting idle prevention loop (interval: Xs)` - When simulation starts
- `✓ Activity simulation completed - mouse moved Xpx (silent mode/with keystroke)` - Each successful activity
- `✗ Error during activity simulation: ...` - If errors occur
- `■ Graceful shutdown initiated` - When stopping

All activity is also logged to the configured log file (default: `~/.eternal_green/activity.log`).

### Library Integration

Use Eternal Green as a library in your Python projects:

#### Basic Usage

```python
from eternal_green import ActivitySimulator, EternalGreenConfig, ActivityLogger

# Create configuration
config = EternalGreenConfig(
    interval_seconds=60,
    movement_pixels=10,
    silent_mode=True,
    log_file_path="~/my_app.log"
)

# Initialize logger
logger = ActivityLogger(config.log_file_path)

# Create simulator
simulator = ActivitySimulator(config, logger)

# Simulate activity once
simulator.simulate_activity()

# Simulate activity with next interval info (shows "next in Xs" in logs)
simulator.simulate_activity(next_interval=60)
```

#### Using Random Intervals

```python
from eternal_green import ActivitySimulator, EternalGreenConfig, ActivityLogger

# Configure with random intervals between 30-120 seconds
config = EternalGreenConfig(
    random_interval=True,
    interval_range_min=30,
    interval_range_max=120,
    movement_pixels=10,
    silent_mode=True
)

logger = ActivityLogger("~/activity.log")
simulator = ActivitySimulator(config, logger)

# Start the loop with randomized timing
simulator.start_loop()
```

#### Running Continuous Loop

```python
from eternal_green import ActivitySimulator, EternalGreenConfig, ActivityLogger

config = EternalGreenConfig(interval_seconds=30, silent_mode=False)
logger = ActivityLogger("~/activity.log")
simulator = ActivitySimulator(config, logger)

# Start the loop (runs until Ctrl+C or simulator.stop())
try:
    simulator.start_loop()
except KeyboardInterrupt:
    print("Stopped by user")
```

#### Configuration Management

```python
from eternal_green import ConfigManager

# Load configuration from file
config_manager = ConfigManager()
config = config_manager.load()

# Update configuration
new_config = config_manager.update(
    interval_seconds=120,
    silent_mode=True
)

# Configuration is automatically saved to ~/.eternal_green/config.json
```

#### Custom Logger Setup

```python
from eternal_green import setup_logger

# Create a custom logger
logger = setup_logger(
    log_file_path="~/custom_path/activity.log",
    name="my_app"
)

logger.info("Custom log message")
```

## Configuration

Configuration is stored in `~/.eternal_green/config.json` with the following options:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `interval_seconds` | int | 60 | Seconds between activity simulations (min: 10, max: 3600) |
| `movement_pixels` | int | 10 | Pixels to move mouse (min: 1, max: 100) |
| `silent_mode` | bool | false | If true, only moves mouse (no keystrokes) |
| `log_file_path` | str | `~/.eternal_green/activity.log` | Path to activity log file |
| `random_interval` | bool | false | If true, randomizes interval between min and max range |
| `interval_range_min` | int | 10 | Minimum seconds for random interval (min: 10, max: 3600) |
| `interval_range_max` | int | 60 | Maximum seconds for random interval (min: 10, max: 3600) |

### Example Configuration File

```json
{
  "interval_seconds": 60,
  "movement_pixels": 10,
  "silent_mode": false,
  "log_file_path": "~/.eternal_green/activity.log",
  "random_interval": false,
  "interval_range_min": 10,
  "interval_range_max": 60
}
```

## Examples

### Example 1: Silent Mode with Custom Interval

```python
from eternal_green import ActivitySimulator, EternalGreenConfig, ActivityLogger

# Configure for silent operation every 2 minutes
config = EternalGreenConfig(
    interval_seconds=120,
    movement_pixels=5,
    silent_mode=True
)

logger = ActivityLogger("~/silent_activity.log")
simulator = ActivitySimulator(config, logger)

# Run for a specific duration
import threading
import time

# Start in background thread
thread = threading.Thread(target=simulator.start_loop)
thread.start()

# Run for 10 minutes then stop
time.sleep(600)
simulator.stop()
thread.join()
```

### Example 2: Integration with Existing Application

```python
import signal
from eternal_green import ActivitySimulator, EternalGreenConfig, ActivityLogger

class MyApplication:
    def __init__(self):
        # Initialize your app
        self.running = True
        
        # Add idle prevention
        config = EternalGreenConfig(interval_seconds=90, silent_mode=True)
        logger = ActivityLogger("~/myapp_activity.log")
        self.idle_preventer = ActivitySimulator(config, logger)
    
    def start(self):
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)
        
        # Start idle prevention in background
        import threading
        idle_thread = threading.Thread(target=self.idle_preventer.start_loop)
        idle_thread.daemon = True
        idle_thread.start()
        
        # Your application logic
        while self.running:
            # Do your work
            pass
    
    def _shutdown(self, signum, frame):
        print("Shutting down...")
        self.idle_preventer.stop()
        self.running = False

# Run the application
app = MyApplication()
app.start()
```

### Example 3: One-Time Activity Simulation

```python
from eternal_green import ActivitySimulator, EternalGreenConfig

# Simple one-time activity simulation
config = EternalGreenConfig(movement_pixels=15, silent_mode=True)
simulator = ActivitySimulator(config)

# Simulate activity once
success = simulator.simulate_activity()
if success:
    print("Activity simulated successfully")

# Simulate with timing info for next activity
success = simulator.simulate_activity(next_interval=120)
# Output: "✓ Activity simulation completed - mouse moved 15px (silent mode), next in 120s"
```

## Requirements

- Python 3.13 or higher
- `pyautogui` - Cross-platform GUI automation

### System Requirements

- **macOS**: No additional setup required
- **Linux**: May require `python3-tk`, `python3-dev`, `scrot`, `xdotool`
- **Windows**: No additional setup required

## Development

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=eternal_green

# Run specific test file
uv run pytest tests/test_simulator.py
```

### Project Structure

```
eternal-green/
├── eternal_green/          # Main package
│   ├── __init__.py        # Package exports
│   ├── __main__.py        # Module entry point
│   ├── cli.py             # Interactive CLI
│   ├── config.py          # Configuration management
│   ├── logger.py          # Logging functionality
│   └── simulator.py       # Activity simulation
├── tests/                 # Test suite
├── CODE_OF_CONDUCT.md     # Community guidelines
├── CONTRIBUTING.md        # Contribution guidelines
├── LICENSE                # MIT License
├── README.md              # This file
├── SECURITY.md            # Security policy
└── pyproject.toml         # Project metadata

```

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a Pull Request

All PRs require admin approval before merging to `master`.

## Security

See [SECURITY.md](SECURITY.md) for security considerations and how to report vulnerabilities.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- 🐛 [Report a bug](https://github.com/ultrasardine/eternal-green/issues)
- 💡 [Request a feature](https://github.com/ultrasardine/eternal-green/issues)
- 📖 [Documentation](https://github.com/ultrasardine/eternal-green)

## Acknowledgments

Built with:
- [pyautogui](https://github.com/asweigart/pyautogui) - GUI automation
- [pytest](https://pytest.org/) - Testing framework
- [hypothesis](https://hypothesis.readthedocs.io/) - Property-based testing
