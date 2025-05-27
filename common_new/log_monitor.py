"""
Log file monitoring service that detects rotated log files and uploads them to Azure Blob Storage.
Singleton pattern ensures only one process handles monitoring across multiple workers.
"""
import os
import asyncio
import time
import json
import tempfile
from pathlib import Path
from typing import Optional, Set, List, Tuple
from datetime import datetime

from common_new.logger import get_logger
from common_new.blob_storage import AsyncBlobStorageUploader

logger = get_logger("log_monitor")

class LogMonitorService:
    """
    Singleton service that periodically scans for rotated log files and uploads them to Azure Blob Storage.
    Uses file-based locking to ensure only one process is active across multiple workers.
    """
    
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls, *args, **kwargs):
        # Singleton pattern within process
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(
        self, 
        logs_dir: str,
        account_name: Optional[str] = None,
        account_url: Optional[str] = None,
        container_name: str = "application-logs",
        app_name: Optional[str] = None,
        retention_days: int = 30,
        scan_interval: int = 60
    ):
        # Only initialize once per process
        if self._initialized:
            return
            
        self.logs_dir = logs_dir
        
        # Determine the account URL
        if account_url:
            self.account_url = account_url
        elif account_name:
            self.account_url = f"https://{account_name}.blob.core.windows.net"
        else:
            self.account_url = None
            
        self.container_name = container_name
        self.app_name = app_name or "unknown_app"
        self.retention_days = retention_days
        self.scan_interval = scan_interval
        
        # Inter-process coordination
        self._lock_file_path = os.path.join(
            tempfile.gettempdir(), 
            f"log_monitor_{self.app_name}.lock"
        )
        
        # State
        self.uploader = None
        self._monitor_task = None
        self._running = False
        self._is_leader = False
        self._lock_file = None
        self._processed_files: Set[str] = set()  # Only track successes to avoid duplicates
        
        self._initialized = True
        
    async def initialize(self) -> bool:
        """
        Initialize the log monitor service. Only one process becomes the leader.
        """
        async with self._lock:
            if self._running:
                return True
                
            # Try to acquire leadership
            if await self._try_acquire_leadership():
                self._is_leader = True
                logger.info(f"Process {os.getpid()} became log monitor leader for {self.app_name}")
                
                # Initialize blob storage if configured
                if not self.account_url:
                    logger.warning("Azure Blob Storage account URL not provided - log upload is disabled")
                    return True
                    
                # Create the uploader
                self.uploader = AsyncBlobStorageUploader(
                    account_url=self.account_url,
                    container_name=self.container_name
                )
                
                # Initialize the uploader
                success = await self.uploader.initialize()
                if not success:
                    logger.error("Failed to initialize blob storage uploader")
                    await self._release_leadership()
                    return False
                
                # Create logs directory if it doesn't exist
                Path(self.logs_dir).mkdir(parents=True, exist_ok=True)
                
                # Start the monitoring task
                self._running = True
                self._monitor_task = asyncio.create_task(self._monitor_loop())
                
                logger.info(f"Singleton log monitor initialized - scanning {self.logs_dir} every {self.scan_interval}s")
                return True
            else:
                logger.info(f"Process {os.getpid()} - another process is handling log monitoring")
                return True  # Not an error, just not the leader
    
    async def _try_acquire_leadership(self) -> bool:
        """Try to acquire the inter-process lock to become the leader."""
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
            
            return True
            
        except (OSError, IOError):
            # Lock is held by another process
            if self._lock_file:
                self._lock_file.close()
                self._lock_file = None
            return False
    
    async def _release_leadership(self):
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
                    
            except Exception as e:
                logger.warning(f"Error releasing lock: {e}")
            finally:
                self._lock_file = None
                self._is_leader = False
    
    async def _monitor_loop(self) -> None:
        """Background task that periodically scans for rotated log files."""
        logger.info("Starting singleton log file monitor loop")
        
        while self._running:
            try:
                if self._is_leader:
                    await self._scan_for_rotated_logs()
                else:
                    # Lost leadership, try to reacquire
                    if await self._try_acquire_leadership():
                        self._is_leader = True
                        logger.info("Reacquired log monitor leadership")
                
                await asyncio.sleep(self.scan_interval)
                
            except asyncio.CancelledError:
                logger.info("Singleton log monitor task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in singleton monitor loop: {str(e)}")
                await asyncio.sleep(5)
    
    async def _scan_for_rotated_logs(self) -> None:
        """Scan for and upload rotated log files. Simplified - no memory tracking of failures."""
        try:
            if not self.uploader:
                return
                
            now = time.time()
            log_files: List[Tuple[str, float]] = []
            
            logger.debug(f"Scanning {self.logs_dir} for rotated log files")
            
            if not os.path.exists(self.logs_dir):
                logger.warning(f"Logs directory {self.logs_dir} does not exist")
                return
                
            # Scan for rotated log files
            for filename in os.listdir(self.logs_dir):
                if "_" in filename and filename.endswith(".log") and not filename.endswith(".current.log"):
                    file_path = os.path.join(self.logs_dir, filename)
                    
                    # Skip already processed files (only tracking successes)
                    if file_path in self._processed_files:
                        continue
                        
                    # Check if file is ready for processing
                    try:
                        stats = os.stat(file_path)
                        # Skip files being written to (modified in the last 30 seconds)
                        if now - stats.st_mtime < 30:
                            logger.debug(f"Skipping {file_path} - recently modified")
                            continue
                            
                        log_files.append((file_path, stats.st_mtime))
                    except Exception as e:
                        logger.error(f"Error checking file {file_path}: {str(e)}")
            
            if not log_files:
                logger.debug("No new rotated log files found")
                return
                
            # Sort by modification time (oldest first)
            log_files.sort(key=lambda x: x[1])
            
            logger.info(f"Found {len(log_files)} rotated log files to process")
            
            # Process files - simplified logic
            for file_path, _ in log_files:
                logger.info(f"Processing rotated log file: {file_path}")
                try:
                    await self.uploader.upload_file(file_path, app_name=self.app_name)
                    self._processed_files.add(file_path)  # Only track successes
                    logger.info(f"Successfully processed {file_path}")
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {str(e)}")
                    # Don't store failures - let them be rediscovered on next scan
                    # File content is already freed from memory automatically
                    
        except Exception as e:
            logger.error(f"Error scanning for rotated logs: {str(e)}")
            
    async def shutdown(self) -> None:
        """Gracefully shut down the singleton log monitor service."""
        async with self._lock:
            if not self._running:
                return
                
            logger.info("Shutting down singleton log monitor service")
            
            # Stop the monitor loop
            self._running = False
            
            # Cancel the monitor task
            if self._monitor_task and not self._monitor_task.done():
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass
                
            # Do a final scan if we're the leader
            if self._is_leader and self.uploader:
                logger.info("Running final log scan before shutdown")
                await self._scan_for_rotated_logs()
                
            # Shut down the uploader
            if self.uploader:
                await self.uploader.shutdown()
                
            # Release leadership
            await self._release_leadership()
                
            logger.info("Singleton log monitor service shut down") 