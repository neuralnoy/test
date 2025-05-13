import logging
import os
import threading
import multiprocessing
import platform
import sys
import shutil
import atexit
from typing import Optional, Tuple, Any
from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener

# Global variables for queue-based logging
_log_queue = None
_queue_listener = None
_listener_configured = False

# Get terminal width, default to 120 if not available
try:
    TERMINAL_WIDTH = shutil.get_terminal_size().columns
except (AttributeError, ValueError):
    TERMINAL_WIDTH = 120

# ANSI color codes
COLORS = {
    'RESET': '\033[0m',
    'BLACK': '\033[30m',
    'RED': '\033[31m',
    'GREEN': '\033[32m',
    'YELLOW': '\033[33m',
    'BLUE': '\033[34m',
    'MAGENTA': '\033[35m',
    'CYAN': '\033[36m',
    'WHITE': '\033[37m',
    'BOLD': '\033[1m',
    'UNDERLINE': '\033[4m',
    'GRAY': '\033[90m'
}

# Define log level colors
LEVEL_COLORS = {
    logging.DEBUG: COLORS['GRAY'],
    logging.INFO: COLORS['GREEN'],
    logging.WARNING: COLORS['YELLOW'],
    logging.ERROR: COLORS['RED'],
    logging.CRITICAL: COLORS['RED'] + COLORS['BOLD'],
}

# Default field widths for formatting - more conservative
NAME_WIDTH = 15
PROCESS_WIDTH = 16
THREAD_WIDTH = 16
FILE_WIDTH = 20
LEVEL_WIDTH = 8

class FixedWidthColoredFormatter(logging.Formatter):
    """
    Custom formatter that adds colors and ensures fixed-width fields for vertical alignment.
    Color codes don't count toward field width to ensure perfect vertical alignment.
    """
    
    def __init__(self, fmt=None, datefmt=None, name_width=NAME_WIDTH, 
                 process_width=PROCESS_WIDTH, thread_width=THREAD_WIDTH, 
                 file_width=FILE_WIDTH, level_width=LEVEL_WIDTH, **kwargs):
        """Initialize with custom field widths."""
        super().__init__(fmt, datefmt, **kwargs)
        self.name_width = name_width
        self.process_width = process_width
        self.thread_width = thread_width
        self.file_width = file_width
        self.level_width = level_width
    
    def truncate_string(self, s, max_length):
        """Truncate a string to a maximum length with ellipsis if needed."""
        if len(s) <= max_length:
            return s.ljust(max_length)  # Use ljust to ensure consistent width
        
        # For shorter max lengths, use a simple truncation with '..'
        if max_length <= 10:
            return s[:max_length-2] + '..'
            
        # Show more of the start and less of the end for longer strings
        start_len = int(max_length * 0.7)
        end_len = max_length - start_len - 2  # Account for '..' 
        return s[:start_len] + '..' + s[-end_len:]
    
    def format(self, record):
        """Format the log record with colors and fixed-width fields."""
        # Save original format
        format_orig = self._style._fmt
        
        # Apply color to levelname - ensure the visible width is fixed
        if record.levelno in LEVEL_COLORS:
            color = LEVEL_COLORS[record.levelno]
            # Fix: Properly pad the record.levelname first, then add color codes
            levelname_padded = f"{record.levelname:{self.level_width}}"
            record.levelname_colored = f"{color}{levelname_padded}{COLORS['RESET']}"
        else:
            record.levelname_colored = f"{record.levelname:{self.level_width}}"
        
        # Apply color to logger name - truncate if too long
        name = record.name
        name = self.truncate_string(name, self.name_width)
        # Fix: Ensure proper padding of visible characters
        name_padded = f"{name:{self.name_width}}"
        record.name_colored = f"{COLORS['BLUE']}{name_padded}{COLORS['RESET']}"
        
        # Apply color to process info and ensure fixed width
        process_info = f"[{record.processName}{record.process}]"
        process_info = self.truncate_string(process_info, self.process_width)
        # Fix: Properly pad the process_info first, then add color codes
        process_info_padded = f"{process_info:{self.process_width}}"
        record.process_info_colored = f"{COLORS['MAGENTA']}{process_info_padded}{COLORS['RESET']}"
        
        # Apply color to thread info and ensure fixed width
        thread_info = f"[{record.threadName}{record.thread}]"
        thread_info = self.truncate_string(thread_info, self.thread_width)
        # Fix: Properly pad the thread_info first, then add color codes
        thread_info_padded = f"{thread_info:{self.thread_width}}"
        record.thread_info_colored = f"{COLORS['CYAN']}{thread_info_padded}{COLORS['RESET']}"
        
        # Apply color to file location and ensure fixed width
        file_info = f"{record.filename}:{record.lineno}"
        file_info = self.truncate_string(file_info, self.file_width)
        # Fix: Properly pad the file_info first, then add color codes
        file_info_padded = f"{file_info:{self.file_width}}"
        record.file_info_colored = f"{COLORS['GRAY']}{file_info_padded}{COLORS['RESET']}"
        
        # Get colored format
        result = logging.Formatter.format(self, record)
        
        # Restore original format
        self._style._fmt = format_orig
        
        return result

def calculate_field_widths():
    """Calculate appropriate field widths based on terminal size."""
    try:
        term_width = TERMINAL_WIDTH
        # Reserve space for separators and timestamp
        available_width = term_width - 30  # Timestamp + separators + message
        
        # Distribute available width
        if available_width >= 60:
            # For larger terminals, use defaults
            name_width = NAME_WIDTH
            process_width = PROCESS_WIDTH
            thread_width = THREAD_WIDTH
            file_width = FILE_WIDTH
            level_width = LEVEL_WIDTH
        else:
            # For smaller terminals, reduce widths proportionally
            proportion = max(0.5, available_width / 60.0)
            name_width = max(8, int(NAME_WIDTH * proportion))
            process_width = max(10, int(PROCESS_WIDTH * proportion))
            thread_width = max(10, int(THREAD_WIDTH * proportion))
            file_width = max(8, int(FILE_WIDTH * proportion))
            level_width = LEVEL_WIDTH  # Keep level width constant
            
        return name_width, process_width, thread_width, file_width, level_width
    except Exception:
        # Default values for fallback
        return NAME_WIDTH, PROCESS_WIDTH, THREAD_WIDTH, FILE_WIDTH, LEVEL_WIDTH

def get_processor_info() -> str:
    """Get processor information."""
    processor = platform.processor()
    if not processor:
        processor = platform.machine()
    return processor

def get_thread_info() -> str:
    """Get current thread name and ID."""
    thread = threading.current_thread()
    return f"{thread.name}-{thread.ident}"

def get_process_info() -> str:
    """Get current process name and ID."""
    process = multiprocessing.current_process()
    return f"{process.name}-{process.pid}"

def setup_logging_listener(log_level: int = logging.INFO, 
                           rotation_interval_minutes: Optional[int] = None, 
                           log_backup_count: int = 7) -> Tuple[QueueListener, Any]:
    """
    Set up a central logging queue and listener for multiprocessing-safe logging.
    This should be called ONCE from the main process before any child processes are spawned.
    
    Args:
        log_level: The logging level for the root logger
        rotation_interval_minutes: If provided, logs will be rotated at this interval
        log_backup_count: Number of rotated log files to keep
        
    Returns:
        A tuple of (QueueListener, Queue) that are now handling all logging 
    """
    global _log_queue, _queue_listener, _listener_configured
    
    if _listener_configured:
        return _queue_listener, _log_queue
    
    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    
    # Set file log format (plain, no colors)
    file_log_format = (
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "[%(processName)s-%(process)d] | "
        "[%(threadName)s-%(thread)d] | "
        "%(filename)s:%(lineno)d | "
        "%(message)s"
    )
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Create file handler for log files
    file_formatter = logging.Formatter(file_log_format, date_format)
    
    # Configure the file handler based on rotation parameters
    if rotation_interval_minutes and rotation_interval_minutes > 0:
        file_handler = TimedRotatingFileHandler(
            filename=os.path.join(logs_dir, "app.log"),
            when='m',  # 'm' for minutes
            interval=rotation_interval_minutes,
            backupCount=log_backup_count,
            encoding='utf-8',
            delay=False
        )
    else:
        file_handler = logging.FileHandler(os.path.join(logs_dir, "app.log"), encoding='utf-8')
    
    file_handler.setFormatter(file_formatter)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    
    # Calculate appropriate field widths for console output
    name_width, process_width, thread_width, file_width, level_width = calculate_field_widths()
    
    # Configure console handler based on TTY environment
    is_tty = sys.stdout.isatty()
    if is_tty:
        # Set colored log format with fixed-width fields for terminal
        log_format = "%(asctime)s | %(levelname_colored)s | %(name_colored)s | %(process_info_colored)s | %(thread_info_colored)s | %(file_info_colored)s | %(message)s"
        date_format = '%Y-%m-%d %H:%M:%S'
        
        formatter = FixedWidthColoredFormatter(
            log_format, 
            date_format,
            name_width=name_width,
            process_width=process_width,
            thread_width=thread_width,
            file_width=file_width,
            level_width=level_width
        )
    else:
        # Set plain log format with fixed-width fields for non-terminals
        log_format = (
            "%(asctime)s | "
            f"%(levelname)-{level_width}s | "
            f"%(name)-{name_width}s | "
            f"[%(processName)s-%(process)d] | "
            f"[%(threadName)s-%(thread)d] | "
            f"%(filename)s:%(lineno)d | "
            "%(message)s"
        )
        formatter = logging.Formatter(log_format, date_format)
    
    console_handler.setFormatter(formatter)
    
    # Set up the queue
    _log_queue = multiprocessing.Queue(-1)  # No limit on queue size
    
    # Set up and start the listener with handlers
    _queue_listener = QueueListener(_log_queue, file_handler, console_handler, respect_handler_level=True)
    _queue_listener.start()
    
    # Configure the root logger with a queue handler
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)  # Set root logger level
    
    # Register to stop the listener at exit
    atexit.register(stop_logging_listener)
    
    _listener_configured = True
    return _queue_listener, _log_queue

def stop_logging_listener():
    """
    Stop the logging queue listener. This should be called when shutting down the application.
    It will be automatically called at exit via atexit registration in setup_logging_listener.
    """
    global _queue_listener, _listener_configured
    
    if _queue_listener is not None:
        _queue_listener.stop()
        _queue_listener = None
        _listener_configured = False

def get_logger(name: str, log_level: Optional[int] = None, rotation_interval_minutes: Optional[int] = None, log_backup_count: int = 7) -> logging.Logger:
    """
    Get a configured logger with colored output, fixed-width fields, and additional information.
    In a multi-process environment, this sets up queue-based logging where only the main process
    handles actual file I/O.
    
    Args:
        name: Name of the logger
        log_level: Optional log level to set (defaults to INFO)
        rotation_interval_minutes: Optional interval in minutes for log rotation
        log_backup_count: Number of backup log files to keep
    
    Returns:
        Configured logger instance
    """
    global _log_queue, _queue_listener, _listener_configured
    
    log_level = log_level if log_level is not None else logging.INFO
    
    # Set up the queue listener if not already configured
    if not _listener_configured:
        setup_logging_listener(log_level, rotation_interval_minutes, log_backup_count)
    
    # Get the logger for this module
    logger = logging.getLogger(name)
    
    # Remove any existing handlers to avoid duplicates
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    
    # Add a queue handler to this logger
    queue_handler = QueueHandler(_log_queue)
    logger.addHandler(queue_handler)
    
    # Set log level for this specific logger
    logger.setLevel(log_level)
    
    # Ensure propagation is enabled to use the QueueHandler
    logger.propagate = False  # Don't propagate to parent loggers since we're using a queue
    
    return logger