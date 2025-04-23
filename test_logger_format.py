#!/usr/bin/env python3
"""
Test script for demonstrating vertical alignment in the enhanced logger.
This script overrides terminal width detection to ensure proper display.
"""
import os
import sys
import logging
import threading
import time
import shutil

# Add the parent directory to the path so we can import common module
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Override terminal size detection before importing the logger
import common.logger
# Force a wider terminal width for testing
common.logger.TERMINAL_WIDTH = 140  # Even larger for demonstration

from common.logger import get_logger

def test_logger_alignment():
    """Test the vertical alignment of the enhanced logger."""
    logger = get_logger("test.alignment")
    
    # Log messages with different levels
    print("\n=== Different Log Levels ===")
    logger.debug("This is a DEBUG message")
    logger.info("This is an INFO message with alignment")
    logger.warning("This is a WARNING message with alignment")
    logger.error("This is an ERROR message with alignment")
    logger.critical("This is a CRITICAL message with alignment")
    
    # Log messages with varying content lengths
    print("\n=== Different Content Lengths ===")
    logger.info("Short message")
    logger.info("This is a medium length message that has more content")
    logger.info("This is a very long message that will test how the logger handles wrapping of long lines of text that may extend beyond the width of a typical terminal window")

def thread_logging():
    """Test logging from threads with distinct names."""
    # Thread worker function
    def worker(name, log_message):
        thread_logger = get_logger(f"thread.{name}")
        thread_logger.info(log_message)
    
    # Log messages with different thread names
    print("\n=== Thread Name Alignment ===")
    
    # Create and start threads with different name lengths
    threads = [
        threading.Thread(target=worker, args=("short", "Message from short thread"), name="T1"),
        threading.Thread(target=worker, args=("medium", "Message from medium thread"), name="Thread-Medium"),
        threading.Thread(target=worker, args=("long", "Message from very long thread name"), name="VeryLongThreadName")
    ]
    
    for thread in threads:
        thread.start()
        thread.join()

def simulate_process_logging():
    """Simulate logging from different processes without actual multiprocessing."""
    print("\n=== Simulated Process Name Alignment ===")
    
    # Simulate different process names with various lengths
    process_infos = [
        {"name": "P1", "pid": 1001},
        {"name": "Process-Medium", "pid": 1002},
        {"name": "VeryLongProcessName", "pid": 1003}
    ]
    
    logger = get_logger("process.test")
    
    # Save original process name and ID
    original_name = threading.current_thread().name
    
    # Simulate logs from different processes by temporarily changing thread name
    for process in process_infos:
        # Override thread name to simulate different processes
        threading.current_thread().name = process["name"]
        
        # Log with the simulated process info
        logger.info(f"Message from process {process['name']}")
        
    # Restore original thread name
    threading.current_thread().name = original_name

# Create loggers with different names to test alignment
logger1 = get_logger("test.logger1")
logger2 = get_logger("test.longerlogger2")
logger3 = get_logger("short")

# Log messages at different levels
logger1.debug("This is a debug message")
logger1.info("This is an info message")
logger1.warning("This is a warning message")
logger1.error("This is an error message")

# Log from different loggers to test name alignment
logger2.info("Info from a logger with a longer name")
logger3.info("Info from a short name logger")

# Log messages with different lengths
logger1.info("Short")
logger1.info("This is a much longer message that should not affect the alignment of the fields")

if __name__ == "__main__":
    print("\n" + "=" * 100)
    print("LOGGER FORMATTING TEST WITH VERTICAL ALIGNMENT".center(100))
    print("=" * 100)
    
    # Ensure we have good terminal width
    terminal_width = shutil.get_terminal_size().columns
    print(f"Terminal width: {terminal_width} columns")
    print(f"Using width: {common.logger.TERMINAL_WIDTH} columns for formatting")
    
    test_logger_alignment()
    thread_logging()
    simulate_process_logging()
    
    print("\n" + "=" * 100)
    print("LOGGER FORMATTING TEST COMPLETE".center(100))
    print("=" * 100 + "\n") 