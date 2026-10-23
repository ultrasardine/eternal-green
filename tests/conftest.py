"""Shared fixtures for eternal-green tests."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch


@pytest.fixture(autouse=True)
def no_quartz():
    """Keep tests independent of the host's displays and input idle time.

    With Quartz unavailable, ``eternal_green.screen`` uses its portable
    fallbacks (primary display from ``pyautogui.size()``, unknown idle time).
    """
    with patch("eternal_green.screen._quartz", return_value=None):
        yield


@pytest.fixture
def temp_config_path():
    """Provide a temporary config file path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "config.json"


@pytest.fixture
def temp_log_path():
    """Provide a temporary log file path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.log"
