"""
Comprehensive unit tests for common_new.log_monitor module.
"""
import pytest
import asyncio
import os
import tempfile
import time
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from pathlib import Path
from common_new.log_monitor import LogMonitorService


class TestLogMonitorServiceInit:
    """Test LogMonitorService initialization."""
    
    @pytest.mark.unit
    def test_basic_initialization_with_account_url(self):
        """Test basic initialization with direct account URL."""
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
        assert service.retention_days == 7
        assert service.scan_interval == 60
        assert service.enable_orphan_cleanup is True
        assert not service._running
        assert service.uploader is None
        assert service._monitor_task is None
        assert len(service._processed_files) == 0

    @pytest.mark.unit
    def test_initialization_with_account_name(self):
        """Test initialization with account name (constructs URL)."""
        service = LogMonitorService(
            logs_dir="/tmp/logs",
            account_name="testaccount",
            container_name="test-logs",
            app_name="test-app"
        )
        
        assert service.logs_dir == "/tmp/logs"
        assert service.account_url == "https://testaccount.blob.core.windows.net"
        assert service.container_name == "test-logs"
        assert service.app_name == "test-app"

    @pytest.mark.unit
    def test_initialization_no_account_info(self):
        """Test initialization without account information (no blob storage)."""
        service = LogMonitorService(
            logs_dir="/tmp/logs",
            app_name="test-app"
        )
        
        assert service.logs_dir == "/tmp/logs"
        assert service.account_url is None
        assert service.container_name == "fla-logs"  # Default value
        assert service.app_name == "test-app"
        assert service.retention_days == 7
        assert service.scan_interval == 60
        assert service.enable_orphan_cleanup is True

    @pytest.mark.unit
    def test_initialization_custom_params(self):
        """Test initialization with custom parameters."""
        service = LogMonitorService(
            logs_dir="/custom/logs",
            account_url="https://custom.blob.core.windows.net",
            container_name="custom-logs",
            app_name="custom-app",
            process_name="custom-process",
            retention_days=30,
            scan_interval=30,
            enable_orphan_cleanup=False
        )
        
        assert service.logs_dir == "/custom/logs"
        assert service.account_url == "https://custom.blob.core.windows.net"
        assert service.container_name == "custom-logs"
        assert service.app_name == "custom-app"
        assert service.process_name == "custom-process"
        assert service.retention_days == 30
        assert service.scan_interval == 30
        assert service.enable_orphan_cleanup is False

    @pytest.mark.unit
    def test_process_name_defaults(self):
        """Test process name fallback behavior."""
        # Test with PROCESS_NAME environment variable
        with patch.dict(os.environ, {'PROCESS_NAME': 'env-worker'}, clear=False):
            service = LogMonitorService(logs_dir="/tmp/logs")
            assert service.process_name == "env-worker"
        
        # Test without PROCESS_NAME env var (should fallback to worker-{pid})
        with patch.dict(os.environ, {}, clear=True):
            with patch('os.getpid', return_value=12345):
                service = LogMonitorService(logs_dir="/tmp/logs")
                assert service.process_name == "worker-12345"


class TestLogMonitorServicePidHandling:
    """Test PID extraction and process handling."""
    
    @pytest.mark.unit
    def test_extract_pid_from_valid_process_name(self):
        """Test PID extraction from valid worker-{pid} format."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        
        # Valid worker-{pid} format
        pid = service._extract_pid_from_process_name("worker-12345")
        assert pid == 12345
        
        # Another valid format
        pid = service._extract_pid_from_process_name("worker-99999")
        assert pid == 99999

    @pytest.mark.unit 
    def test_extract_pid_from_invalid_process_name(self):
        """Test PID extraction from invalid process names."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        
        # Non-worker format
        pid = service._extract_pid_from_process_name("custom-process")
        assert pid is None
        
        # Worker but non-numeric PID
        pid = service._extract_pid_from_process_name("worker-abc")
        assert pid is None
        
        # Empty string
        pid = service._extract_pid_from_process_name("")
        assert pid is None
        
        # None input
        pid = service._extract_pid_from_process_name(None)
        assert pid is None
        
        # Just "worker-" with no PID
        pid = service._extract_pid_from_process_name("worker-")
        assert pid is None

    @pytest.mark.unit
    def test_is_process_alive_success(self):
        """Test process alive check when psutil works correctly."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        
        # Process exists
        with patch('psutil.pid_exists', return_value=True):
            assert service._is_process_alive(12345) is True
        
        # Process doesn't exist
        with patch('psutil.pid_exists', return_value=False):
            assert service._is_process_alive(12345) is False

    @pytest.mark.unit
    def test_is_process_alive_exception_handling(self):
        """Test process alive check when psutil raises exceptions."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        
        # psutil raises an exception - should return False for safety
        with patch('psutil.pid_exists', side_effect=Exception("psutil error")):
            assert service._is_process_alive(12345) is False
        
        # Test with different exception types
        with patch('psutil.pid_exists', side_effect=OSError("Permission denied")):
            assert service._is_process_alive(12345) is False


class TestLogMonitorServiceInitialize:
    """Test the initialize method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_initialize_already_running(self):
        """Test initialization when service is already running."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        service._running = True
        
        result = await service.initialize()
        assert result is True
        # State should remain unchanged
        assert service._running is True

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_initialize_no_account_url(self):
        """Test initialization without account URL (no blob storage)."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        
        result = await service.initialize()
        
        assert result is True
        assert service.uploader is None
        assert service._running is False  # No monitor task started without blob storage
        assert service._monitor_task is None

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
        
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            with patch('common_new.log_monitor.AsyncBlobStorageUploader', return_value=mock_uploader):
                with patch('asyncio.create_task') as mock_create_task:
                    result = await service.initialize()
                    
                    assert result is True
                    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
                    assert service.uploader is mock_uploader
                    mock_uploader.initialize.assert_called_once()
                    assert service._running is True
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
        
        with patch('pathlib.Path.mkdir'):
            with patch('common_new.log_monitor.AsyncBlobStorageUploader', return_value=mock_uploader):
                result = await service.initialize()
                
                assert result is False
                assert service._running is False
                assert service._monitor_task is None


class TestLogMonitorServiceScanForRotatedLogs:
    """Test the _scan_for_rotated_logs method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_no_uploader(self):
        """Test scanning when no uploader is configured."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app")
        service.uploader = None
        
        # Should return early without doing anything
        await service._scan_for_rotated_logs()
        # No assertions needed - just checking it doesn't crash

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_logs_directory_not_exists(self):
        """Test scanning when logs directory doesn't exist."""
        service = LogMonitorService(logs_dir="/nonexistent/logs", app_name="test-app")
        service.uploader = AsyncMock()
        
        with patch('os.path.exists', return_value=False):
            await service._scan_for_rotated_logs()
            
        # Should not try to upload anything
        service.uploader.upload_file.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_no_rotated_logs(self):
        """Test scanning when no rotated log files exist."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app", process_name="worker-123")
        service.uploader = AsyncMock()
        
        with patch('os.path.exists', return_value=True):
            with patch('os.listdir', return_value=["other-file.txt", "test-app-worker-123.current.log"]):
                await service._scan_for_rotated_logs()
                
        # Should not try to upload anything
        service.uploader.upload_file.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_with_valid_rotated_logs(self):
        """Test scanning with valid rotated log files."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app", process_name="worker-123")
        service.uploader = AsyncMock()
        
        # Mock files in directory
        files = [
            "test-app-worker-123__2024-01-15.log",  # Valid rotated log
            "test-app-worker-123.current.log",      # Current log (should be skipped)
            "other-file.txt"                        # Other file (should be skipped)
        ]
        
        # Mock file stats (old file)
        mock_stat = Mock()
        mock_stat.st_mtime = time.time() - 3600  # 1 hour ago
        
        with patch('os.path.exists', return_value=True):
            with patch('os.listdir', return_value=files):
                with patch('os.stat', return_value=mock_stat):
                    with patch('os.path.join', side_effect=lambda a, b: f"{a}/{b}"):
                        with patch('time.time', return_value=time.time()):
                            await service._scan_for_rotated_logs()
                            
        # Should upload the rotated log file
        service.uploader.upload_file.assert_called_once()
        call_args = service.uploader.upload_file.call_args
        assert "/tmp/logs/test-app-worker-123__2024-01-15.log" in call_args[0][0]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_skips_recently_modified_files(self):
        """Test that recently modified files are skipped."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app", process_name="worker-123")
        service.uploader = AsyncMock()
        
        files = ["test-app-worker-123__2024-01-15.log"]
        
        # Mock file stats (very recent file)
        mock_stat = Mock()
        mock_stat.st_mtime = time.time() - 15  # 15 seconds ago (less than 30 second threshold)
        
        with patch('os.path.exists', return_value=True):
            with patch('os.listdir', return_value=files):
                with patch('os.stat', return_value=mock_stat):
                    with patch('time.time', return_value=time.time()):
                        await service._scan_for_rotated_logs()
                        
        # Should not upload recently modified files
        service.uploader.upload_file.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_skips_already_processed_files(self):
        """Test that already processed files are skipped."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app", process_name="worker-123")
        service.uploader = AsyncMock()
        
        # Add file to processed set
        file_path = "/tmp/logs/test-app-worker-123__2024-01-15.log"
        service._processed_files.add(file_path)
        
        files = ["test-app-worker-123__2024-01-15.log"]
        
        with patch('os.path.exists', return_value=True):
            with patch('os.listdir', return_value=files):
                with patch('os.path.join', return_value=file_path):
                    await service._scan_for_rotated_logs()
                    
        # Should not upload already processed files
        service.uploader.upload_file.assert_not_called()


class TestLogMonitorServiceOrphanDetection:
    """Test orphaned log file detection and processing."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_orphaned_logs_no_orphans(self):
        """Test orphan scanning when no orphaned files exist."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app", process_name="worker-123")
        
        # Only files from our own process
        files = [
            "test-app-worker-123__2024-01-15.log",
            "test-app-worker-123.current.log",
            "other-app-worker-456.current.log"  # Different app
        ]
        
        with patch('os.listdir', return_value=files):
            orphans = await service._scan_for_orphaned_logs(time.time())
            
        assert len(orphans) == 0

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_orphaned_logs_dead_process_rotated_log(self):
        """Test finding orphaned rotated logs from dead processes."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app", process_name="worker-123")
        
        files = [
            "test-app-worker-456__2024-01-15.log",  # Orphaned rotated log
            "test-app-worker-123.current.log"       # Our current log
        ]
        
        # Mock file stats (old file)
        mock_stat = Mock()
        mock_stat.st_mtime = time.time() - 3600  # 1 hour ago
        
        with patch('os.listdir', return_value=files):
            with patch('os.stat', return_value=mock_stat):
                with patch('os.path.join', side_effect=lambda a, b: f"{a}/{b}"):
                    orphans = await service._scan_for_orphaned_logs(time.time())
                    
        assert len(orphans) == 1
        assert "/tmp/logs/test-app-worker-456__2024-01-15.log" in orphans[0][0]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_orphaned_logs_dead_process_current_log(self):
        """Test finding orphaned current logs from dead processes."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app", process_name="worker-123")
        
        files = [
            "test-app-worker-456.current.log",  # Orphaned current log from dead process
            "test-app-worker-123.current.log"  # Our current log
        ]
        
        # Mock file stats (old file - 15 minutes ago, more than 10 minute threshold)
        mock_stat = Mock()
        mock_stat.st_mtime = time.time() - 900
        
        with patch('os.listdir', return_value=files):
            with patch('os.stat', return_value=mock_stat):
                with patch('os.path.join', side_effect=lambda a, b: f"{a}/{b}"):
                    with patch.object(service, '_extract_pid_from_process_name', return_value=456):
                        with patch.object(service, '_is_process_alive', return_value=False):
                            orphans = await service._scan_for_orphaned_logs(time.time())
                            
        assert len(orphans) == 1
        assert "/tmp/logs/test-app-worker-456.current.log" in orphans[0][0]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_orphaned_logs_alive_process_current_log(self):
        """Test that current logs from alive processes are not considered orphaned."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app", process_name="worker-123")
        
        files = ["test-app-worker-456.current.log"]
        
        with patch('os.listdir', return_value=files):
            with patch.object(service, '_extract_pid_from_process_name', return_value=456):
                with patch.object(service, '_is_process_alive', return_value=True):
                    orphans = await service._scan_for_orphaned_logs(time.time())
                    
        assert len(orphans) == 0

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_orphaned_logs_recent_current_log(self):
        """Test that recent current logs from dead processes are not considered orphaned."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app", process_name="worker-123")
        
        files = ["test-app-worker-456.current.log"]
        
        # Mock file stats (recent file - 5 minutes ago, less than 10 minute threshold)
        mock_stat = Mock()
        mock_stat.st_mtime = time.time() - 300
        
        with patch('os.listdir', return_value=files):
            with patch('os.stat', return_value=mock_stat):
                with patch('os.path.join', side_effect=lambda a, b: f"{a}/{b}"):
                    with patch.object(service, '_extract_pid_from_process_name', return_value=456):
                        with patch.object(service, '_is_process_alive', return_value=False):
                            orphans = await service._scan_for_orphaned_logs(time.time())
                            
        assert len(orphans) == 0

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_orphaned_logs_custom_process_names(self):
        """Test orphan detection with custom (non-worker) process names."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app", process_name="custom-process")
        
        files = [
            "test-app-other-process__2024-01-15.log",  # Orphaned log from custom process
            "test-app-custom-process.current.log"      # Our current log
        ]
        
        # Mock file stats (old file)
        mock_stat = Mock()
        mock_stat.st_mtime = time.time() - 3600
        
        with patch('os.listdir', return_value=files):
            with patch('os.stat', return_value=mock_stat):
                with patch('os.path.join', side_effect=lambda a, b: f"{a}/{b}"):
                    orphans = await service._scan_for_orphaned_logs(time.time())
                    
        assert len(orphans) == 1
        assert "/tmp/logs/test-app-other-process__2024-01-15.log" in orphans[0][0]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_scan_orphaned_logs_skips_already_processed(self):
        """Test that already processed orphaned files are skipped."""
        service = LogMonitorService(logs_dir="/tmp/logs", app_name="test-app", process_name="worker-123")
        
        # Add orphaned file to processed set
        orphaned_file = "/tmp/logs/test-app-worker-456__2024-01-15.log"
        service._processed_files.add(orphaned_file)
        
        files = ["test-app-worker-456__2024-01-15.log"]
        
        with patch('os.listdir', return_value=files):
            with patch('os.path.join', return_value=orphaned_file):
                orphans = await service._scan_for_orphaned_logs(time.time())
                
        assert len(orphans) == 0


class TestLogMonitorServiceMonitorLoop:
    """Test the _monitor_loop background task."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_monitor_loop_normal_operation(self):
        """Test normal monitor loop operation with periodic scanning."""
        service = LogMonitorService(logs_dir="/tmp/logs", scan_interval=0.1)
        service._running = True
        
        scan_count = 0
        async def mock_scan():
            nonlocal scan_count
            scan_count += 1
            if scan_count >= 2:  # Stop after 2 scans
                service._running = False
        
        with patch.object(service, '_scan_for_rotated_logs', side_effect=mock_scan):
            with patch('asyncio.sleep') as mock_sleep:
                await service._monitor_loop()
                
        assert scan_count == 2
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(0.1)

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_monitor_loop_cancellation(self):
        """Test monitor loop handles cancellation gracefully."""
        service = LogMonitorService(logs_dir="/tmp/logs", scan_interval=0.1)
        service._running = True
        
        async def mock_scan():
            # Simulate cancellation during scan
            raise asyncio.CancelledError()
        
        with patch.object(service, '_scan_for_rotated_logs', side_effect=mock_scan):
            # Should exit gracefully without raising
            await service._monitor_loop()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_monitor_loop_exception_handling(self):
        """Test monitor loop handles exceptions and continues."""
        service = LogMonitorService(logs_dir="/tmp/logs", scan_interval=0.1)
        service._running = True
        
        scan_count = 0
        async def mock_scan():
            nonlocal scan_count
            scan_count += 1
            if scan_count == 1:
                raise Exception("Scan failed")
            elif scan_count >= 2:
                service._running = False  # Stop after recovery
        
        with patch.object(service, '_scan_for_rotated_logs', side_effect=mock_scan):
            with patch('asyncio.sleep') as mock_sleep:
                await service._monitor_loop()
                
        assert scan_count == 2  # Should have retried after exception
        # Should have called sleep after exception (5 seconds) and normal interval (0.1)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(5)  # Error recovery sleep
        mock_sleep.assert_any_call(0.1)  # Normal interval

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_monitor_loop_not_running(self):
        """Test monitor loop exits immediately when not running."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        service._running = False
        
        with patch.object(service, '_scan_for_rotated_logs') as mock_scan:
            await service._monitor_loop()
            
        # Should not have called scan since not running
        mock_scan.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_monitor_loop_stop_during_execution(self):
        """Test monitor loop can be stopped during execution."""
        service = LogMonitorService(logs_dir="/tmp/logs", scan_interval=0.1)
        service._running = True
        
        scan_count = 0
        async def mock_scan():
            nonlocal scan_count
            scan_count += 1
            # Stop the service during the first scan
            service._running = False
        
        with patch.object(service, '_scan_for_rotated_logs', side_effect=mock_scan):
            with patch('asyncio.sleep') as mock_sleep:
                await service._monitor_loop()
                
        assert scan_count == 1
        # Sleep is called once after the scan, then loop exits on next iteration
        mock_sleep.assert_called_once_with(0.1)


class TestLogMonitorServiceShutdown:
    """Test the shutdown method."""
    
    class AwaitableTaskMock:
        """A mock task that can be awaited and has done/cancel methods."""
        
        def __init__(self, is_done=False, cancel_effect=None):
            self.is_done = is_done
            self.cancel_effect = cancel_effect
            self.cancel = Mock()
            
        def done(self):
            return self.is_done
            
        def __await__(self):
            async def async_method():
                if self.cancel_effect:
                    raise self.cancel_effect
            return async_method().__await__()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_shutdown_not_running(self):
        """Test shutdown when service is not running."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        service._running = False
        
        # Should return early without doing anything
        await service.shutdown()
        
        # State should remain unchanged
        assert service._running is False

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_shutdown_basic_no_uploader(self):
        """Test basic shutdown without uploader."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        service._running = True
        service.uploader = None
        
        await service.shutdown()
        
        assert service._running is False

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_shutdown_with_monitor_task(self):
        """Test shutdown with active monitor task."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        service._running = True
        
        # Create an awaitable mock task that's not done
        mock_task = self.AwaitableTaskMock(is_done=False, cancel_effect=asyncio.CancelledError())
        service._monitor_task = mock_task
        
        await service.shutdown()
        
        assert service._running is False
        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_shutdown_with_completed_monitor_task(self):
        """Test shutdown when monitor task is already completed."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        service._running = True
        
        # Create a mock completed monitor task
        mock_task = self.AwaitableTaskMock(is_done=True)
        service._monitor_task = mock_task
        
        await service.shutdown()
        
        assert service._running is False
        mock_task.cancel.assert_not_called()  # Should not cancel completed task

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_shutdown_with_final_scan(self):
        """Test shutdown performs final scan when uploader is present."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        service._running = True
        service.uploader = AsyncMock()
        
        with patch.object(service, '_scan_for_rotated_logs') as mock_scan:
            await service.shutdown()
            
        assert service._running is False
        mock_scan.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_shutdown_with_uploader(self):
        """Test shutdown properly shuts down uploader."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        service._running = True
        
        mock_uploader = AsyncMock()
        service.uploader = mock_uploader
        
        with patch.object(service, '_scan_for_rotated_logs'):
            await service.shutdown()
            
        assert service._running is False
        mock_uploader.shutdown.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_shutdown_task_cancellation_exception(self):
        """Test shutdown handles task cancellation exceptions gracefully."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        service._running = True
        
        # Create a mock task that raises CancelledError when awaited
        mock_task = self.AwaitableTaskMock(is_done=False, cancel_effect=asyncio.CancelledError())
        service._monitor_task = mock_task
        
        # Should not raise exception
        await service.shutdown()
        
        assert service._running is False
        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_shutdown_complete_workflow(self):
        """Test complete shutdown workflow with all components."""
        service = LogMonitorService(logs_dir="/tmp/logs")
        service._running = True
        
        mock_uploader = AsyncMock()
        service.uploader = mock_uploader
        
        # Create a mock task 
        mock_task = self.AwaitableTaskMock(is_done=False, cancel_effect=asyncio.CancelledError())
        service._monitor_task = mock_task
        
        with patch.object(service, '_scan_for_rotated_logs') as mock_scan:
            await service.shutdown()
            
        # Verify all shutdown steps occurred in order
        assert service._running is False
        mock_task.cancel.assert_called_once()
        mock_scan.assert_called_once()
        mock_uploader.shutdown.assert_called_once() 