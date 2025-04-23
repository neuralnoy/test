import sys
import os
import logging
import threading
import time
from multiprocessing import Process

# Add the parent directory to the path so we can import common module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.logger import get_logger

def test_logger_levels():
    """Test all logging levels with the enhanced logger."""
    logger = get_logger("test_levels")
    
    logger.debug("This is a DEBUG message")
    logger.info("This is an INFO message")
    logger.warning("This is a WARNING message")
    logger.error("This is an ERROR message")
    logger.critical("This is a CRITICAL message")

def thread_logging_task():
    """Function to demonstrate logging from a different thread."""
    logger = get_logger("thread_logger")
    logger.info(f"Logging from a different thread")
    
def process_logging_task():
    """Function to demonstrate logging from a different process."""
    logger = get_logger("process_logger")
    logger.info(f"Logging from a different process")

def test_thread_logging():
    """Test logging from multiple threads."""
    logger = get_logger("test_threads")
    logger.info("Starting thread logging test")
    
    threads = []
    for i in range(3):
        thread = threading.Thread(target=thread_logging_task, name=f"TestThread-{i}")
        threads.append(thread)
        thread.start()
        
    for thread in threads:
        thread.join()
        
    logger.info("Finished thread logging test")

def test_process_logging():
    """Test logging from multiple processes."""
    logger = get_logger("test_processes")
    logger.info("Starting process logging test")
    
    processes = []
    for i in range(2):
        process = Process(target=process_logging_task, name=f"TestProcess-{i}")
        processes.append(process)
        process.start()
        
    for process in processes:
        process.join()
        
    logger.info("Finished process logging test")

def test_exception_logging():
    """Test logging with exception information."""
    logger = get_logger("test_exceptions")
    
    try:
        # Intentionally cause an exception
        result = 1 / 0
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}", exc_info=True)

if __name__ == "__main__":
    print("\n=== Testing Logger Levels ===")
    test_logger_levels()
    
    print("\n=== Testing Thread Logging ===")
    test_thread_logging()
    
    print("\n=== Testing Process Logging ===")
    test_process_logging()
    
    print("\n=== Testing Exception Logging ===")
    test_exception_logging() 