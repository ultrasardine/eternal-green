"""Tests for logging module."""

import re
import tempfile
from pathlib import Path
from hypothesis import given, strategies as st, settings
from eternal_green.logger import ActivityLogger


# Strategy for generating valid log messages (ASCII printable chars only for cross-platform compatibility)
printable_message = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),  # ASCII printable only
    min_size=1,
    max_size=100
).filter(lambda x: x.strip())


# Feature: eternal-green, Property 7: Log Entry Format Compliance
# **Validates: Requirements 4.1, 4.4**
@settings(max_examples=100)
@given(message=printable_message)
def test_log_entry_format_compliance_info(message):
    """For any logged activity event, the log entry should contain a valid ISO timestamp and valid log level."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "test.log"
        logger = ActivityLogger(str(log_path))
        
        logger.log_activity(message)
        
        # Close logger handlers to release file on Windows
        for handler in logger.logger.handlers[:]:
            handler.close()
            logger.logger.removeHandler(handler)
        
        log_content = log_path.read_text()
        
        # Verify format: [TIMESTAMP] [LEVEL] [COMPONENT] MESSAGE
        pattern = r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[(INFO|WARNING|ERROR)\] \[[\w_]+\] .+$'
        
        lines = log_content.strip().split('\n')
        assert len(lines) >= 1
        
        for line in lines:
            match = re.match(pattern, line)
            assert match is not None, f"Log line does not match expected format: {line}"
            
            timestamp = match.group(1)
            assert re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', timestamp)
            
            level = match.group(2)
            assert level in ('INFO', 'WARNING', 'ERROR')


@settings(max_examples=100)
@given(message=printable_message)
def test_log_entry_format_compliance_error(message):
    """For any logged error event, the log entry should contain a valid ISO timestamp and ERROR level."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "test.log"
        logger = ActivityLogger(str(log_path))
        
        logger.log_error(message)
        
        # Close logger handlers to release file on Windows
        for handler in logger.logger.handlers[:]:
            handler.close()
            logger.logger.removeHandler(handler)
        
        log_content = log_path.read_text()
        
        pattern = r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[(ERROR)\] \[[\w_]+\] .+$'
        
        lines = log_content.strip().split('\n')
        assert len(lines) >= 1
        
        for line in lines:
            match = re.match(pattern, line)
            assert match is not None, f"Log line does not match expected format: {line}"


@settings(max_examples=100)
@given(message=printable_message)
def test_log_entry_format_compliance_warning(message):
    """For any logged warning event, the log entry should contain a valid ISO timestamp and WARNING level."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "test.log"
        logger = ActivityLogger(str(log_path))
        
        logger.log_warning(message)
        
        # Close logger handlers to release file on Windows
        for handler in logger.logger.handlers[:]:
            handler.close()
            logger.logger.removeHandler(handler)
        
        log_content = log_path.read_text()
        
        pattern = r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[(WARNING)\] \[[\w_]+\] .+$'
        
        lines = log_content.strip().split('\n')
        assert len(lines) >= 1
        
        for line in lines:
            match = re.match(pattern, line)
            assert match is not None, f"Log line does not match expected format: {line}"


def test_loggers_with_different_paths_are_independent(tmp_path):
    first = ActivityLogger(str(tmp_path / "a.log"))
    second = ActivityLogger(str(tmp_path / "b.log"))
    first.log_activity("one")
    second.log_activity("two")
    first.log_activity("three")
    first.close()
    second.close()

    a = (tmp_path / "a.log").read_text()
    b = (tmp_path / "b.log").read_text()
    assert "one" in a and "three" in a and "two" not in a
    assert "two" in b and "one" not in b


def test_close_releases_handler_and_reopens_on_demand(tmp_path):
    logger = ActivityLogger(str(tmp_path / "a.log"))
    logger.log_activity("before")
    handler = logger.logger.handlers[0]
    logger.close()
    assert handler.stream is None  # file closed
    logger.log_activity("after")
    logger.close()
    assert "after" in (tmp_path / "a.log").read_text()


def test_error_with_traceback(tmp_path):
    logger = ActivityLogger(str(tmp_path / "a.log"))
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        logger.log_error("failed", exc_info=True)
    logger.close()
    content = (tmp_path / "a.log").read_text()
    assert "failed" in content and "RuntimeError: boom" in content
