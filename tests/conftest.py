"""Shared fixtures for eternal-green tests."""

import pytest
import tempfile
from pathlib import Path


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
