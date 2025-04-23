#!/usr/bin/env python
import time
import threading
import os
import sys
from common.logger import get_logger, TERMINAL_WIDTH

# Override terminal width detection for testing
# This ensures the test will have consistent output regardless of actual terminal size
os.environ['COLUMNS'] = '140'  

def test_logger_alignment():
    """Test the vertical alignment of the enhanced logger with various log message lengths."""
    logger = get_logger("test.alignment")
    
    # Log at different levels
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.critical("This is a critical message")
    
    # Log messages with varying lengths
    logger.info("Short")
    logger.info("This is a medium length message that should fit on one line")
    logger.info("This is a very long message that might wrap to the next line depending on your terminal width. " +
               "It contains a lot of text to demonstrate how the logger handles wrapping while maintaining the " +
               "vertical alignment of the columns.")
    
    # Log with different logger names
    short_logger = get_logger("short")
    medium_logger = get_logger("medium.logger")
    very_long_logger_name = get_logger("very.long.logger.name.that.needs.truncation")
    
    short_logger.info("Message from short logger")
    medium_logger.info("Message from medium logger")
    very_long_logger_name.info("Message from long logger")

def test_thread_logging():
    """Test logging from multiple threads to verify thread information is aligned."""
    logger = get_logger("test.threads")
    
    def worker(name, count):
        thread_logger = get_logger(f"thread.{name}")
        for i in range(count):
            thread_logger.info(f"Message {i+1} from thread {name}")
            time.sleep(0.1)
    
    # Create and start threads
    threads = []
    for i in range(3):
        thread_name = f"Worker-{i+1}"
        t = threading.Thread(target=worker, args=(thread_name, 2), name=thread_name)
        threads.append(t)
        t.start()
    
    # Log from main thread
    logger.info("Message from main thread")
    
    # Wait for all threads to complete
    for t in threads:
        t.join()

if __name__ == "__main__":
    main_logger = get_logger("test_logger_alignment")
    main_logger.info(f"Testing logger with terminal width: {TERMINAL_WIDTH}")
    main_logger.info("=" * 100)
    
    main_logger.info("Testing basic logger alignment")
    test_logger_alignment()
    
    main_logger.info("=" * 100)
    main_logger.info("Testing thread logging")
    test_thread_logging()
    
    main_logger.info("=" * 100)
    main_logger.info("Logger alignment test completed") 