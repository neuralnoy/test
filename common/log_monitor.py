"""
Log file monitoring service that detects rotated log files and uploads them to Azure Blob Storage.
"""
import os
import asyncio
import time
from pathlib import Path
from typing import Optional, Set, Dict, List, Tuple
from datetime import datetime

from common.logger import get_logger
from common.blob_storage import AsyncBlobStorageUploader

logger = get_logger("log_monitor")

class LogMonitorService:
    """
    Service that periodically scans for rotated log files and uploads them to Azure Blob Storage.
    Designed to work with TimedRotatingFileHandler from the logging module.
    """
    def __init__(
        self, 
        logs_dir: str,
        account_name: Optional[str] = None,
        account_url: Optional[str] = None,
        container_name: str = "application-logs",
        retention_days: int = 30,
        scan_interval: int = 60  # Scan every 60 seconds
    ):
        """
        Initialize the log monitor service.
        
        Args:
            logs_dir: Directory containing log files to monitor
            account_name: Azure Storage account name (will construct URL as https://{account_name}.blob.core.windows.net)
            account_url: Azure Storage account URL (will be used if provided, otherwise constructed from account_name)
            container_name: Name of the container to store logs
            retention_days: Number of days to retain logs in blob storage
            scan_interval: How often to scan for new log files (in seconds)
        """
        self.logs_dir = logs_dir
        
        # Determine the account URL - either use the provided URL or construct from account name
        if account_url:
            self.account_url = account_url
        elif account_name:
            self.account_url = f"https://{account_name}.blob.core.windows.net"
        else:
            self.account_url = None
            
        self.container_name = container_name
        self.retention_days = retention_days
        self.scan_interval = scan_interval
        self.uploader = None
        self._monitor_task = None
        self._processed_files: Set[str] = set()
        self._last_scan_time = 0
        self._running = False
        
    async def initialize(self) -> bool:
        """
        Initialize the log monitor service and start background scanning.
        
        Returns:
            bool: True if initialized successfully, False otherwise
        """
        # Create the blob storage uploader if account URL is provided
        if not self.account_url:
            logger.warning("Azure Blob Storage account URL not provided - log upload is disabled")
            return False
            
        # Create the uploader
        self.uploader = AsyncBlobStorageUploader(
            account_url=self.account_url,
            container_name=self.container_name,
            retention_days=self.retention_days
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
        
        logger.info(f"Log monitor service initialized - scanning {self.logs_dir} every {self.scan_interval}s")
        return True
    
    async def _monitor_loop(self) -> None:
        """Background task that periodically scans for rotated log files."""
        try:
            logger.info("Starting log file monitor loop")
            
            # Do an initial scan
            await self._scan_for_rotated_logs()
            
            # Then scan periodically
            while self._running:
                # Wait for the scan interval
                await asyncio.sleep(self.scan_interval)
                
                # Scan for rotated logs
                await self._scan_for_rotated_logs()
                
        except asyncio.CancelledError:
            logger.info("Log monitor task cancelled")
        except Exception as e:
            logger.error(f"Error in log monitor loop: {str(e)}")
            
    async def _scan_for_rotated_logs(self) -> None:
        """Scan for and upload rotated log files."""
        try:
            now = time.time()
            self._last_scan_time = now
            
            # Build a list of log files to process
            log_files: List[Tuple[str, float]] = []
            
            logger.debug(f"Scanning {self.logs_dir} for rotated log files")
            
            # Scan the logs directory
            if not os.path.exists(self.logs_dir):
                logger.warning(f"Logs directory {self.logs_dir} does not exist")
                return
                
            for filename in os.listdir(self.logs_dir):
                # Only process rotated log files (with a date suffix after .log)
                # This matches the TimedRotatingFileHandler pattern we're using in logger.py
                if ".log." in filename:
                    file_path = os.path.join(self.logs_dir, filename)
                    
                    # Skip already processed files
                    if file_path in self._processed_files:
                        continue
                        
                    # Get file stats
                    try:
                        stats = os.stat(file_path)
                        # Skip files being written to (modified in the last 10 seconds)
                        if now - stats.st_mtime < 10:
                            logger.debug(f"Skipping {file_path} - recently modified")
                            continue
                            
                        log_files.append((file_path, stats.st_mtime))
                    except Exception as e:
                        logger.error(f"Error checking file {file_path}: {str(e)}")
            
            # If no files found, we're done
            if not log_files:
                logger.debug("No new rotated log files found")
                return
                
            # Sort by modification time (oldest first)
            log_files.sort(key=lambda x: x[1])
            
            logger.info(f"Found {len(log_files)} rotated log files to process")
            
            # Process files
            for file_path, _ in log_files:
                logger.info(f"Processing rotated log file: {file_path}")
                try:
                    await self.uploader.upload_file(file_path)
                    self._processed_files.add(file_path)
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error scanning for rotated logs: {str(e)}")
            
    async def shutdown(self) -> None:
        """Gracefully shut down the log monitor service."""
        logger.info("Shutting down log monitor service")
        
        # Stop the monitor loop
        self._running = False
        
        # Cancel the monitor task
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            
        # Do a final scan before shutting down
        if self.uploader and self.uploader._initialized:
            logger.info("Running final log scan before shutdown")
            await self._scan_for_rotated_logs()
            
        # Shut down the uploader
        if self.uploader:
            await self.uploader.shutdown()
            
        logger.info("Log monitor service shut down") 