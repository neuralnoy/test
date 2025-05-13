import logging
import os
from logging.handlers import TimedRotatingFileHandler
from typing import Optional

# --- Configuration Constants ---
# Rotates logs every N minutes.
LOG_ROTATION_INTERVAL_MINUTES = 1
# Keeps the most recent N rotated log files. Set to 0 to keep all.
LOG_BACKUP_COUNT = 60
# Default log level if not specified when calling get_logger.
DEFAULT_LOG_LEVEL = logging.INFO
# --- End Configuration Constants ---

# Ensure the root logger is configured only once.
_root_logger_configured = False

def get_logger(name: str, log_level: Optional[int] = None) -> logging.Logger:
    """
    Get a configured logger that writes to time-rotated files in a 'logs' directory.

    Args:
        name: Name of the logger.
        log_level: Optional log level to set for this specific logger instance.
                   Defaults to DEFAULT_LOG_LEVEL.

    Returns:
        Configured logger instance.
    """
    global _root_logger_configured

    # Determine the log level for this logger instance.
    effective_log_level = log_level if log_level is not None else DEFAULT_LOG_LEVEL

    # Configure the root logger and its handlers only once.
    if not _root_logger_configured:
        root_logger = logging.getLogger()
        # Set the root logger's level to the lowest possible (e.g., DEBUG)
        # to allow handlers to control their own levels effectively,
        # or set it based on the first logger's request. For simplicity,
        # let's set it based on the default or first request.
        root_logger.setLevel(DEFAULT_LOG_LEVEL) # Or min(DEFAULT_LOG_LEVEL, effective_log_level) if more dynamic

        # --- File Handler Setup ---
        # Create 'logs' directory if it doesn't exist.
        # Assumes logger.py is in a subdirectory (e.g., 'common') 
        # and 'logs' is at the project root.
        project_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logs_dir = os.path.join(project_root_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        
        log_file_path = os.path.join(logs_dir, "app.log")

        # Log format: Timestamp.Milliseconds | Level | LoggerName | ProcessInfo | ThreadInfo | File:Line | Message
        log_format_string = "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | [%(processName)s-%(process)d] | [%(threadName)s-%(thread)d] | %(filename)s:%(lineno)d | %(message)s"
        date_format_string = '%Y-%m-%d %H:%M:%S'

        formatter = logging.Formatter(fmt=log_format_string, datefmt=date_format_string)

        # Timed Rotating File Handler
        file_handler = TimedRotatingFileHandler(
            filename=log_file_path,
            when='M',  # Rotate by minutes
            interval=LOG_ROTATION_INTERVAL_MINUTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding='utf-8',
            delay=False, # Open file immediately
            utc=False    # Use local time for rotation
        )
        # The default suffix for TimedRotatingFileHandler is .YYYY-MM-DD_HH-MM-SS
        # If interval is less than a day, HH-MM-SS is used. If less than an hour, MM-SS. If less than a minute, SS.
        # For 'M' interval, it will be like .YYYY-MM-DD_HH-MM
        # To get seconds in suffix as well if rotating every minute, need to adjust this.
        # However, default behavior should be fine. The timestamp in the log lines has seconds.
        
        file_handler.setFormatter(formatter)
        file_handler.setLevel(DEFAULT_LOG_LEVEL) # Handler respects this level

        root_logger.addHandler(file_handler)
        
        root_logger.info(f"Root logger configured. File logging to: {log_file_path}")
        root_logger.info(f"Log rotation: every {LOG_ROTATION_INTERVAL_MINUTES} minute(s), keeping {LOG_BACKUP_COUNT} backups.")

        _root_logger_configured = True

    # Get the specific logger instance.
    logger = logging.getLogger(name)
    logger.setLevel(effective_log_level)
    # Handlers are on the root logger; messages will propagate by default.
    
    return logger

if __name__ == '__main__':
    # Example usage (for testing this module directly)
    # This part will only run if you execute logger.py directly (e.g., python common/logger.py)
    
    # Configure a default level for the test loggers
    test_log_level = logging.DEBUG 

    logger1 = get_logger("TestApp1", log_level=test_log_level)
    logger2 = get_logger("TestApp2.ModuleA", log_level=test_log_level)
    
    logger1.info("This is an info message from TestApp1.")
    logger1.debug("This is a debug message from TestApp1.") # Will show if test_log_level is DEBUG
    
    import time
    count = 0
    try:
        while count < 150: # Log for 2.5 minutes if interval is 1s
            logger2.info(f"TestApp2.ModuleA logging message count: {count+1}")
            time.sleep(1) # Log a message every second
            count += 1
            if count % 30 == 0:
                 logger1.warning(f"TestApp1: Reached {count} messages.")
    except KeyboardInterrupt:
        logger1.info("Test logging interrupted by user.")
    finally:
        logger1.info("Test logging finished.")
