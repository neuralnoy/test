import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from typing import Optional

def get_app_name() -> str:
    """
    Get the application name from the directory containing main.py.
    Returns the directory name if found, otherwise returns 'unknown_app'.
    """
    try:
        # Start from the current directory and walk up until we find main.py
        current_path = os.path.abspath(os.getcwd())
        while current_path != os.path.dirname(current_path):  # Stop at root directory
            if os.path.exists(os.path.join(current_path, 'main.py')):
                return os.path.basename(current_path)
            current_path = os.path.dirname(current_path)
        return 'unknown_app'
    except Exception as e:
        logging.error(f"Error determining app name: {str(e)}")
        return 'unknown_app'

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
        try:
            # Get app name from main.py directory
            app_name = get_app_name()
            
            # Create logs directory
            logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
            os.makedirs(logs_dir, exist_ok=True)
            
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
            
            # Log a warning if using unknown_app
            if app_name == 'unknown_app':
                logger.warning("Could not find main.py in directory structure. Using 'unknown_app' as fallback.")
                
        except Exception as e:
            logger.error(f"Failed to configure file logging: {str(e)}")
            # Continue with console logging only
    
    return logger