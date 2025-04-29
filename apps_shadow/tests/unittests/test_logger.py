import pytest
import logging
import io
import sys
import re
from unittest.mock import patch, MagicMock

from common.logger import (
    get_logger,
    FixedWidthColoredFormatter,
    calculate_field_widths,
    NAME_WIDTH,
    PROCESS_WIDTH,
    THREAD_WIDTH,
    FILE_WIDTH,
    LEVEL_WIDTH
)

class TestLogger:
    """Test suite for the logger module"""

    @pytest.fixture
    def log_stream(self):
        """Create a stream for capturing log output"""
        stream = io.StringIO()
        return stream

    @pytest.fixture
    def test_logger(self, log_stream):
        """Create a logger for testing"""
        logger = logging.getLogger("test_logger")
        
        # Clear existing handlers
        logger.handlers = []
        
        # Set level to DEBUG
        logger.setLevel(logging.DEBUG)
        
        # Create a StreamHandler with our test stream
        handler = logging.StreamHandler(log_stream)
        logger.addHandler(handler)
        
        return logger, log_stream

    def test_get_logger(self):
        """Test that get_logger returns a configured logger"""
        logger = get_logger("test_module")
        
        # Test logger has correct name
        assert logger.name == "test_module"
        
        # Test logger has appropriate level
        assert logger.level == logging.INFO
        
        # Test logger has a handler
        assert len(logger.handlers) == 1
        
        # Test handler has a formatter
        handler = logger.handlers[0]
        assert handler.formatter is not None

    def test_get_logger_with_level(self):
        """Test that get_logger accepts a custom log level"""
        logger = get_logger("test_module", logging.DEBUG)
        
        # Test logger has correct level
        assert logger.level == logging.DEBUG

    def test_get_logger_singleton(self):
        """Test that get_logger returns the same logger for the same name"""
        logger1 = get_logger("test_singleton")
        logger2 = get_logger("test_singleton")
        
        # Should be the same logger instance
        assert logger1 is logger2
        
        # Should have only one handler
        assert len(logger1.handlers) == 1

    def test_fixed_width_colored_formatter(self, test_logger):
        """Test the fixed width colored formatter"""
        logger, stream = test_logger
        
        # Create and apply a colored formatter
        formatter = FixedWidthColoredFormatter(
            "%(levelname_colored)s | %(name_colored)s | %(message)s",
            name_width=10,
            level_width=7
        )
        logger.handlers[0].setFormatter(formatter)
        
        # Log a message
        logger.info("Test message")
        
        # Get the output
        output = stream.getvalue()
        
        # Test that output contains the message
        assert "Test message" in output
        
        # Test that output contains color codes
        assert "\033[" in output
        
        # Test that level and name fields are present
        assert "INFO" in output
        assert "test_logger" in output

    def test_truncate_string(self):
        """Test string truncation in the formatter"""
        formatter = FixedWidthColoredFormatter()
        
        # Test string shorter than max length
        short_str = "short"
        assert formatter.truncate_string(short_str, 10) == short_str.ljust(10)
        
        # Test string longer than max length
        long_str = "this_is_a_very_long_string"
        truncated = formatter.truncate_string(long_str, 15)
        assert len(truncated) == 15
        assert ".." in truncated
        
        # Test very short max length
        very_long_str = "this_is_a_very_long_string_that_needs_more_truncation"
        very_truncated = formatter.truncate_string(very_long_str, 5)
        assert len(very_truncated) == 5
        assert ".." in very_truncated

    def test_logger_formatting(self):
        """Test that logger formatting is applied correctly"""
        # Create a string stream to capture output
        stream = io.StringIO()
        
        # Create a logger with a handler for this stream
        logger = logging.getLogger("format_test")
        logger.handlers = []  # Clear existing handlers
        logger.setLevel(logging.DEBUG)
        
        handler = logging.StreamHandler(stream)
        logger.addHandler(handler)
        
        # Create a formatter without color (for easier testing)
        format_str = "%(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
        formatter = logging.Formatter(format_str)
        handler.setFormatter(formatter)
        
        # Log a message
        logger.info("Test message")
        
        # Get the output
        output = stream.getvalue()
        
        # Check if the output matches the expected format
        assert "INFO" in output
        assert "format_test" in output
        assert "test_logger.py" in output
        assert "Test message" in output

    @patch('common.logger.shutil.get_terminal_size')
    def test_calculate_field_widths_large_terminal(self, mock_get_terminal_size):
        """Test field width calculation for large terminals"""
        # Mock terminal width to be large
        mock_get_terminal_size.return_value = MagicMock(columns=120)
        
        # Calculate widths
        name_width, process_width, thread_width, file_width, level_width = calculate_field_widths()
        
        # For large terminals, should use defaults
        assert name_width == NAME_WIDTH
        assert process_width == PROCESS_WIDTH
        assert thread_width == THREAD_WIDTH
        assert file_width == FILE_WIDTH
        assert level_width == LEVEL_WIDTH

    @patch('common.logger.shutil.get_terminal_size')
    def test_calculate_field_widths_small_terminal(self, mock_get_terminal_size):
        """Test field width calculation for small terminals"""
        # Mock terminal width to be small
        mock_get_terminal_size.return_value = MagicMock(columns=60)
        
        # Calculate widths
        name_width, process_width, thread_width, file_width, level_width = calculate_field_widths()
        
        # For small terminals, widths should be reduced
        assert name_width < NAME_WIDTH
        assert process_width < PROCESS_WIDTH
        assert thread_width < THREAD_WIDTH
        assert file_width < FILE_WIDTH
        assert level_width == LEVEL_WIDTH  # Level width should remain constant

    @patch('common.logger.shutil.get_terminal_size')
    def test_calculate_field_widths_error(self, mock_get_terminal_size):
        """Test field width calculation when an error occurs"""
        # Mock get_terminal_size to raise an exception
        mock_get_terminal_size.side_effect = AttributeError("No terminal size")
        
        # Calculate widths - should fall back to defaults
        name_width, process_width, thread_width, file_width, level_width = calculate_field_widths()
        
        assert name_width == NAME_WIDTH
        assert process_width == PROCESS_WIDTH
        assert thread_width == THREAD_WIDTH
        assert file_width == FILE_WIDTH
        assert level_width == LEVEL_WIDTH

    @patch('common.logger.sys.stdout.isatty')
    def test_get_logger_non_tty(self, mock_isatty):
        """Test logger configuration for non-tty environment"""
        # Mock isatty to return False (not a terminal)
        mock_isatty.return_value = False
        
        # Get a logger
        logger = get_logger("non_tty_test")
        
        # Formatter should be a standard Formatter, not our custom one
        handler = logger.handlers[0]
        assert isinstance(handler.formatter, logging.Formatter)
        assert not isinstance(handler.formatter, FixedWidthColoredFormatter)

    @patch('common.logger.sys.stdout.isatty')
    def test_get_logger_tty(self, mock_isatty):
        """Test logger configuration for tty environment"""
        # Mock isatty to return True (is a terminal)
        mock_isatty.return_value = True
        
        # Get a logger
        logger = get_logger("tty_test")
        
        # Formatter should be our custom FixedWidthColoredFormatter
        handler = logger.handlers[0]
        assert isinstance(handler.formatter, FixedWidthColoredFormatter)

    def test_log_all_levels(self, test_logger):
        """Test logging at all levels"""
        logger, stream = test_logger
        
        # Log messages at different levels
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        logger.critical("Critical message")
        
        # Get the output
        output = stream.getvalue()
        
        # Check all messages are present
        assert "Debug message" in output
        assert "Info message" in output
        assert "Warning message" in output
        assert "Error message" in output
        assert "Critical message" in output

    def test_format_with_process_and_thread_info(self):
        """Test formatting with process and thread information"""
        formatter = FixedWidthColoredFormatter(
            "%(process_info_colored)s | %(thread_info_colored)s | %(message)s",
            process_width=15,
            thread_width=15
        )
        
        # Create a log record with process and thread info
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
            func=None,
            sinfo=None
        )
        record.processName = "MainProcess"
        record.process = 123
        record.threadName = "MainThread"
        record.thread = 456
        
        # Format the record
        output = formatter.format(record)
        
        # Check that process and thread info are included
        assert "MainProcess" in output
        assert "123" in output
        assert "MainThread" in output
        assert "456" in output

    def test_format_with_file_info(self):
        """Test formatting with file information"""
        formatter = FixedWidthColoredFormatter(
            "%(file_info_colored)s | %(message)s",
            file_width=20
        )
        
        # Create a log record with file info
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test_module.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func=None,
            sinfo=None
        )
        
        # Format the record
        output = formatter.format(record)
        
        # Check that file info is included
        assert "test_module.py" in output
        assert "42" in output 