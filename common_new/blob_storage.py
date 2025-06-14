"""
Asynchronous Azure Blob Storage client for uploading and downloading files.
"""
import os
import asyncio
from typing import Optional, Set, List
from azure.storage.blob.aio import BlobServiceClient
from azure.identity.aio import DefaultAzureCredential
from common_new.logger import get_logger

logger = get_logger("common")

class AsyncBlobStorageUploader:
    """
    Asynchronous handler for uploading files to Azure Blob Storage.
    Uses Azure Identity for authentication with DefaultAzureCredential.
    """
    def __init__(
        self,
        account_url: str,
        container_name: str,
        max_retries: int = 5,
        retry_delay: float = 2.0,
        delete_after_upload: bool = True
    ):
        """
        Initialize the Azure Blob Storage uploader.
        
        Args:
            account_url: Azure Storage account URL (e.g., https://accountname.blob.core.windows.net)
            container_name: Name of the container to store uploaded files
            max_retries: Maximum number of retry attempts for failed uploads
            retry_delay: Base delay between retries in seconds (uses exponential backoff)
            delete_after_upload: Whether to delete files from local storage after successful upload
        """
        self.account_url = account_url
        self.container_name = container_name
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.delete_after_upload = delete_after_upload
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
        credential = None
        blob_service_client = None
        
        try:
            # Create credential and client for testing
            credential = DefaultAzureCredential()
            blob_service_client = BlobServiceClient(
                account_url=self.account_url,
                credential=credential
            )
            
            # Test connection by listing containers
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
        finally:
            # Make sure to close resources even when successful
            if blob_service_client:
                await blob_service_client.close()
            if credential:
                await credential.close()
        
    async def upload_file(self, file_path: str, blob_name: Optional[str] = None, app_name: Optional[str] = None) -> None:
        """
        Queue a file for upload to Azure Blob Storage.
        
        Args:
            file_path: Path to the file to upload
            blob_name: Name of the blob in the container (defaults to file basename)
            app_name: Optional application name to use as directory prefix
        """
        if not self._initialized:
            success = await self.initialize()
            if not success:
                logger.error(f"Failed to initialize uploader, cannot upload {file_path}")
                return
            
        if not blob_name:
            blob_name = os.path.basename(file_path)
        
        # If app_name is provided, prepend it to the blob_name
        if app_name:
            blob_name = f"{app_name}/{blob_name}"
        
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
                        
                        # Delete the file after successful upload
                        if self.delete_after_upload:
                            try:
                                os.remove(file_path)
                                logger.info(f"Successfully deleted {file_path} from local storage")
                            except FileNotFoundError:
                                logger.warning(f"File {file_path} was already deleted")
                            except PermissionError:
                                logger.error(f"Permission denied when trying to delete {file_path}")
                            except Exception as e:
                                logger.error(f"Error deleting {file_path}: {str(e)}")
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

        # Implement retry logic with exponential backoff
        for attempt in range(self.max_retries):
            credential = None
            blob_service_client = None
            
            try:
                # Create credentials and client
                credential = DefaultAzureCredential()
                blob_service_client = BlobServiceClient(
                    account_url=self.account_url,
                    credential=credential
                )
                
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
                
                # Upload the file - use a synchronous open, then upload the data
                file_size = os.path.getsize(file_path)
                logger.info(f"Uploading {file_path} ({file_size} bytes) to blob storage as {blob_name}")
                
                # Use regular (non-async) file opening, then upload the data
                with open(file_path, "rb") as f:
                    data = f.read()
                
                # Upload the data from memory
                await blob_client.upload_blob(
                    data, 
                    overwrite=True
                )
                
                return True
                    
            except Exception as e:
                if attempt < self.max_retries - 1:
                    # Add a fixed 1-second delay before calculating the exponential backoff
                    await asyncio.sleep(1.0)
                    
                    # Calculate exponential backoff for additional delay
                    delay = self.retry_delay * (2 ** attempt)
                    logger.warning(f"Error uploading {file_path} (attempt {attempt+1}/{self.max_retries}): {str(e)}")
                    logger.info(f"Retrying in {delay:.1f} seconds after initial 1-second delay...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Error uploading {file_path} after {self.max_retries} attempts: {str(e)}")
                    return False
            finally:
                # Always clean up resources
                if blob_service_client:
                    await blob_service_client.close()
                if credential:
                    await credential.close()
            
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

class AsyncBlobStorageDownloader:
    """
    Asynchronous handler for downloading files from Azure Blob Storage.
    Uses Azure Identity for authentication with DefaultAzureCredential.
    """
    def __init__(
        self,
        account_url: str,
        container_name: str,
        max_retries: int = 5,
        retry_delay: float = 2.0,
        download_dir: Optional[str] = None
    ):
        """
        Initialize the Azure Blob Storage downloader.
        
        Args:
            account_url: Azure Storage account URL (e.g., https://accountname.blob.core.windows.net)
            container_name: Name of the container to download files from
            max_retries: Maximum number of retry attempts for failed downloads
            retry_delay: Base delay between retries in seconds (uses exponential backoff)
            download_dir: Directory to download files to (defaults to current directory)
        """
        self.account_url = account_url
        self.container_name = container_name
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.download_dir = download_dir or os.getcwd()
        self._initialized = False
        
        # Ensure download directory exists
        os.makedirs(self.download_dir, exist_ok=True)
        
    async def initialize(self) -> bool:
        """
        Initialize the downloader and verify connection.
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        if self._initialized:
            return True
            
        logger.info(f"Initializing Blob Storage Downloader with container {self.container_name}")
        
        # Verify we can connect to Azure Blob Storage
        credential = None
        blob_service_client = None
        
        try:
            # Create credential and client for testing
            credential = DefaultAzureCredential()
            blob_service_client = BlobServiceClient(
                account_url=self.account_url,
                credential=credential
            )
            
            # Test connection by checking if container exists
            container_client = blob_service_client.get_container_client(self.container_name)
            container_exists = await container_client.exists()
            
            if not container_exists:
                logger.error(f"Container {self.container_name} does not exist")
                return False
            
            self._initialized = True
            logger.info(f"Blob Storage Downloader initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Blob Storage Downloader: {str(e)}")
            return False
        finally:
            # Make sure to close resources
            if blob_service_client:
                await blob_service_client.close()
            if credential:
                await credential.close()
    
    async def download_file(
        self, 
        blob_name: str, 
        local_file_path: Optional[str] = None,
        overwrite: bool = False
    ) -> Optional[str]:
        """
        Download a file from Azure Blob Storage.
        
        Args:
            blob_name: Name of the blob to download
            local_file_path: Local path to save the file (defaults to download_dir/blob_name)
            overwrite: Whether to overwrite existing local files
            
        Returns:
            str: Path to the downloaded file, or None if download failed
        """
        if not self._initialized:
            success = await self.initialize()
            if not success:
                logger.error(f"Failed to initialize downloader, cannot download {blob_name}")
                return None
        
        # Determine local file path
        if not local_file_path:
            # Use just the filename part of blob_name for local storage
            filename = os.path.basename(blob_name)
            local_file_path = os.path.join(self.download_dir, filename)
        
        # Check if file already exists
        if os.path.exists(local_file_path) and not overwrite:
            logger.info(f"File {local_file_path} already exists, skipping download")
            return local_file_path
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
        
        # Download the file with retry logic
        for attempt in range(self.max_retries):
            success = await self._download_blob_to_file(blob_name, local_file_path)
            if success:
                return local_file_path
            
            if attempt < self.max_retries - 1:
                wait_time = self.retry_delay * (2 ** attempt)
                logger.warning(f"Download attempt {attempt + 1} failed, retrying in {wait_time} seconds")
                await asyncio.sleep(wait_time)
        
        logger.error(f"Failed to download {blob_name} after {self.max_retries} attempts")
        return None
    
    async def _download_blob_to_file(self, blob_name: str, local_file_path: str) -> bool:
        """
        Download a blob to a local file.
        
        Args:
            blob_name: Name of the blob to download
            local_file_path: Local path to save the file
            
        Returns:
            bool: True if download was successful, False otherwise
        """
        credential = None
        blob_service_client = None
        
        try:
            # Create credentials and client
            credential = DefaultAzureCredential()
            blob_service_client = BlobServiceClient(
                account_url=self.account_url,
                credential=credential
            )
            
            # Get the blob client
            blob_client = blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            
            # Check if blob exists
            blob_exists = await blob_client.exists()
            if not blob_exists:
                logger.error(f"Blob {blob_name} does not exist in container {self.container_name}")
                return False
            
            # Get blob properties for logging
            blob_properties = await blob_client.get_blob_properties()
            blob_size = blob_properties.size
            
            logger.info(f"Downloading {blob_name} ({blob_size} bytes) to {local_file_path}")
            
            # Download the blob
            with open(local_file_path, "wb") as download_file:
                download_stream = await blob_client.download_blob()
                async for chunk in download_stream.chunks():
                    download_file.write(chunk)
            
            # Verify the download
            if os.path.exists(local_file_path):
                downloaded_size = os.path.getsize(local_file_path)
                if downloaded_size == blob_size:
                    logger.info(f"Successfully downloaded {blob_name} to {local_file_path}")
                    return True
                else:
                    logger.error(f"Download size mismatch: expected {blob_size}, got {downloaded_size}")
                    # Clean up partial download
                    try:
                        os.remove(local_file_path)
                    except:
                        pass
                    return False
            else:
                logger.error(f"Downloaded file {local_file_path} does not exist")
                return False
                
        except Exception as e:
            logger.error(f"Error downloading blob {blob_name}: {str(e)}")
            # Clean up partial download
            try:
                if os.path.exists(local_file_path):
                    os.remove(local_file_path)
            except:
                pass
            return False
        finally:
            # Clean up resources
            if blob_service_client:
                await blob_service_client.close()
            if credential:
                await credential.close()
    
    async def list_blobs(self, name_starts_with: Optional[str] = None) -> List[str]:
        """
        List blobs in the container.
        
        Args:
            name_starts_with: Optional prefix to filter blob names
            
        Returns:
            List of blob names
        """
        if not self._initialized:
            success = await self.initialize()
            if not success:
                logger.error("Failed to initialize downloader, cannot list blobs")
                return []
        
        credential = None
        blob_service_client = None
        
        try:
            credential = DefaultAzureCredential()
            blob_service_client = BlobServiceClient(
                account_url=self.account_url,
                credential=credential
            )
            
            container_client = blob_service_client.get_container_client(self.container_name)
            
            blob_names = []
            async for blob in container_client.list_blobs(name_starts_with=name_starts_with):
                blob_names.append(blob.name)
            
            logger.info(f"Found {len(blob_names)} blobs in container {self.container_name}")
            return blob_names
            
        except Exception as e:
            logger.error(f"Error listing blobs: {str(e)}")
            return []
        finally:
            if blob_service_client:
                await blob_service_client.close()
            if credential:
                await credential.close()
    
    async def blob_exists(self, blob_name: str) -> bool:
        """
        Check if a blob exists in the container.
        
        Args:
            blob_name: Name of the blob to check
            
        Returns:
            bool: True if blob exists, False otherwise
        """
        if not self._initialized:
            success = await self.initialize()
            if not success:
                return False
        
        credential = None
        blob_service_client = None
        
        try:
            credential = DefaultAzureCredential()
            blob_service_client = BlobServiceClient(
                account_url=self.account_url,
                credential=credential
            )
            
            blob_client = blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            
            return await blob_client.exists()
            
        except Exception as e:
            logger.error(f"Error checking if blob {blob_name} exists: {str(e)}")
            return False
        finally:
            if blob_service_client:
                await blob_service_client.close()
            if credential:
                await credential.close()

