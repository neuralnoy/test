import logging
import os
import sys
import time
import json
import tempfile
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

class _SingletonFileLogService:
    """
    Internal singleton service that ensures only one process handles file rotation
    across multiple workers, while allowing all workers to write to the log file.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        # Only initialize once per process
        if self._initialized:
            return
            
        self.app_name = get_app_name()
        self.logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        
        # Inter-process coordination
        self._lock_file_path = os.path.join(
            tempfile.gettempdir(), 
            f"logger_{self.app_name}.lock"
        )
        
        # State
        self._is_leader = False
        self._lock_file = None
        self._file_handler = None
        self._initialized = True
        
    def _try_acquire_leadership(self) -> bool:
        """Try to acquire the inter-process lock to become the logging leader."""
        try:
            # Try to open the lock file exclusively
            self._lock_file = open(self._lock_file_path, 'w')
            
            # Try to acquire an exclusive, non-blocking lock (Windows compatible)
            try:
                import msvcrt
                msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            except ImportError:
                # Unix/Linux systems
                import fcntl
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            # Write our process info to the lock file
            lock_info = {
                "pid": os.getpid(),
                "timestamp": time.time(),
                "app_name": self.app_name
            }
            self._lock_file.write(json.dumps(lock_info))
            self._lock_file.flush()
            
            self._is_leader = True
            return True
            
        except (OSError, IOError):
            # Lock is held by another process
            if self._lock_file:
                self._lock_file.close()
                self._lock_file = None
            return False
    
    def _create_simple_file_handler(self, formatter: logging.Formatter) -> Optional[logging.Handler]:
        """Create a simple file handler for non-leader processes."""
        try:
            # Create logs directory
            os.makedirs(self.logs_dir, exist_ok=True)
            
            # Use the same file path as the leader
            file_path = os.path.join(self.logs_dir, f"{self.app_name}.current.log")
            
            # Create a simple FileHandler (no rotation)
            file_handler = logging.FileHandler(
                filename=file_path,
                mode='a',  # Append mode
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            
            return file_handler
            
        except Exception:
            # If file handler creation fails, return None
            return None
    
    def _create_rotating_file_handler(self, formatter: logging.Formatter) -> Optional[logging.Handler]:
        """Create a rotating file handler for the leader process."""
        try:
            # Create logs directory
            os.makedirs(self.logs_dir, exist_ok=True)
            
            # Create rotating file handler with daily rotation
            file_path = os.path.join(self.logs_dir, f"{self.app_name}.current.log")
            file_handler = TimedRotatingFileHandler(
                filename=file_path,
                when='midnight',
                interval=1,
                backupCount=30,  # Keep logs for 30 days
            )
            
            # Set custom naming pattern for rotated files
            file_handler.namer = lambda name: f"{name.split('.')[0]}_{name.split('.')[-1]}.log"
            file_handler.setFormatter(formatter)
            
            return file_handler
            
        except Exception:
            # If file handler creation fails, release leadership
            self._release_leadership()
            return None
    
    def get_file_handler(self, formatter: logging.Formatter) -> Optional[logging.Handler]:
        """Get the appropriate file handler for this process."""
        if self._file_handler:
            return self._file_handler
            
        # Try to acquire leadership first
        if not self._is_leader:
            self._try_acquire_leadership()
        
        if self._is_leader:
            # Leader gets rotating file handler
            self._file_handler = self._create_rotating_file_handler(formatter)
            return self._file_handler
        else:
            # Non-leader gets simple file handler
            self._file_handler = self._create_simple_file_handler(formatter)
            return self._file_handler
    
    def _release_leadership(self):
        """Release the inter-process lock."""
        if self._lock_file:
            try:
                # Release the lock
                try:
                    import msvcrt
                    msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                except ImportError:
                    import fcntl
                    fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                
                self._lock_file.close()
                
                # Clean up the lock file
                if os.path.exists(self._lock_file_path):
                    os.unlink(self._lock_file_path)
                    
            except Exception:
                pass  # Ignore cleanup errors
            finally:
                self._lock_file = None
                self._is_leader = False
    
    def shutdown(self):
        """Shutdown the logging service and release resources."""
        if self._file_handler:
            self._file_handler.close()
            self._file_handler = None
        self._release_leadership()

# Global singleton instance
_log_service = _SingletonFileLogService()

def get_logger(name: str, log_level: Optional[int] = None) -> logging.Logger:
    """
    Get a configured logger with console and file output.
    All processes can write to the log file, but only the leader handles rotation.
    
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
    
    # Create console handler (all processes get this)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Configure root logger for file logging if not already configured
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        try:
            # All processes get a file handler (leader gets rotating, non-leaders get simple)
            file_handler = _log_service.get_file_handler(formatter)
            
            if file_handler:
                root_logger.addHandler(file_handler)
                pid = os.getpid()
                if _log_service._is_leader:
                    logger.info(f"Process {pid} became logging leader (handles rotation) for {_log_service.app_name}")
                else:
                    logger.info(f"Process {pid} is non-leader (writes to file, no rotation) for {_log_service.app_name}")
            else:
                logger.warning(f"Process {os.getpid()} could not create file handler - console logging only")
                
            root_logger.setLevel(log_level)
            
            # Log a warning if using unknown_app
            if _log_service.app_name == 'unknown_app':
                logger.warning("APP_NAME environment variable not set. Using 'unknown_app' as fallback.")
                
        except Exception as e:
            logger.error(f"Failed to configure file logging: {str(e)}")
            # Continue with console logging only
    
    return logger

def shutdown_logging():
    """Shutdown the singleton logging service and release resources."""
    global _log_service
    if _log_service:
        _log_service.shutdown()