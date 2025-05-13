import logging
import os
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
    # Create a root logger if it doesn't exist yet
    root_logger = logging.getLogger()
    log_level = log_level if log_level is not None else logging.INFO
    
    # Only configure root logger if it hasn't been configured yet
    if not root_logger.handlers:
        root_logger.setLevel(log_level)
        
        # Create logs directory if it doesn't exist
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        os.makedirs(logs_dir, exist_ok=True)
        
        # Common log format
        log_format = (
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "[%(processName)s-%(process)d] | "
            "[%(threadName)s-%(thread)d] | "
            "%(filename)s:%(lineno)d | "
            "%(message)s"
        )
        date_format = '%Y-%m-%d %H:%M:%S'
        
        # Create file handler
        file_handler = logging.FileHandler(os.path.join(logs_dir, "app.log"))
        file_formatter = logging.Formatter(log_format, date_format)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    
    # Get the logger for this module
    logger = logging.getLogger(name)
    
    # Only configure console handler if it hasn't been configured yet
    if not logger.handlers:
        # Create console handler
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter(log_format, date_format)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # Set log level
        logger.setLevel(log_level)
    
    return logger