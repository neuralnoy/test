"""
Log file monitoring service that detects rotated log files and uploads them to Azure Blob Storage.
Each process monitors its own log files independently and cleans up orphaned files from dead processes.
"""
import os
import asyncio
import time
import psutil
from pathlib import Path
from typing import Optional, Set, List, Tuple

from common_new.logger import get_logger, get_app_name
from common_new.blob_storage import AsyncBlobStorageUploader

logger = get_logger("common")

class LogMonitorService:
    """
    Service that periodically scans for rotated log files and uploads them to Azure Blob Storage.
    Each process instance monitors its own log files independently and also cleans up orphaned files.
    """
    
    def __init__(
        self, 
        logs_dir: str,
        account_name: Optional[str] = None,
        account_url: Optional[str] = None,
        container_name: str = "fla-logs",
        app_name: Optional[str] = None,
        process_name: Optional[str] = None,
        scan_interval: int = 60,
        enable_orphan_cleanup: bool = True,
        delete_after_upload: bool = True
    ):
        self.logs_dir = logs_dir
        
        # Determine the account URL
        if account_url:
            self.account_url = account_url
        elif account_name:
            self.account_url = f"https://{account_name}.blob.core.windows.net"
        else:
            self.account_url = None
            
        self.container_name = container_name
        self.app_name = app_name or get_app_name()
        self.process_name = process_name or os.getenv('PROCESS_NAME', f"worker-{os.getpid()}")
        self.scan_interval = scan_interval
        self.enable_orphan_cleanup = enable_orphan_cleanup
        self.delete_after_upload = delete_after_upload
        
        # State
        self.uploader = None
        self._monitor_task = None
        self._running = False
        self._processed_files: Set[str] = set()  # Track successfully processed files
        
    async def initialize(self) -> bool:
        """
        Initialize the log monitor service for this process.
        """
        if self._running:
            return True
            
        logger.info(f"Process {os.getpid()} ({self.process_name}) initializing log monitor (orphan_cleanup={self.enable_orphan_cleanup})")
        
        # Initialize blob storage if configured
        if not self.account_url:
            logger.warning("Azure Blob Storage account URL not provided - log upload is disabled")
            return True
            
        # Create the uploader
        self.uploader = AsyncBlobStorageUploader(
            account_url=self.account_url,
            container_name=self.container_name,
            delete_after_upload=self.delete_after_upload
        )
        
        # Initialize the uploader
        success = await self.uploader.initialize()
        if not success:
            logger.error("Failed to initialize blob storage uploader")
            return False
        
        # Create logs directory if it doesn't exist
        Path(self.logs_dir).mkdir(parents=True, exist_ok=True)
        
        # Start the monitoring task
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info(f"Log monitor initialized for {self.process_name} - scanning {self.logs_dir} every {self.scan_interval}s")
        return True
    
    def _is_process_alive(self, pid: int) -> bool:
        """Check if a process with given PID is still running."""
        try:
            return psutil.pid_exists(pid)
        except Exception:
            # If psutil fails, assume process is dead to be safe
            return False
    
    def _extract_pid_from_process_name(self, process_name: str) -> Optional[int]:
        """Extract PID from process name if it follows worker-{pid} pattern."""
        try:
            if process_name.startswith("worker-"):
                pid_str = process_name.replace("worker-", "")
                return int(pid_str)
            return None
        except (ValueError, AttributeError):
            return None
    
    async def _monitor_loop(self) -> None:
        """Background task that periodically scans for rotated log files."""
        logger.info(f"Starting log file monitor loop for {self.process_name}")
        
        while self._running:
            try:
                await self._scan_for_rotated_logs()
                await asyncio.sleep(self.scan_interval)
                
            except asyncio.CancelledError:
                logger.info(f"Log monitor task cancelled for {self.process_name}")
                break
            except Exception as e:
                logger.error(f"Error in monitor loop for {self.process_name}: {str(e)}")
                await asyncio.sleep(5)
    
    async def _scan_for_rotated_logs(self) -> None:
        """Scan for and upload rotated log files for this process only."""
        try:
            if not self.uploader:
                return
                
            now = time.time()
            log_files: List[Tuple[str, float]] = []
            
            logger.debug(f"Scanning {self.logs_dir} for rotated log files from {self.process_name}")
            
            if not os.path.exists(self.logs_dir):
                logger.warning(f"Logs directory {self.logs_dir} does not exist")
                return
                
            # Pattern to match this process's rotated log files
            # Example: myapp-worker-123__2024-01-15.log
            process_log_prefix = f"{self.app_name}-{self.process_name}__"
            current_log_name = f"{self.app_name}-{self.process_name}.current.log"
            
            # Scan for rotated log files belonging to this process
            for filename in os.listdir(self.logs_dir):
                if (filename.startswith(process_log_prefix) and 
                    filename.endswith(".log") and 
                    "__" in filename and 
                    filename != current_log_name):  # Skip current log file
                    
                    file_path = os.path.join(self.logs_dir, filename)
                    
                    # Skip already processed files
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

            # Also scan for orphaned files from dead processes
            if self.enable_orphan_cleanup:
                orphan_files = await self._scan_for_orphaned_logs(now)
                if orphan_files:  # Safety check to ensure it's not None
                    log_files.extend(orphan_files)
            
            if not log_files:
                logger.debug(f"No new rotated log files found for {self.process_name}")
                return
                
            # Sort by modification time (oldest first)
            log_files.sort(key=lambda x: x[1])
            
            logger.info(f"Found {len(log_files)} rotated log files to process for {self.process_name}")
            
            # Process files
            for file_path, _ in log_files:
                logger.info(f"Processing rotated log file: {file_path}")
                try:
                    await self.uploader.upload_file(file_path, app_name=self.app_name)
                    self._processed_files.add(file_path)
                    logger.info(f"Successfully processed {file_path}")
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error scanning for rotated logs in {self.process_name}: {str(e)}")
            
    async def _scan_for_orphaned_logs(self, now: float) -> List[Tuple[str, float]]:
        """Scan for orphaned log files from dead processes and return them for upload."""
        orphan_files: List[Tuple[str, float]] = []
        
        try:
            logger.debug(f"Scanning for orphaned log files from dead processes")
            
            app_prefix = f"{self.app_name}-"
            
            for filename in os.listdir(self.logs_dir):
                # Look for files from this app but different processes
                if (filename.startswith(app_prefix) and 
                    filename.endswith(".log")):
                    
                    # Skip our own files
                    if (filename.startswith(f"{self.app_name}-{self.process_name}__") or 
                        filename == f"{self.app_name}-{self.process_name}.current.log"):
                        continue
                    
                    file_path = os.path.join(self.logs_dir, filename)
                    
                    # Skip already processed files
                    if file_path in self._processed_files:
                        continue
                    
                    # Determine file type and extract process name
                    is_current_log = filename.endswith(".current.log")
                    is_rotated_log = "__" in filename and not filename.endswith(".current.log")
                    
                    if not (is_current_log or is_rotated_log):
                        continue  # Unknown file type
                    
                    # Extract process name from filename
                    if is_current_log:
                        # Format: app-process.current.log
                        base_name = filename.replace(f"{self.app_name}-", "").replace(".current.log", "")
                        other_process_name = base_name
                    elif is_rotated_log:
                        # Format: app-process__date.log
                        base_name = filename.replace(f"{self.app_name}-", "").split("__")[0]
                        other_process_name = base_name
                    else:
                        continue
                    
                    # For current log files, check if the process is still alive
                    if is_current_log:
                        pid = self._extract_pid_from_process_name(other_process_name)
                        if pid and self._is_process_alive(pid):
                            continue  # Process is alive, skip its current log
                        
                        # Process is dead, but current log might still be rotated later
                        # Check if it's old enough to be considered orphaned
                        try:
                            stats = os.stat(file_path)
                            # Only consider current logs orphaned if not modified for 10 minutes
                            if now - stats.st_mtime < 600:  # 10 minutes
                                continue
                        except Exception:
                            continue
                    
                    # Check if file is ready for processing
                    try:
                        stats = os.stat(file_path)
                        # Skip files being written to (modified in the last 60 seconds for orphans)
                        if now - stats.st_mtime < 60:
                            continue
                            
                        orphan_files.append((file_path, stats.st_mtime))
                        logger.info(f"Found orphaned log file: {filename} (from process {other_process_name})")
                        
                    except Exception as e:
                        logger.error(f"Error checking orphaned file {file_path}: {str(e)}")
                        
        except Exception as e:
            logger.error(f"Error scanning for orphaned logs: {str(e)}")
            
        if orphan_files:
            logger.info(f"Found {len(orphan_files)} orphaned log files to upload")
            
        return orphan_files
            
    async def shutdown(self) -> None:
        """Gracefully shut down the log monitor service."""
        if not self._running:
            return
            
        logger.info(f"Shutting down log monitor service for {self.process_name}")
        
        # Stop the monitor loop
        self._running = False
        
        # Cancel the monitor task
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            
        # Do a final scan
        if self.uploader:
            logger.info(f"Running final log scan before shutdown for {self.process_name}")
            await self._scan_for_rotated_logs()
            
        # Shut down the uploader
        if self.uploader:
            await self.uploader.shutdown()
            
        logger.info(f"Log monitor service shut down for {self.process_name}") 