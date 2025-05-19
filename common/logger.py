import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from typing import Optional

def get_logger(name: str, log_level: Optional[int] = None) -> logging.Logger:
    """
    Get a configured logger with console and file output.
    
    Args:
        name: Name of the logger
        log_level: Optional log level to set (defaults to INFO)
    
    Returns:
        Configured logger instance
    """
    # Set default log level if not provided
    if log_level is None:
        log_level = logging.INFO
    
    # Define log format to be used for all handlers
    log_format_str = "%(asctime)s.%(msecs)03d | %(levelname)s | %(name)s | [%(processName)s-%(process)d] | [%(threadName)s-%(thread)d] | %(filename)s:%(lineno)d | %(message)s"
    date_format_str = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter(log_format_str, date_format_str)
    
    # Get or create logger
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # Return logger if it already has handlers configured
    if logger.handlers:
        return logger
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Configure root logger for file logging if not already configured
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        # Create logs directory
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        os.makedirs(logs_dir, exist_ok=True)
        
        # Get app name from folder name
        app_name = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Create rotating file handler with daily rotation
        file_path = os.path.join(logs_dir, f"{app_name}.log")
        file_handler = TimedRotatingFileHandler(
            filename=file_path,
            when='midnight',
            interval=1,
            backupCount=30,  # Keep logs for 30 days
        )
        # Set custom naming pattern for rotated files
        file_handler.namer = lambda name: name.replace(".log", f"_{name.split('.')[-1]}.log")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        root_logger.setLevel(log_level)
    
    return logger