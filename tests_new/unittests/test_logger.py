"""
Comprehensive unit tests for common_new.logger module.
"""
import pytest
import os
import logging
import sys
from unittest.mock import patch, MagicMock

from common_new.logger import get_app_name, get_logger


class TestGetAppName:
    """Test the get_app_name function."""
    
    @pytest.mark.unit
    def test_get_app_name_without_env_var_defaults_to_unknown_app(self):
        """Test get_app_name when APP_NAME_FOR_LOGGER environment variable is not set."""
        # Clear the environment variable and ensure it returns default
        with patch.dict(os.environ, {}, clear=True):
            # Explicitly mock os.getenv to return None for our specific key
            with patch('os.getenv', return_value='unknown_app') as mock_getenv:
                result = get_app_name()
                
                # Verify the function was called with correct parameters
                mock_getenv.assert_called_once_with('APP_NAME_FOR_LOGGER', 'unknown_app')
                # Verify it returns the default value
                assert result == 'unknown_app'
    
    @pytest.mark.unit
    def test_get_app_name_with_env_var_returns_set_value(self):
        """Test get_app_name when APP_NAME_FOR_LOGGER environment variable is set."""
        test_app_name = 'test_application'
        with patch.dict(os.environ, {'APP_NAME_FOR_LOGGER': test_app_name}):
            result = get_app_name()
            assert result == test_app_name
    
    @pytest.mark.unit
    def test_get_app_name_with_empty_string_env_var(self):
        """Test get_app_name when APP_NAME_FOR_LOGGER environment variable is set to empty string."""
        with patch.dict(os.environ, {'APP_NAME_FOR_LOGGER': ''}):
            result = get_app_name()
            # Should return the empty string, not the default
            assert result == ''
    
    @pytest.mark.unit
    def test_get_app_name_with_special_characters(self):
        """Test get_app_name when APP_NAME_FOR_LOGGER contains special characters."""
        special_chars_cases = [
            'my app',  # spaces
            'app-name',  # hyphens
            'app_name',  # underscores  
            'my/app',  # forward slash
            'my\\app',  # backslash
            'café-app',  # unicode characters
            'app.name',  # dots
            'app@company',  # at symbol
            'app(v1.0)',  # parentheses
        ]
        
        for test_name in special_chars_cases:
            with patch.dict(os.environ, {'APP_NAME_FOR_LOGGER': test_name}):
                result = get_app_name()
                assert result == test_name, f"Failed for special character case: {test_name}"


class TestGetLogger:
    """Test the get_logger function."""
    
    def setup_method(self):
        """Reset logger state before each test."""
        # Clear existing loggers to avoid interference between tests
        logging.Logger.manager.loggerDict.clear()
        
        # Reset root logger handlers - ensure it's completely clean
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        # Also clear the handlers list to be absolutely sure
        root_logger.handlers = []
    
    @pytest.mark.unit
    def test_get_logger_basic_creation_with_defaults(self):
        """Test basic logger creation with default parameters."""
        logger_name = 'test_logger'
        
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            with patch('os.makedirs'):
                with patch('logging.handlers.TimedRotatingFileHandler') as mock_file_handler:
                    # Mock the file handler to avoid actual file creation
                    mock_handler_instance = MagicMock()
                    mock_file_handler.return_value = mock_handler_instance
                    
                    logger = get_logger(logger_name)
                    
                    # Verify logger properties
                    assert logger.name == logger_name
                    assert logger.level == logging.INFO  # Default level
                    
                    # Verify console handler was added
                    assert len(logger.handlers) == 1
                    console_handler = logger.handlers[0]
                    assert isinstance(console_handler, logging.StreamHandler)
                    assert console_handler.stream == sys.stdout
                    
                    # Verify formatter was set on console handler
                    assert console_handler.formatter is not None
                    assert '%(asctime)s' in console_handler.formatter._fmt
                    assert '%(levelname)s' in console_handler.formatter._fmt
                    assert '%(name)s' in console_handler.formatter._fmt
    
    @pytest.mark.unit
    def test_get_logger_with_custom_log_level(self):
        """Test logger creation with custom log level."""
        logger_name = 'test_logger_debug'
        custom_level = logging.DEBUG
        
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            with patch('os.makedirs'):
                with patch('logging.handlers.TimedRotatingFileHandler') as mock_file_handler:
                    # Mock the file handler to avoid actual file creation
                    mock_handler_instance = MagicMock()
                    mock_file_handler.return_value = mock_handler_instance
                    
                    logger = get_logger(logger_name, log_level=custom_level)
                    
                    # Verify logger has custom level
                    assert logger.level == custom_level
                    assert logger.name == logger_name
                    
                    # Verify console handler was still added
                    assert len(logger.handlers) == 1
                    assert isinstance(logger.handlers[0], logging.StreamHandler)
    
    @pytest.mark.unit
    def test_get_logger_same_name_returns_same_instance(self):
        """Test that multiple calls with same logger name return the same instance."""
        logger_name = 'shared_logger'
        
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            with patch('os.makedirs'):
                with patch('logging.handlers.TimedRotatingFileHandler') as mock_file_handler:
                    # Mock the file handler to avoid actual file creation
                    mock_handler_instance = MagicMock()
                    mock_file_handler.return_value = mock_handler_instance
                    
                    # Get the same logger multiple times
                    logger1 = get_logger(logger_name)
                    logger2 = get_logger(logger_name)
                    logger3 = get_logger(logger_name, log_level=logging.DEBUG)  # Even with different level
                    
                    # All should be the same instance
                    assert logger1 is logger2
                    assert logger2 is logger3
                    assert logger1 is logger3
                    
                    # Verify the logger only has handlers from first creation
                    # (not duplicated on subsequent calls)
                    assert len(logger1.handlers) == 1
    
    @pytest.mark.unit
    def test_get_logger_process_name_defaults_when_not_set(self):
        """Test that PROCESS_NAME defaults to worker-{pid} when not set in environment."""
        logger_name = 'test_process_name_unique'  # Use unique name
        test_pid = 12345
        
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            with patch('os.getpid', return_value=test_pid):
                with patch('os.makedirs') as mock_makedirs:
                    # Use the correct import path for TimedRotatingFileHandler
                    with patch('common_new.logger.TimedRotatingFileHandler') as mock_file_handler:
                        with patch.dict(os.environ, {}, clear=True):
                            # Ensure root logger has no handlers
                            root_logger = logging.getLogger()
                            root_logger.handlers = []
                            
                            # Mock the file handler with proper attributes
                            mock_handler_instance = MagicMock()
                            mock_handler_instance.level = logging.INFO  # Set proper level
                            mock_file_handler.return_value = mock_handler_instance
                            
                            # Mock the logger.info call to avoid the comparison issue
                            with patch.object(logging.Logger, 'info') as mock_info:
                                with patch.object(logging.Logger, 'warning') as mock_warning:
                                    logger = get_logger(logger_name)
                                    
                                    # Verify the TimedRotatingFileHandler was called with expected filename
                                    mock_file_handler.assert_called_once()
                                    call_args = mock_file_handler.call_args
                                    filename = call_args[1]['filename']
                                    
                                    # Should contain the default process name format
                                    expected_process_name = f"worker-{test_pid}"
                                    assert expected_process_name in filename
                                    assert filename.endswith('.current.log')
                                    assert 'test_app' in filename
                                    
                                    # Verify logger was created successfully
                                    assert logger is not None
                                    assert logger.name == logger_name
    
    @pytest.mark.unit
    def test_get_logger_process_name_with_special_characters(self):
        """Test that PROCESS_NAME with special characters is handled properly in filename."""
        logger_name = 'test_special_process_name'
        test_pid = 12345
        
        # Test various special characters that might be problematic in filenames
        special_process_names = [
            'worker/with/slashes',     # forward slashes
            'worker\\with\\backslashes', # backslashes  
            'worker:with:colons',      # colons
            'worker<with>brackets',    # angle brackets
            'worker|with|pipes',       # pipe characters
            'worker"with"quotes',      # quotes
            'worker*with*asterisks',   # asterisks
            'worker?with?questions',   # question marks
            'worker with spaces',      # spaces
            'worker.with.dots',        # multiple dots
        ]
        
        for special_name in special_process_names:
            with patch('common_new.logger.get_app_name', return_value='test_app'):
                with patch('os.getpid', return_value=test_pid):
                    with patch('os.makedirs') as mock_makedirs:
                        with patch('common_new.logger.TimedRotatingFileHandler') as mock_file_handler:
                            with patch.dict(os.environ, {'PROCESS_NAME': special_name}):
                                # Reset state for each iteration
                                root_logger = logging.getLogger()
                                root_logger.handlers = []
                                
                                # Mock the file handler with proper attributes
                                mock_handler_instance = MagicMock()
                                mock_handler_instance.level = logging.INFO
                                mock_file_handler.return_value = mock_handler_instance
                                
                                # Mock the logger calls to avoid comparison issues
                                with patch.object(logging.Logger, 'info') as mock_info:
                                    with patch.object(logging.Logger, 'warning') as mock_warning:
                                        logger = get_logger(logger_name + special_name.replace('/', '_'))  # unique name
                                        
                                        # Verify the TimedRotatingFileHandler was called
                                        mock_file_handler.assert_called_once()
                                        call_args = mock_file_handler.call_args
                                        filename = call_args[1]['filename']
                                        
                                        # Should contain the special process name (exactly as set)
                                        assert special_name in filename, f"Process name '{special_name}' not found in filename: {filename}"
                                        assert filename.endswith('.current.log')
                                        assert 'test_app' in filename
                                        
                                        # Reset mock for next iteration
                                        mock_file_handler.reset_mock()
    
    @pytest.mark.unit
    def test_get_logger_logs_directory_creation_fails(self):
        """Test that logger handles logs directory creation failure gracefully."""
        logger_name = 'test_logs_dir_fail'
        
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            with patch('os.getpid', return_value=12345):
                # Mock os.makedirs to raise permission denied error
                with patch('os.makedirs', side_effect=PermissionError("Permission denied")):
                    # Reset state
                    root_logger = logging.getLogger()
                    root_logger.handlers = []
                    
                    # Mock logger methods to capture error handling
                    with patch.object(logging.Logger, 'error') as mock_error:
                        logger = get_logger(logger_name)
                        
                        # Verify logger was still created (with console handler only)
                        assert logger is not None
                        assert logger.name == logger_name
                        assert len(logger.handlers) == 1  # Only console handler
                        assert isinstance(logger.handlers[0], logging.StreamHandler)
                        
                        # Verify root logger has no file handler (due to failure)
                        assert len(root_logger.handlers) == 0
                        
                        # Verify error was logged about the failure
                        mock_error.assert_called_once()
                        error_call_args = mock_error.call_args[0]
                        assert "Failed to configure file logging" in error_call_args[0]
                        assert "Permission denied" in error_call_args[0]


class TestCustomNamerFunction:
    """Test the custom namer function for log rotation."""
    
    def setup_method(self):
        """Reset logger state before each test."""
        logging.Logger.manager.loggerDict.clear()
        root_logger = logging.getLogger()
        root_logger.handlers = []
    
    @pytest.mark.unit
    def test_custom_namer_with_expected_format(self):
        """Test custom namer function with expected filename format."""
        from common_new.logger import get_logger
        
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            with patch('os.getpid', return_value=12345):
                with patch('os.makedirs'):
                    with patch('common_new.logger.TimedRotatingFileHandler') as mock_file_handler:
                        # Reset state
                        root_logger = logging.getLogger()
                        root_logger.handlers = []
                        
                        # Mock the file handler
                        mock_handler_instance = MagicMock()
                        mock_handler_instance.level = logging.INFO
                        mock_file_handler.return_value = mock_handler_instance
                        
                        with patch.object(logging.Logger, 'info'):
                            logger = get_logger('test_namer')
                            
                            # Get the custom namer function that was set
                            mock_file_handler.assert_called_once()
                            handler_instance = mock_file_handler.return_value
                            
                            # The namer should have been set on the handler
                            assert hasattr(handler_instance, 'namer')
                            custom_namer = handler_instance.namer
                            
                            # Test with expected format: appname-worker-PID.current.log.2024-01-15
                            test_filename = "test_app-worker-12345.current.log.2024-01-15"
                            result = custom_namer(test_filename)
                            
                            # Should convert to: appname-worker-PID__2024-01-15.log
                            expected = "test_app-worker-12345__2024-01-15.log"
                            assert result == expected
    
    @pytest.mark.unit 
    def test_custom_namer_with_unexpected_format(self):
        """Test custom namer function with unexpected filename formats."""
        from common_new.logger import get_logger
        
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            with patch('os.getpid', return_value=12345):
                with patch('os.makedirs'):
                    with patch('common_new.logger.TimedRotatingFileHandler') as mock_file_handler:
                        # Reset state  
                        root_logger = logging.getLogger()
                        root_logger.handlers = []
                        
                        # Mock the file handler
                        mock_handler_instance = MagicMock()
                        mock_handler_instance.level = logging.INFO
                        mock_file_handler.return_value = mock_handler_instance
                        
                        with patch.object(logging.Logger, 'info'):
                            logger = get_logger('test_namer_unexpected')
                            
                            # Get the custom namer function
                            custom_namer = mock_file_handler.return_value.namer
                            
                            # Test various unexpected formats (should return unchanged)
                            unexpected_formats = [
                                "simple.log",                    # Too few parts
                                "app.log.date",                  # Missing 'current'
                                "app-worker.txt.2024-01-15",     # Wrong extension before date
                                "app-worker.current.2024-01-15", # Missing .log
                                "",                              # Empty string
                                "no_dots_at_all",               # No dots
                                "app.current.log",              # Missing date
                            ]
                            
                            for unexpected in unexpected_formats:
                                result = custom_namer(unexpected)
                                assert result == unexpected, f"Namer should return unchanged for unexpected format: {unexpected}"
    
    @pytest.mark.unit
    def test_get_logger_unknown_app_warning(self):
        """Test that logger logs warning when APP_NAME_FOR_LOGGER is not set (unknown_app)."""
        logger_name = 'test_unknown_app_warning'
        
        # Ensure APP_NAME_FOR_LOGGER is not set, so get_app_name returns 'unknown_app'
        with patch('common_new.logger.get_app_name', return_value='unknown_app'):
            with patch('os.getpid', return_value=12345):
                with patch('os.makedirs'):
                    with patch('common_new.logger.TimedRotatingFileHandler') as mock_file_handler:
                        # Reset state
                        root_logger = logging.getLogger()
                        root_logger.handlers = []
                        
                        # Mock the file handler
                        mock_handler_instance = MagicMock()
                        mock_handler_instance.level = logging.INFO
                        mock_file_handler.return_value = mock_handler_instance
                        
                        # Mock the logger methods to capture warning
                        with patch.object(logging.Logger, 'info') as mock_info:
                            with patch.object(logging.Logger, 'warning') as mock_warning:
                                logger = get_logger(logger_name)
                                
                                # Verify the warning was logged about unknown_app
                                mock_warning.assert_called_once()
                                warning_call_args = mock_warning.call_args[0]
                                assert "APP_NAME environment variable not set" in warning_call_args[0]
                                assert "unknown_app" in warning_call_args[0]
                                
                                # Verify logger was still created successfully
                                assert logger is not None
                                assert logger.name == logger_name


class TestRaceConditionsAndCorruption:
    """Test race conditions and file corruption scenarios during logging operations."""
    
    def setup_method(self):
        """Reset logger state before each test."""
        logging.Logger.manager.loggerDict.clear()
        root_logger = logging.getLogger()
        root_logger.handlers = []
    
    @pytest.mark.unit
    def test_multiple_processes_creating_loggers_simultaneously(self):
        """Test race condition when multiple processes create loggers at the same time."""
        import threading
        import time
        from concurrent.futures import ThreadPoolExecutor
        
        # Shared state to simulate race condition
        handler_creation_calls = []
        handler_creation_lock = threading.Lock()
        
        def mock_file_handler_with_delay(*args, **kwargs):
            """Mock TimedRotatingFileHandler that introduces delay to simulate race condition."""
            with handler_creation_lock:
                handler_creation_calls.append(kwargs.get('filename', 'unknown'))
            
            # Simulate file creation delay that could cause race conditions
            time.sleep(0.01)
            
            mock_handler = MagicMock()
            mock_handler.level = logging.INFO
            return mock_handler
        
        def create_logger_worker(worker_id):
            """Worker function that creates a logger (simulates different process)."""
            logger_name = f'race_test_logger_{worker_id}'
            
            with patch('common_new.logger.get_app_name', return_value='race_test_app'):
                with patch('os.getpid', return_value=12345):
                    with patch('os.makedirs'):
                        with patch('common_new.logger.TimedRotatingFileHandler', side_effect=mock_file_handler_with_delay):
                            # Simulate fresh process by clearing and resetting root logger for each worker
                            root_logger = logging.getLogger()
                            
                            # Temporarily clear root logger to simulate race condition
                            # where each process thinks it's the first to set up logging
                            original_handlers = root_logger.handlers[:]
                            root_logger.handlers = []
                            
                            try:
                                # Mock the logging calls to avoid handler issues
                                with patch.object(logging.Logger, 'info'):
                                    with patch.object(logging.Logger, 'warning'):
                                        logger = get_logger(logger_name)
                                        return logger
                            finally:
                                # Restore original handlers to avoid affecting other workers
                                # (this simulates the race condition where handlers get set)
                                if not original_handlers and root_logger.handlers:
                                    # Keep the handlers that were just added
                                    pass
                                else:
                                    # Restore the state for next worker  
                                    root_logger.handlers = original_handlers
        
        # Simulate multiple processes trying to create loggers simultaneously
        num_workers = 3  # Reduced to make race condition more predictable
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Submit all workers simultaneously to create race condition
            futures = [executor.submit(create_logger_worker, i) for i in range(num_workers)]
            
            # Wait for all workers to complete
            loggers = [future.result() for future in futures]
        
        # Verify all loggers were created successfully
        assert len(loggers) == num_workers
        for i, logger in enumerate(loggers):
            assert logger is not None
            assert logger.name == f'race_test_logger_{i}'
        
        # Verify that file handler creation was attempted
        # In this simulation, each worker should attempt to create a file handler
        # since we're clearing the root logger for each worker
        assert len(handler_creation_calls) >= 1, f"At least one file handler should have been created, got: {len(handler_creation_calls)}"
        
        # Verify all file handler calls used the same filename (consistent naming)
        if handler_creation_calls:
            unique_filenames = set(handler_creation_calls)
            assert len(unique_filenames) == 1, f"Expected consistent filename, got: {unique_filenames}"
    
    @pytest.mark.unit
    def test_file_handler_creation_fails_due_to_file_lock_conflict(self):
        """Test when TimedRotatingFileHandler creation fails due to file being locked by another process."""
        logger_name = 'test_file_lock_conflict'
        
        # Simulate a file lock error (errno 11 or 35 on different systems)
        class FileLockError(OSError):
            def __init__(self):
                super().__init__(11, "Resource temporarily unavailable")  # EAGAIN/EWOULDBLOCK
        
        with patch('common_new.logger.get_app_name', return_value='lock_test_app'):
            with patch('os.getpid', return_value=12345):
                with patch('os.makedirs'):
                    # Mock TimedRotatingFileHandler to raise file lock error
                    with patch('common_new.logger.TimedRotatingFileHandler', side_effect=FileLockError()):
                        # Reset state
                        root_logger = logging.getLogger()
                        root_logger.handlers = []
                        
                        # Mock logger methods to capture error handling
                        with patch.object(logging.Logger, 'error') as mock_error:
                            logger = get_logger(logger_name)
                            
                            # Verify logger was still created (with console handler only)
                            assert logger is not None
                            assert logger.name == logger_name
                            assert len(logger.handlers) == 1  # Only console handler
                            assert isinstance(logger.handlers[0], logging.StreamHandler)
                            
                            # Verify root logger has no file handler (due to lock failure)
                            assert len(root_logger.handlers) == 0
                            
                            # Verify error was logged about the lock failure
                            mock_error.assert_called_once()
                            error_call_args = mock_error.call_args[0]
                            assert "Failed to configure file logging" in error_call_args[0]
                            assert "Resource temporarily unavailable" in error_call_args[0]
    
    @pytest.mark.unit
    def test_custom_namer_with_corrupted_rotation_filename(self):
        """Test custom namer function with corrupted/malformed rotation filenames."""
        from common_new.logger import get_logger
        
        with patch('common_new.logger.get_app_name', return_value='corruption_test_app'):
            with patch('os.getpid', return_value=12345):
                with patch('os.makedirs'):
                    with patch('common_new.logger.TimedRotatingFileHandler') as mock_file_handler:
                        # Reset state
                        root_logger = logging.getLogger()
                        root_logger.handlers = []
                        
                        # Mock the file handler
                        mock_handler_instance = MagicMock()
                        mock_handler_instance.level = logging.INFO
                        mock_file_handler.return_value = mock_handler_instance
                        
                        with patch.object(logging.Logger, 'info'):
                            logger = get_logger('test_corruption_namer')
                            
                            # Get the custom namer function
                            custom_namer = mock_file_handler.return_value.namer
                            
                            # Test various corrupted/malformed filenames that could occur
                            # due to file system corruption, incomplete writes, or race conditions
                            
                            # First, test a few cases manually to verify our understanding
                            test_cases = [
                                # Simple valid case for reference
                                ("app-worker-123.current.log.2024-01-15", "app-worker-123__2024-01-15.log"),
                                
                                # Corruption scenarios that still match the pattern (len >= 4, parts[-2] == 'log')
                                ("app-worker-123.current.log.", "app-worker-123__.log"),  # Empty date
                                ("app-worker-123.current.log.corrupted", "app-worker-123__corrupted.log"),  # Invalid date
                                ("app-worker-123.current.log.2024", "app-worker-123__2024.log"),  # Incomplete date
                                
                                # Corruption scenarios that don't match pattern (should return unchanged)
                                ("simple.log", "simple.log"),  # Too few parts
                                ("app.log.date", "app.log.date"),  # Only 3 parts
                                ("app-worker.txt.2024-01-15", "app-worker.txt.2024-01-15"),  # parts[-2] != 'log'
                                ("", ""),  # Empty string
                                ("no_dots_at_all", "no_dots_at_all"),  # No dots
                            ]
                            
                            for input_name, expected in test_cases:
                                try:
                                    result = custom_namer(input_name)
                                    assert result == expected, f"Namer for {repr(input_name)} expected {repr(expected)}, got {repr(result)}"
                                except Exception as e:
                                    # If an exception occurs, it should be a controlled failure, not a crash
                                    assert False, f"Namer should not crash on input {repr(input_name)}, got exception: {e}"
                            
                            # Test that namer doesn't crash on extreme corruption (binary data, null bytes, etc.)
                            extreme_corruption_cases = [
                                "app\x00worker.current.log.2024-01-15",  # Null bytes
                                "app-worker-123.current.log.2024-01-15\x00garbage",  # Null bytes + garbage
                                "app-worker-123.current.log.2024-01-15" + "\n" + "multiline",  # Newlines
                            ]
                            
                            for corrupted in extreme_corruption_cases:
                                try:
                                    result = custom_namer(corrupted)
                                    # Just verify it doesn't crash - we don't care about the exact output for extreme corruption
                                    assert isinstance(result, str), f"Namer should return string for {repr(corrupted)}, got {type(result)}"
                                except Exception as e:
                                    assert False, f"Namer should not crash on extreme corruption {repr(corrupted)}, got exception: {e}" 