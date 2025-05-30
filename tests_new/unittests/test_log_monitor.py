"""
Comprehensive unit tests for common_new.log_monitor module.
"""
import pytest
import asyncio
import os
import tempfile
import json
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from pathlib import Path
from common_new.log_monitor import LogMonitorService


class TestLogMonitorServiceInit:
    """Test LogMonitorService initialization."""
    
    def setup_method(self):
        """Reset singleton instance before each test."""
        LogMonitorService._instance = None
    
    @pytest.mark.unit
    def test_singleton_pattern(self):
        """Test that only one instance is created."""
        service1 = LogMonitorService(logs_dir="/tmp/logs")
        service2 = LogMonitorService(logs_dir="/different/path")
        assert service1 is service2
    
    @pytest.mark.unit
    def test_init_with_account_url(self):
        """Test initialization with direct account URL."""
        service = LogMonitorService(
            logs_dir="/tmp/logs",
            account_url="https://test.blob.core.windows.net",
            container_name="test-logs",
            app_name="test-app"
        )
        
        assert service.logs_dir == "/tmp/logs"
        assert service.account_url == "https://test.blob.core.windows.net"
        assert service.container_name == "test-logs"
        assert service.app_name == "test-app"
        assert service.retention_days == 30
        assert service.scan_interval == 60
        assert not service._running
        assert not service._is_leader
    
    @pytest.mark.unit
    def test_init_with_account_name(self):
        """Test initialization with account name (constructs URL)."""
        service = LogMonitorService(
            logs_dir="/tmp/logs",
            account_name="testaccount"
        )
        
        assert service.account_url == "https://testaccount.blob.core.windows.net"
    
    @pytest.mark.unit
    def test_init_no_account_info(self):
        """Test initialization without account information."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        assert service.account_url is None
    
    @pytest.mark.unit
    def test_init_custom_params(self):
        """Test initialization with custom parameters."""
        service = LogMonitorService(
            logs_dir="/custom/logs",
            account_url="https://custom.blob.core.windows.net",
            container_name="custom-logs",
            app_name="custom-app",
            retention_days=7,
            scan_interval=30
        )
        
        assert service.retention_days == 7
        assert service.scan_interval == 30
    
    @pytest.mark.unit
    def test_init_only_once(self):
        """Test that initialization only happens once."""
        service1 = LogMonitorService(logs_dir="/tmp/logs", app_name="first")
        service2 = LogMonitorService(logs_dir="/different", app_name="second")
        
        # Second initialization should not override first
        assert service1.app_name == "first"
        assert service2.app_name == "first"  # Same instance
        assert service1._initialized is True


class TestLogMonitorServiceLeadership:
    """Test leadership acquisition and release."""
    
    def setup_method(self):
        """Reset singleton instance before each test."""
        LogMonitorService._instance = None
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_try_acquire_leadership_success(self):
        """Test successful leadership acquisition."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app")
        
        mock_file = MagicMock()
        
        with patch('builtins.open', return_value=mock_file):
            with patch('fcntl.flock'):
                with patch('os.getpid', return_value=12345):
                    with patch('time.time', return_value=1234567890.0):
                        result = await service._try_acquire_leadership()
                        
                        assert result is True
                        mock_file.write.assert_called_once()
                        mock_file.flush.assert_called_once()
                        
                        # Verify lock info was written
                        written_data = mock_file.write.call_args[0][0]
                        lock_info = json.loads(written_data)
                        assert lock_info["pid"] == 12345
                        assert lock_info["app_name"] == "test-app"
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_try_acquire_leadership_failure(self):
        """Test failed leadership acquisition."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app")
        
        mock_file = MagicMock()
        
        with patch('builtins.open', return_value=mock_file):
            with patch('fcntl.flock', side_effect=OSError("Lock held")):
                result = await service._try_acquire_leadership()
                
                assert result is False
                mock_file.close.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_release_leadership(self):
        """Test releasing leadership."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app")
        
        mock_file = MagicMock()
        service._lock_file = mock_file
        service._is_leader = True
        
        with patch('fcntl.flock'):
            with patch('os.path.exists', return_value=True):
                with patch('os.unlink') as mock_unlink:
                    await service._release_leadership()
                    
                    mock_file.close.assert_called_once()
                    mock_unlink.assert_called_once()
                    assert service._lock_file is None
                    assert not service._is_leader
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_release_leadership_with_exception(self):
        """Test releasing leadership when exception occurs."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app")
        
        mock_file = MagicMock()
        service._lock_file = mock_file
        service._is_leader = True
        
        with patch('fcntl.flock', side_effect=Exception("Release failed")):
            await service._release_leadership()
            
            # Should still clean up state despite exception
            assert service._lock_file is None
            assert not service._is_leader


class TestLogMonitorServiceInitialize:
    """Test the initialize method."""
    
    def setup_method(self):
        """Reset singleton instance before each test."""
        LogMonitorService._instance = None
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_initialize_already_running(self):
        """Test initialization when already running."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        service._running = True
        
        result = await service.initialize()
        assert result is True
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_initialize_no_account_url(self):
        """Test initialization without account URL (no blob storage)."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        
        with patch.object(service, '_try_acquire_leadership', return_value=True):
            with patch('pathlib.Path.mkdir'):
                result = await service.initialize()
                
                assert result is True
                assert service._is_leader is True
                assert service.uploader is None  # No uploader created
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_initialize_with_blob_storage_success(self):
        """Test successful initialization with blob storage."""
        service = LogMonitorService(
            logs_dir="/tmp/logs",
            account_url="https://test.blob.core.windows.net"
        )
        
        mock_uploader = AsyncMock()
        mock_uploader.initialize.return_value = True
        
        with patch.object(service, '_try_acquire_leadership', return_value=True):
            with patch('pathlib.Path.mkdir'):
                with patch('common_new.log_monitor.AsyncBlobStorageUploader', return_value=mock_uploader):
                    with patch('asyncio.create_task') as mock_create_task:
                        result = await service.initialize()
                        
                        assert result is True
                        assert service._is_leader is True
                        assert service._running is True
                        assert service.uploader is mock_uploader
                        mock_uploader.initialize.assert_called_once()
                        mock_create_task.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_initialize_blob_storage_failure(self):
        """Test initialization when blob storage fails."""
        service = LogMonitorService(
            logs_dir="/tmp/logs",
            account_url="https://test.blob.core.windows.net"
        )
        
        mock_uploader = AsyncMock()
        mock_uploader.initialize.return_value = False
        
        with patch.object(service, '_try_acquire_leadership', return_value=True):
            with patch.object(service, '_release_leadership') as mock_release:
                with patch('common_new.log_monitor.AsyncBlobStorageUploader', return_value=mock_uploader):
                    result = await service.initialize()
                    
                    assert result is False
                    mock_release.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_initialize_not_leader(self):
        """Test initialization when not acquiring leadership."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        
        with patch.object(service, '_try_acquire_leadership', return_value=False):
            result = await service.initialize()
            
            assert result is True
            assert not service._is_leader
            assert not service._running


class TestLogMonitorServiceScanForRotatedLogs:
    """Test the _scan_for_rotated_logs method."""
    
    def setup_method(self):
        """Reset singleton instance before each test."""
        LogMonitorService._instance = None
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_for_rotated_logs_no_files(self):
        """Test scanning when no rotated logs exist."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app")
        service.uploader = AsyncMock()
        
        with patch('pathlib.Path.glob', return_value=[]):
            await service._scan_for_rotated_logs()
            
            service.uploader.upload_file.assert_not_called()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_for_rotated_logs_with_files(self):
        """Test scanning with rotated log files."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app")
        service.uploader = AsyncMock()
        
        # Mock rotated log files
        mock_file1 = Mock()
        mock_file1.name = "test-app_20231201.log"
        mock_file1.is_file.return_value = True
        mock_file1.stat.return_value.st_mtime = 1700000000  # Old file
        
        mock_file2 = Mock()
        mock_file2.name = "test-app_20231202.log"
        mock_file2.is_file.return_value = True
        mock_file2.stat.return_value.st_mtime = 1700086400  # Another old file
        
        with patch('pathlib.Path.glob', return_value=[mock_file1, mock_file2]):
            await service._scan_for_rotated_logs()
            
            # Should upload both files
            assert service.uploader.upload_file.call_count == 2
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_for_rotated_logs_with_recent_files(self):
        """Test scanning with recent files (should be skipped)."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app", retention_days=1)
        service.uploader = AsyncMock()
        
        # Mock recent file (should be skipped)
        mock_file = Mock()
        mock_file.name = "test-app_today.log"
        mock_file.is_file.return_value = True
        mock_file.stat.return_value.st_mtime = 9999999999  # Very recent
        
        with patch('pathlib.Path.glob', return_value=[mock_file]):
            with patch('time.time', return_value=9999999999):
                await service._scan_for_rotated_logs()
                
                service.uploader.upload_file.assert_not_called()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_for_rotated_logs_already_processed(self):
        """Test scanning with already processed files."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app")
        service.uploader = AsyncMock()
        service._processed_files.add("test-app_20231201.log")
        
        mock_file = Mock()
        mock_file.name = "test-app_20231201.log"
        mock_file.is_file.return_value = True
        mock_file.stat.return_value.st_mtime = 1700000000
        
        with patch('pathlib.Path.glob', return_value=[mock_file]):
            await service._scan_for_rotated_logs()
            
            service.uploader.upload_file.assert_not_called()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_for_rotated_logs_no_uploader(self):
        """Test scanning when no uploader is configured."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app")
        service.uploader = None
        
        mock_file = Mock()
        mock_file.name = "test-app_20231201.log"
        
        with patch('pathlib.Path.glob', return_value=[mock_file]):
            # Should not raise exception
            await service._scan_for_rotated_logs()


class TestLogMonitorServiceMonitorLoop:
    """Test the _monitor_loop method."""
    
    def setup_method(self):
        """Reset singleton instance before each test."""
        LogMonitorService._instance = None
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_monitor_loop_as_leader(self):
        """Test monitor loop when process is leader."""
        service = LogMonitorService(logs_dir="/tmp/logs", scan_interval=0.1)
        service._running = True
        service._is_leader = True
        
        scan_called = False
        async def mock_scan():
            nonlocal scan_called
            scan_called = True
            service._running = False  # Stop after first scan
        
        with patch.object(service, '_scan_for_rotated_logs', side_effect=mock_scan):
            with patch('asyncio.sleep'):
                await service._monitor_loop()
                
                assert scan_called
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_monitor_loop_lost_leadership(self):
        """Test monitor loop when leadership is lost and reacquired."""
        service = LogMonitorService(logs_dir="/tmp/logs", scan_interval=0.1)
        service._running = True
        service._is_leader = False  # Start as non-leader
        
        reacquire_called = False
        async def mock_reacquire():
            nonlocal reacquire_called
            reacquire_called = True
            service._is_leader = True
            service._running = False  # Stop after reacquiring
            return True
        
        with patch.object(service, '_try_acquire_leadership', side_effect=mock_reacquire):
            with patch('asyncio.sleep'):
                await service._monitor_loop()
                
                assert reacquire_called
                assert service._is_leader
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_monitor_loop_cancelled(self):
        """Test monitor loop cancellation."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        service._running = True
        service._is_leader = True
        
        # Create a task that gets cancelled
        async def run_and_cancel():
            task = asyncio.create_task(service._monitor_loop())
            await asyncio.sleep(0.01)  # Let it start
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        with patch.object(service, '_scan_for_rotated_logs'):
            await run_and_cancel()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_monitor_loop_exception_handling(self):
        """Test monitor loop handles exceptions gracefully."""
        service = LogMonitorService(logs_dir="/tmp/logs", scan_interval=0.1)
        service._running = True
        service._is_leader = True
        
        exception_count = 0
        async def mock_scan():
            nonlocal exception_count
            exception_count += 1
            if exception_count == 1:
                raise Exception("Scan failed")
            else:
                service._running = False  # Stop after retry
        
        with patch.object(service, '_scan_for_rotated_logs', side_effect=mock_scan):
            with patch('asyncio.sleep'):
                await service._monitor_loop()
                
                assert exception_count == 2  # Should retry after exception


class TestLogMonitorServiceIntegration:
    """Integration tests for LogMonitorService."""
    
    def setup_method(self):
        """Reset singleton instance before each test."""
        LogMonitorService._instance = None
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_full_lifecycle_with_blob_storage(self):
        """Test complete lifecycle with blob storage."""
        service = LogMonitorService(
            logs_dir="/tmp/logs",
            account_url="https://test.blob.core.windows.net",
            app_name="test-app"
        )
        
        mock_uploader = AsyncMock()
        mock_uploader.initialize.return_value = True
        
        with patch.object(service, '_try_acquire_leadership', return_value=True):
            with patch('pathlib.Path.mkdir'):
                with patch('common_new.log_monitor.AsyncBlobStorageUploader', return_value=mock_uploader):
                    # Initialize
                    result = await service.initialize()
                    assert result is True
                    assert service._is_leader
                    
                    # Should have created uploader
                    assert service.uploader is mock_uploader
                    mock_uploader.initialize.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_full_lifecycle_without_blob_storage(self):
        """Test complete lifecycle without blob storage."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app")
        
        with patch.object(service, '_try_acquire_leadership', return_value=True):
            with patch('pathlib.Path.mkdir'):
                # Initialize
                result = await service.initialize()
                assert result is True
                assert service._is_leader
                
                # Should not have created uploader
                assert service.uploader is None
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_multiple_instances_same_singleton(self):
        """Test that multiple instances return same singleton."""
        service1 = LogMonitorService(logs_dir="/tmp/logs1", app_name="app1")
        service2 = LogMonitorService(logs_dir="/tmp/logs2", app_name="app2")
        
        assert service1 is service2
        # First initialization should prevail
        assert service1.logs_dir == "/tmp/logs1"
        assert service1.app_name == "app1" 