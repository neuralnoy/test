import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logging.getLogger("azure").setLevel(logging.WARNING)

def get_app_name() -> str:
    """
    Get the application name from environment variable.
    Returns the APP_NAME if set, otherwise returns 'unknown_app'.
    """
    return os.getenv('APP_NAME_FOR_LOGGER', 'unknown_app')

def get_logger(name: str, log_level: Optional[int] = None) -> logging.Logger:
    """
    Get a configured logger with console and file output.
    Each process gets its own log file with rotation.
    
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
            app_name = get_app_name()
            process_name = os.getenv('PROCESS_NAME', f"worker-{os.getpid()}")
            
            # Create logs directory
            logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
            os.makedirs(logs_dir, exist_ok=True)
            
            # Create process-specific log file with rotation
            log_filename = f"{app_name}__{process_name}.log"
            file_path = os.path.join(logs_dir, log_filename)
            
            file_handler = TimedRotatingFileHandler(
                filename=file_path,
                when='midnight',
                interval=1,
                backupCount=30,  # Keep logs for 30 days
                encoding='utf-8'
            )
            
            # Set custom naming pattern for rotated files
            # Use double underscore to separate timestamp from process name
            file_handler.namer = lambda name: name.replace('.log', '') + '__' + name.split('.')[-1] + '.log'
            file_handler.setFormatter(formatter)
            
            root_logger.addHandler(file_handler)
            root_logger.setLevel(log_level)
            
            logger.info(f"Process {os.getpid()} ({process_name}) logging to {file_path}")
            
            # Log a warning if using unknown_app
            if app_name == 'unknown_app':
                logger.warning("APP_NAME environment variable not set. Using 'unknown_app' as fallback.")
                
        except Exception as e:
            logger.error(f"Failed to configure file logging: {str(e)}")
            # Continue with console logging only
    
    return logger