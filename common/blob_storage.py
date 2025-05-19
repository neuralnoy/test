"""
Asynchronous Azure Blob Storage client for uploading files.
"""
import os
import asyncio
from typing import Optional, Set
from datetime import datetime, timedelta
from azure.storage.blob.aio import BlobServiceClient
from azure.identity.aio import DefaultAzureCredential
from common.logger import get_logger

logger = get_logger("blob_storage")

class AsyncBlobStorageUploader:
    """
    Asynchronous handler for uploading files to Azure Blob Storage.
    Uses Azure Identity for authentication with DefaultAzureCredential.
    """
    def __init__(
        self,
        account_url: str,
        container_name: str,
        retention_days: Optional[int] = 30
    ):
        """
        Initialize the Azure Blob Storage uploader.
        
        Args:
            account_url: Azure Storage account URL (e.g., https://accountname.blob.core.windows.net)
            container_name: Name of the container to store uploaded files
            retention_days: Optional number of days to retain files before expiry (30 by default)
        """
        self.account_url = account_url
        self.container_name = container_name
        self.retention_days = retention_days
        self._initialized = False
        self._upload_queue = asyncio.Queue()
        self._upload_task = None
        self._processed_files: Set[str] = set()
        
    async def initialize(self) -> bool:
        """
        Initialize the uploader and start background task.
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        if self._initialized:
            return True
            
        logger.info(f"Initializing Blob Storage Uploader with container {self.container_name}")
        
        # Verify we can connect to Azure Blob Storage
        try:
            credential = DefaultAzureCredential()
            blob_service_client = BlobServiceClient(
                account_url=self.account_url,
                credential=credential
            )
            
            # Test connection by listing containers
            async with blob_service_client:
                containers = []
                async for container in blob_service_client.list_containers(name_starts_with=self.container_name):
                    containers.append(container["name"])
                
                if self.container_name not in containers:
                    logger.info(f"Container {self.container_name} not found, will be created when needed")
            
            # Create and start the upload worker task
            self._upload_task = asyncio.create_task(self._upload_worker())
            self._initialized = True
            logger.info(f"Blob Storage Uploader initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Blob Storage Uploader: {str(e)}")
            return False
        
    async def upload_file(self, file_path: str, blob_name: Optional[str] = None) -> None:
        """
        Queue a file for upload to Azure Blob Storage.
        
        Args:
            file_path: Path to the file to upload
            blob_name: Name of the blob in the container (defaults to file basename)
        """
        if not self._initialized:
            success = await self.initialize()
            if not success:
                logger.error(f"Failed to initialize uploader, cannot upload {file_path}")
                return
            
        if not blob_name:
            blob_name = os.path.basename(file_path)
            
        # Check if file exists
        if not os.path.exists(file_path):
            logger.error(f"File {file_path} does not exist, cannot upload")
            return
            
        # Check if already processed
        if file_path in self._processed_files:
            logger.info(f"File {file_path} already processed, skipping")
            return
            
        # Queue the file for upload
        await self._upload_queue.put((file_path, blob_name))
        logger.debug(f"Queued {file_path} for upload as {blob_name}")
        
    async def _upload_worker(self) -> None:
        """Background task to process uploads from the queue."""
        logger.info("Starting blob storage upload worker")
        while True:
            try:
                # Get the next file to upload
                file_path, blob_name = await self._upload_queue.get()
                
                try:
                    # Upload the file
                    success = await self._upload_file_to_blob(file_path, blob_name)
                    
                    if success:
                        logger.info(f"Successfully uploaded {file_path} to blob storage")
                        self._processed_files.add(file_path)
                    else:
                        logger.error(f"Failed to upload {file_path}")
                        
                except Exception as e:
                    logger.error(f"Error in upload worker: {str(e)}")
                finally:
                    # Mark the task as done
                    self._upload_queue.task_done()
                    
            except asyncio.CancelledError:
                logger.info("Upload worker task cancelled")
                break
                
            except Exception as e:
                logger.error(f"Error in upload worker loop: {str(e)}")
                # Prevent tight loop in case of recurring errors
                await asyncio.sleep(5)
                
        logger.info("Upload worker stopped")
                
    async def _upload_file_to_blob(self, file_path: str, blob_name: str) -> bool:
        """
        Upload a file to Azure Blob Storage.
        
        Args:
            file_path: Path to the file to upload
            blob_name: Name of the blob in the container
            
        Returns:
            bool: True if upload was successful, False otherwise
        """
        if not os.path.exists(file_path):
            logger.error(f"File {file_path} does not exist, cannot upload")
            return False
            
        try:
            # Create credentials and client
            credential = DefaultAzureCredential()
            blob_service_client = BlobServiceClient(
                account_url=self.account_url,
                credential=credential
            )
            
            try:
                # Get the container client
                container_client = blob_service_client.get_container_client(self.container_name)
                
                # Create container if it doesn't exist
                try:
                    await container_client.create_container()
                    logger.info(f"Created container {self.container_name}")
                except Exception:
                    # Container might already exist (409 error)
                    pass
                
                # Get the blob client
                blob_client = container_client.get_blob_client(blob_name)
                
                # Set expiration time if retention_days is specified
                headers = {}
                if self.retention_days:
                    expiry = datetime.utcnow() + timedelta(days=self.retention_days)
                    headers["x-ms-expiry-time"] = expiry.strftime("%a, %d %b %Y %H:%M:%S GMT")
                
                # Upload the file
                file_size = os.path.getsize(file_path)
                logger.info(f"Uploading {file_path} ({file_size} bytes) to blob storage as {blob_name}")
                
                async with open(file_path, "rb") as data:
                    await blob_client.upload_blob(
                        data, 
                        overwrite=True,
                        headers=headers
                    )
                
                return True
                
            finally:
                # Clean up resources
                await blob_service_client.close()
                await credential.close()
                
        except Exception as e:
            logger.error(f"Error uploading {file_path} to blob storage: {str(e)}")
            return False
            
    async def shutdown(self) -> None:
        """Gracefully shut down the uploader and wait for pending uploads to complete."""
        if not self._initialized:
            logger.info("Blob storage uploader not initialized, nothing to shut down")
            return
            
        logger.info("Shutting down blob storage uploader")
        
        # Wait for all queued uploads to complete
        if self._upload_queue.qsize() > 0:
            queue_size = self._upload_queue.qsize()
            logger.info(f"Waiting for {queue_size} uploads to complete")
            try:
                await asyncio.wait_for(self._upload_queue.join(), timeout=60.0)
                logger.info("All pending uploads completed")
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for uploads to complete")
            
        # Cancel the upload task
        if self._upload_task and not self._upload_task.done():
            self._upload_task.cancel()
            try:
                await self._upload_task
            except asyncio.CancelledError:
                pass
                
        self._initialized = False
        logger.info("Blob storage uploader shut down") 