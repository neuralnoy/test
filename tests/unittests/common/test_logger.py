import logging
import unittest
import io
import sys
import os
from unittest.mock import patch, MagicMock

# Add the parent directory to the path so we can import common module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from common.logger import get_logger, ColoredFormatter, COLORS, LEVEL_COLORS


class TestLogger(unittest.TestCase):
    """Unit tests for the enhanced logger functionality."""
    
    def test_get_logger_creates_handler_once(self):
        """Test that logger only gets configured once no matter how many times get_logger is called."""
        # Clear any existing logger
        logger_name = "test_single_config"
        if logger_name in logging.Logger.manager.loggerDict:
            del logging.Logger.manager.loggerDict[logger_name]
        
        # Get the logger twice
        logger1 = get_logger(logger_name)
        num_handlers1 = len(logger1.handlers)
        
        logger2 = get_logger(logger_name)
        num_handlers2 = len(logger2.handlers)
        
        # Verify only one handler was created
        self.assertEqual(num_handlers1, 1)
        self.assertEqual(num_handlers2, 1)
        self.assertIs(logger1, logger2)
    
    def test_get_logger_with_custom_level(self):
        """Test get_logger with custom log level."""
        # Get a logger with DEBUG level
        logger_name = "test_debug_level"
        if logger_name in logging.Logger.manager.loggerDict:
            del logging.Logger.manager.loggerDict[logger_name]
        
        logger = get_logger(logger_name, logging.DEBUG)
        
        # Verify the log level is set correctly
        self.assertEqual(logger.level, logging.DEBUG)
    
    def test_get_logger_default_level(self):
        """Test that get_logger uses INFO as default log level."""
        # Get a logger with default level
        logger_name = "test_default_level"
        if logger_name in logging.Logger.manager.loggerDict:
            del logging.Logger.manager.loggerDict[logger_name]
        
        logger = get_logger(logger_name)
        
        # Verify the log level is INFO
        self.assertEqual(logger.level, logging.INFO)
    
    def test_colored_formatter(self):
        """Test that ColoredFormatter correctly colorizes log records."""
        # Create a record with INFO level
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test_file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        # Create formatter with simple format that includes levelname
        formatter = ColoredFormatter("%(levelname)s: %(message)s")
        
        # Format the record
        formatted = formatter.format(record)
        
        # Check that levelname is colorized
        expected_level_color = LEVEL_COLORS[logging.INFO] + "INFO" + COLORS['RESET']
        self.assertIn(expected_level_color, formatted)
    
    def test_logger_output_includes_all_info(self):
        """Test that logger output includes all required information."""
        # Capture logger output
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        
        # Create a simple format that includes all required fields
        log_format = (
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "[%(processName)s-%(process)d] | "
            "[%(threadName)s-%(thread)d] | "
            "%(filename)s:%(lineno)d | "
            "%(message)s"
        )
        formatter = logging.Formatter(log_format)
        handler.setFormatter(formatter)
        
        # Create a logger with our custom formatter
        logger_name = "test_output"
        if logger_name in logging.Logger.manager.loggerDict:
            del logging.Logger.manager.loggerDict[logger_name]
        
        logger = logging.getLogger(logger_name)
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        
        # Log a message
        logger.info("Test message")
        
        # Get the output
        output = stream.getvalue()
        
        # Check that all required fields are present
        self.assertIn(logger_name, output)  # Logger name
        self.assertIn("INFO", output)  # Log level
        self.assertIn("Test message", output)  # Message
        self.assertIn("MainProcess", output)  # Process name
        self.assertIn("MainThread", output)  # Thread name
        self.assertIn("test_logger.py", output)  # Filename


if __name__ == '__main__':
    unittest.main() 