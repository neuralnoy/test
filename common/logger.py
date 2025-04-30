import logging
import os
import threading
import multiprocessing
import platform
import sys
import shutil
from typing import Optional

# Get terminal width, default to 80 if not available
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

def get_logger(name: str, log_level: Optional[int] = None) -> logging.Logger:
    """
    Get a configured logger with colored output, fixed-width fields, and additional information.
    Also saves logs to a file in the logs directory at the root of the project.
    
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
        
        # Create file handler
        file_handler = logging.FileHandler(os.path.join(logs_dir, "app.log"))
        file_formatter = logging.Formatter(file_log_format, date_format)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    
    # Get the logger for this module
    logger = logging.getLogger(name)
    
    # Only configure console handler if it hasn't been configured yet
    if not logger.handlers:
        # Create console handler
        console_handler = logging.StreamHandler()
        
        # Calculate appropriate field widths
        name_width, process_width, thread_width, file_width, level_width = calculate_field_widths()
        
        # Check if running in a tty environment
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
                f"[%(processName)s-%(process)d] | "  # Remove unnecessary padding and use consistent separator
                f"[%(threadName)s-%(thread)d] | "    # Remove unnecessary padding and use consistent separator
                f"%(filename)s:%(lineno)d | "        # Remove unnecessary padding and use consistent separator
                "%(message)s"
            )
            date_format = '%Y-%m-%d %H:%M:%S'
            
            formatter = logging.Formatter(log_format, date_format)
            
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # Set log level
        logger.setLevel(log_level)
    
    return logger
