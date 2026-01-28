"""Tests for logging module."""

import re
import tempfile
from pathlib import Path
from hypothesis import given, strategies as st, settings
from eternal_green.logger import ActivityLogger


# Strategy for generating valid log messages (printable chars without control chars)
printable_message = st.text(
    alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'S', 'Zs'),
        blacklist_characters='\r\n\x00'
    ),
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
