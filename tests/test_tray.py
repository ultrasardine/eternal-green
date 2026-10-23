"""Tests for the system tray controller (pystray itself is not started)."""

import threading
from unittest.mock import MagicMock, patch

from eternal_green.config import ConfigManager
from eternal_green.simulator import ActivitySimulator
from eternal_green.tray import TrayIcon


def _tray(temp_config_path, temp_log_path):
    manager = ConfigManager(temp_config_path)
    manager.update(log_file_path=str(temp_log_path))
    tray = TrayIcon(manager)
    tray._icon = MagicMock()
    return tray


def test_icon_refreshes_when_loop_ends_on_its_own(temp_config_path, temp_log_path):
    tray = _tray(temp_config_path, temp_log_path)
    ended = threading.Event()

    def refresh():
        ended.set()

    with patch.object(ActivitySimulator, "start_loop", side_effect=RuntimeError("boom")), \
         patch("eternal_green.tray._on_ui_thread", side_effect=lambda fn: refresh()):
        tray._toggle(None, None)
        assert ended.wait(timeout=5)
        tray._sim_thread.join(timeout=5)

    assert not tray.simulator.is_running
    assert "Idle prevention failed: boom" in temp_log_path.read_text()


def test_menu_shows_running_immediately_after_start(temp_config_path, temp_log_path):
    tray = _tray(temp_config_path, temp_log_path)
    release = threading.Event()

    def loop(self):
        release.wait(timeout=5)
        self._running = False

    with patch.object(ActivitySimulator, "start_loop", loop), \
         patch("eternal_green.tray._on_ui_thread"):
        tray._toggle(None, None)
        assert tray.simulator.is_running
        release.set()
        tray._sim_thread.join(timeout=5)


def test_settings_window_opens_only_once(temp_config_path, temp_log_path):
    tray = _tray(temp_config_path, temp_log_path)
    process = MagicMock()
    process.poll.return_value = None  # still open
    process.wait.side_effect = lambda: threading.Event().wait(0.1)

    with patch("eternal_green.tray.subprocess.Popen", return_value=process) as popen:
        tray._open_settings(None, None)
        tray._open_settings(None, None)

    popen.assert_called_once()


def test_toggle_silent_keeps_changes_saved_by_settings_window(temp_config_path, temp_log_path):
    tray = _tray(temp_config_path, temp_log_path)
    ConfigManager(temp_config_path).update(interval_seconds=120)

    tray._toggle_silent(None, None)

    reloaded = ConfigManager(temp_config_path).load()
    assert reloaded.silent_mode is True
    assert reloaded.interval_seconds == 120
