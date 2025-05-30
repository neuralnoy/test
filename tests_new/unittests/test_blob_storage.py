"""
Comprehensive unit tests for common_new.blob_storage module.
"""
import pytest
import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, Mock, patch, mock_open
from common_new.blob_storage import AsyncBlobStorageUploader


class TestAsyncBlobStorageUploaderInit:
    """Test AsyncBlobStorageUploader initialization."""
    
    @pytest.mark.unit
    def test_init_basic(self):
        """Test basic initialization."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        
        assert uploader.account_url == "https://test.blob.core.windows.net"
        assert uploader.container_name == "test-container"
        assert uploader.max_retries == 16
        assert uploader.retry_delay == 2.0
        assert not uploader._initialized
        assert uploader._upload_task is None
        assert len(uploader._processed_files) == 0
    
    @pytest.mark.unit
    def test_init_with_custom_params(self):
        """Test initialization with custom parameters."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://custom.blob.core.windows.net",
            container_name="custom-container",
            max_retries=5,
            retry_delay=1.0
        )
        
        assert uploader.account_url == "https://custom.blob.core.windows.net"
        assert uploader.container_name == "custom-container"
        assert uploader.max_retries == 5
        assert uploader.retry_delay == 1.0


class TestAsyncBlobStorageUploaderInitialize:
    """Test the initialize method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_initialize_success(self):
        """Test successful initialization."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        
        # Mock Azure components
        mock_credential = AsyncMock()
        mock_blob_client = AsyncMock()
        mock_container = {"name": "test-container"}
        
        with patch('common_new.blob_storage.DefaultAzureCredential', return_value=mock_credential):
            with patch('common_new.blob_storage.BlobServiceClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                mock_client.list_containers.return_value.__aiter__.return_value = [mock_container]
                
                result = await uploader.initialize()
                
                assert result is True
                assert uploader._initialized is True
                assert uploader._upload_task is not None
                mock_client.close.assert_called_once()
                mock_credential.close.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_initialize_already_initialized(self):
        """Test initialization when already initialized."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        uploader._initialized = True
        
        result = await uploader.initialize()
        assert result is True
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_initialize_container_not_found(self):
        """Test initialization when container doesn't exist."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="missing-container"
        )
        
        mock_credential = AsyncMock()
        
        with patch('common_new.blob_storage.DefaultAzureCredential', return_value=mock_credential):
            with patch('common_new.blob_storage.BlobServiceClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                mock_client.list_containers.return_value.__aiter__.return_value = []
                
                result = await uploader.initialize()
                
                assert result is True
                assert uploader._initialized is True
                mock_client.close.assert_called_once()
                mock_credential.close.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_initialize_failure(self):
        """Test initialization failure."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        
        mock_credential = AsyncMock()
        
        with patch('common_new.blob_storage.DefaultAzureCredential', return_value=mock_credential):
            with patch('common_new.blob_storage.BlobServiceClient', side_effect=Exception("Connection failed")):
                result = await uploader.initialize()
                
                assert result is False
                assert not uploader._initialized
                mock_credential.close.assert_called_once()


class TestAsyncBlobStorageUploaderUploadFile:
    """Test the upload_file method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_upload_file_not_initialized(self):
        """Test upload_file when uploader is not initialized."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        
        with patch.object(uploader, 'initialize', return_value=False):
            with patch('os.path.exists', return_value=True):
                await uploader.upload_file("test.txt")
                
                # Queue should be empty since initialization failed
                assert uploader._upload_queue.qsize() == 0
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_upload_file_file_not_exists(self):
        """Test upload_file when file doesn't exist."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        uploader._initialized = True
        
        with patch('os.path.exists', return_value=False):
            await uploader.upload_file("nonexistent.txt")
            
            assert uploader._upload_queue.qsize() == 0
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_upload_file_already_processed(self):
        """Test upload_file when file is already processed."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        uploader._initialized = True
        uploader._processed_files.add("test.txt")
        
        with patch('os.path.exists', return_value=True):
            await uploader.upload_file("test.txt")
            
            assert uploader._upload_queue.qsize() == 0
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_upload_file_success(self):
        """Test successful file upload queuing."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        uploader._initialized = True
        
        with patch('os.path.exists', return_value=True):
            await uploader.upload_file("test.txt")
            
            assert uploader._upload_queue.qsize() == 1
            file_path, blob_name = await uploader._upload_queue.get()
            assert file_path == "test.txt"
            assert blob_name == "test.txt"
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_upload_file_with_custom_blob_name(self):
        """Test file upload with custom blob name."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        uploader._initialized = True
        
        with patch('os.path.exists', return_value=True):
            await uploader.upload_file("test.txt", blob_name="custom.txt")
            
            assert uploader._upload_queue.qsize() == 1
            file_path, blob_name = await uploader._upload_queue.get()
            assert file_path == "test.txt"
            assert blob_name == "custom.txt"
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_upload_file_with_app_name(self):
        """Test file upload with app name prefix."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        uploader._initialized = True
        
        with patch('os.path.exists', return_value=True):
            await uploader.upload_file("test.txt", app_name="myapp")
            
            assert uploader._upload_queue.qsize() == 1
            file_path, blob_name = await uploader._upload_queue.get()
            assert file_path == "test.txt"
            assert blob_name == "myapp/test.txt"


class TestAsyncBlobStorageUploaderUploadFileToBlob:
    """Test the _upload_file_to_blob method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_upload_file_to_blob_file_not_exists(self):
        """Test upload when file doesn't exist."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        
        with patch('os.path.exists', return_value=False):
            result = await uploader._upload_file_to_blob("nonexistent.txt", "blob.txt")
            assert result is False
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_upload_file_to_blob_success(self):
        """Test successful file upload to blob."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        
        mock_credential = AsyncMock()
        mock_blob_client = AsyncMock()
        mock_container_client = AsyncMock()
        mock_service_client = AsyncMock()
        
        mock_service_client.get_container_client.return_value = mock_container_client
        mock_container_client.get_blob_client.return_value = mock_blob_client
        
        file_content = b"test file content"
        
        with patch('os.path.exists', return_value=True):
            with patch('os.path.getsize', return_value=len(file_content)):
                with patch('builtins.open', mock_open(read_data=file_content)):
                    with patch('common_new.blob_storage.DefaultAzureCredential', return_value=mock_credential):
                        with patch('common_new.blob_storage.BlobServiceClient', return_value=mock_service_client):
                            result = await uploader._upload_file_to_blob("test.txt", "blob.txt")
                            
                            assert result is True
                            mock_blob_client.upload_blob.assert_called_once_with(file_content, overwrite=True)
                            mock_service_client.close.assert_called_once()
                            mock_credential.close.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_upload_file_to_blob_with_retries(self):
        """Test file upload with retries on failure."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container",
            max_retries=2,
            retry_delay=0.1
        )
        
        mock_credential = AsyncMock()
        mock_blob_client = AsyncMock()
        mock_container_client = AsyncMock()
        mock_service_client = AsyncMock()
        
        mock_service_client.get_container_client.return_value = mock_container_client
        mock_container_client.get_blob_client.return_value = mock_blob_client
        
        # First attempt fails, second succeeds
        mock_blob_client.upload_blob.side_effect = [Exception("Upload failed"), None]
        
        file_content = b"test file content"
        
        with patch('os.path.exists', return_value=True):
            with patch('os.path.getsize', return_value=len(file_content)):
                with patch('builtins.open', mock_open(read_data=file_content)):
                    with patch('common_new.blob_storage.DefaultAzureCredential', return_value=mock_credential):
                        with patch('common_new.blob_storage.BlobServiceClient', return_value=mock_service_client):
                            with patch('asyncio.sleep'):
                                result = await uploader._upload_file_to_blob("test.txt", "blob.txt")
                                
                                assert result is True
                                assert mock_blob_client.upload_blob.call_count == 2
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_upload_file_to_blob_max_retries_exceeded(self):
        """Test file upload when max retries are exceeded."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container",
            max_retries=2,
            retry_delay=0.1
        )
        
        mock_credential = AsyncMock()
        mock_blob_client = AsyncMock()
        mock_container_client = AsyncMock()
        mock_service_client = AsyncMock()
        
        mock_service_client.get_container_client.return_value = mock_container_client
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_blob_client.upload_blob.side_effect = Exception("Upload failed")
        
        file_content = b"test file content"
        
        with patch('os.path.exists', return_value=True):
            with patch('os.path.getsize', return_value=len(file_content)):
                with patch('builtins.open', mock_open(read_data=file_content)):
                    with patch('common_new.blob_storage.DefaultAzureCredential', return_value=mock_credential):
                        with patch('common_new.blob_storage.BlobServiceClient', return_value=mock_service_client):
                            with patch('asyncio.sleep'):
                                result = await uploader._upload_file_to_blob("test.txt", "blob.txt")
                                
                                assert result is False
                                assert mock_blob_client.upload_blob.call_count == 2


class TestAsyncBlobStorageUploaderUploadWorker:
    """Test the _upload_worker method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_upload_worker_processes_queue(self):
        """Test that upload worker processes queued files."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        
        # Mock successful upload
        with patch.object(uploader, '_upload_file_to_blob', return_value=True):
            # Start worker
            worker_task = asyncio.create_task(uploader._upload_worker())
            
            # Add items to queue
            await uploader._upload_queue.put(("test1.txt", "blob1.txt"))
            await uploader._upload_queue.put(("test2.txt", "blob2.txt"))
            
            # Let worker process one item
            await asyncio.sleep(0.1)
            
            # Cancel worker
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            
            # Check that files were marked as processed
            assert "test1.txt" in uploader._processed_files
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_upload_worker_handles_upload_failure(self):
        """Test that upload worker handles upload failures gracefully."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        
        # Mock failed upload
        with patch.object(uploader, '_upload_file_to_blob', return_value=False):
            # Start worker
            worker_task = asyncio.create_task(uploader._upload_worker())
            
            # Add item to queue
            await uploader._upload_queue.put(("test.txt", "blob.txt"))
            
            # Let worker process item
            await asyncio.sleep(0.1)
            
            # Cancel worker
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            
            # File should not be marked as processed on failure
            assert "test.txt" not in uploader._processed_files
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_upload_worker_handles_exceptions(self):
        """Test that upload worker handles exceptions gracefully."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        
        # Mock upload that raises exception
        with patch.object(uploader, '_upload_file_to_blob', side_effect=Exception("Unexpected error")):
            # Start worker
            worker_task = asyncio.create_task(uploader._upload_worker())
            
            # Add item to queue
            await uploader._upload_queue.put(("test.txt", "blob.txt"))
            
            # Let worker process item
            await asyncio.sleep(0.1)
            
            # Cancel worker
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            
            # Worker should continue running despite exception
            # File should not be marked as processed on exception
            assert "test.txt" not in uploader._processed_files


class TestAsyncBlobStorageUploaderShutdown:
    """Test the shutdown method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_shutdown_not_initialized(self):
        """Test shutdown when uploader is not initialized."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        
        await uploader.shutdown()
        # Should not raise any exceptions
        assert not uploader._initialized
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_shutdown_with_pending_uploads(self):
        """Test shutdown with pending uploads in queue."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        uploader._initialized = True
        
        # Mock upload task
        mock_task = AsyncMock()
        mock_task.done.return_value = False
        uploader._upload_task = mock_task
        
        # Add items to queue
        await uploader._upload_queue.put(("test1.txt", "blob1.txt"))
        await uploader._upload_queue.put(("test2.txt", "blob2.txt"))
        
        with patch('asyncio.wait_for') as mock_wait_for:
            mock_wait_for.return_value = None  # Simulate successful wait
            
            await uploader.shutdown()
            
            mock_wait_for.assert_called_once()
            mock_task.cancel.assert_called_once()
            assert not uploader._initialized
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_shutdown_timeout(self):
        """Test shutdown when waiting for queue times out."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        uploader._initialized = True
        
        # Mock upload task
        mock_task = AsyncMock()
        mock_task.done.return_value = False
        uploader._upload_task = mock_task
        
        # Add items to queue
        await uploader._upload_queue.put(("test.txt", "blob.txt"))
        
        with patch('asyncio.wait_for', side_effect=asyncio.TimeoutError):
            await uploader.shutdown()
            
            mock_task.cancel.assert_called_once()
            assert not uploader._initialized


class TestAsyncBlobStorageUploaderIntegration:
    """Integration tests for AsyncBlobStorageUploader."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_full_upload_lifecycle(self):
        """Test complete upload lifecycle from initialization to shutdown."""
        uploader = AsyncBlobStorageUploader(
            account_url="https://test.blob.core.windows.net",
            container_name="test-container"
        )
        
        # Mock all Azure components
        mock_credential = AsyncMock()
        mock_blob_client = AsyncMock()
        mock_container_client = AsyncMock()
        mock_service_client = AsyncMock()
        
        mock_service_client.get_container_client.return_value = mock_container_client
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_service_client.list_containers.return_value.__aiter__.return_value = [{"name": "test-container"}]
        
        file_content = b"test file content"
        
        with patch('os.path.exists', return_value=True):
            with patch('os.path.getsize', return_value=len(file_content)):
                with patch('builtins.open', mock_open(read_data=file_content)):
                    with patch('common_new.blob_storage.DefaultAzureCredential', return_value=mock_credential):
                        with patch('common_new.blob_storage.BlobServiceClient', return_value=mock_service_client):
                            # Initialize
                            init_success = await uploader.initialize()
                            assert init_success is True
                            
                            # Upload file
                            await uploader.upload_file("test.txt", "test-blob.txt")
                            
                            # Wait for upload to process
                            await asyncio.sleep(0.1)
                            
                            # Shutdown
                            await uploader.shutdown()
                            
                            # Verify upload was called
                            mock_blob_client.upload_blob.assert_called_once()
                            assert "test.txt" in uploader._processed_files 