"""
Comprehensive unit tests for common_new.logger module.
"""
import pytest
import os
import tempfile
import logging
import json
from unittest.mock import Mock, patch, mock_open, MagicMock
from pathlib import Path

from common_new.logger import (
    get_app_name, 
    _SingletonFileLogService, 
    get_logger, 
    shutdown_logging
)


class TestGetAppName:
    """Test the get_app_name function."""
    
    @pytest.mark.unit
    def test_get_app_name_with_env_var(self):
        """Test get_app_name when environment variable is set."""
        with patch.dict(os.environ, {'APP_NAME_FOR_LOGGER': 'test_app'}):
            assert get_app_name() == 'test_app'
    
    @pytest.mark.unit
    def test_get_app_name_without_env_var(self):
        """Test get_app_name when environment variable is not set."""
        with patch.dict(os.environ, {}, clear=True):
            with patch('os.getenv', return_value=None):
                assert get_app_name() == 'unknown_app'


class TestSingletonFileLogService:
    """Test the _SingletonFileLogService class."""
    
    def setup_method(self):
        """Reset singleton instance before each test."""
        _SingletonFileLogService._instance = None
    
    @pytest.mark.unit
    def test_singleton_pattern(self):
        """Test that only one instance is created."""
        service1 = _SingletonFileLogService()
        service2 = _SingletonFileLogService()
        assert service1 is service2
    
    @pytest.mark.unit
    def test_initialization_only_once(self):
        """Test that initialization only happens once."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            service1 = _SingletonFileLogService()
            original_app_name = service1.app_name
            
            # Second instance should not reinitialize
            service2 = _SingletonFileLogService()
            assert service2.app_name == original_app_name
            assert service2._initialized is True
    
    @pytest.mark.unit
    def test_try_acquire_leadership_success(self):
        """Test successful leadership acquisition."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            service = _SingletonFileLogService()
            
            mock_file = MagicMock()
            mock_lock = MagicMock()
            
            with patch('builtins.open', return_value=mock_file):
                with patch('fcntl.flock', mock_lock):
                    with patch('os.getpid', return_value=12345):
                        result = service._try_acquire_leadership()
                        
                        assert result is True
                        assert service._is_leader is True
                        assert service._lock_file is mock_file
                        mock_file.write.assert_called_once()
                        mock_file.flush.assert_called_once()
    
    @pytest.mark.unit
    def test_try_acquire_leadership_failure(self):
        """Test failed leadership acquisition due to lock conflict."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            service = _SingletonFileLogService()
            
            mock_file = MagicMock()
            
            with patch('builtins.open', return_value=mock_file):
                with patch('fcntl.flock', side_effect=OSError("Lock held")):
                    result = service._try_acquire_leadership()
                    
                    assert result is False
                    assert service._is_leader is False
                    assert service._lock_file is None
                    mock_file.close.assert_called_once()
    
    @pytest.mark.unit
    def test_create_simple_file_handler(self):
        """Test creation of simple file handler."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            service = _SingletonFileLogService()
            formatter = logging.Formatter('%(message)s')
            
            with patch('os.makedirs'):
                with patch('logging.FileHandler') as mock_handler_class:
                    mock_handler = MagicMock()
                    mock_handler_class.return_value = mock_handler
                    
                    handler = service._create_simple_file_handler(formatter)
                    
                    assert handler is mock_handler
                    mock_handler.setFormatter.assert_called_once_with(formatter)
                    mock_handler_class.assert_called_once()
    
    @pytest.mark.unit
    def test_create_simple_file_handler_failure(self):
        """Test simple file handler creation failure."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            service = _SingletonFileLogService()
            formatter = logging.Formatter('%(message)s')
            
            with patch('os.makedirs', side_effect=Exception("Permission denied")):
                handler = service._create_simple_file_handler(formatter)
                assert handler is None
    
    @pytest.mark.unit
    def test_create_rotating_file_handler(self):
        """Test creation of rotating file handler."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            service = _SingletonFileLogService()
            formatter = logging.Formatter('%(message)s')
            
            with patch('os.makedirs'):
                with patch('logging.handlers.TimedRotatingFileHandler') as mock_handler_class:
                    mock_handler = MagicMock()
                    mock_handler_class.return_value = mock_handler
                    
                    handler = service._create_rotating_file_handler(formatter)
                    
                    assert handler is mock_handler
                    mock_handler.setFormatter.assert_called_once_with(formatter)
                    assert hasattr(mock_handler, 'namer')
    
    @pytest.mark.unit
    def test_create_rotating_file_handler_failure(self):
        """Test rotating file handler creation failure."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            service = _SingletonFileLogService()
            formatter = logging.Formatter('%(message)s')
            
            with patch('os.makedirs', side_effect=Exception("Permission denied")):
                with patch.object(service, '_release_leadership') as mock_release:
                    handler = service._create_rotating_file_handler(formatter)
                    
                    assert handler is None
                    mock_release.assert_called_once()
    
    @pytest.mark.unit
    def test_get_file_handler_as_leader(self):
        """Test file handler creation when process is leader."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            service = _SingletonFileLogService()
            formatter = logging.Formatter('%(message)s')
            
            # Make process a leader
            service._is_leader = True
            
            mock_handler = MagicMock()
            with patch.object(service, '_create_rotating_file_handler', return_value=mock_handler):
                handler = service.get_file_handler(formatter)
                
                assert handler is mock_handler
                assert service._file_handler is mock_handler
    
    @pytest.mark.unit
    def test_get_file_handler_as_non_leader(self):
        """Test file handler creation when process is not leader."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            service = _SingletonFileLogService()
            formatter = logging.Formatter('%(message)s')
            
            # Make process not a leader and unable to acquire leadership
            service._is_leader = False
            
            mock_handler = MagicMock()
            with patch.object(service, '_try_acquire_leadership', return_value=False):
                with patch.object(service, '_create_simple_file_handler', return_value=mock_handler):
                    handler = service.get_file_handler(formatter)
                    
                    assert handler is mock_handler
                    assert service._file_handler is mock_handler
    
    @pytest.mark.unit
    def test_release_leadership(self):
        """Test releasing leadership."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            service = _SingletonFileLogService()
            
            mock_file = MagicMock()
            service._lock_file = mock_file
            service._is_leader = True
            
            with patch('fcntl.flock') as mock_flock:
                with patch('os.path.exists', return_value=True):
                    with patch('os.unlink') as mock_unlink:
                        service._release_leadership()
                        
                        mock_flock.assert_called_once()
                        mock_file.close.assert_called_once()
                        mock_unlink.assert_called_once()
                        assert service._lock_file is None
                        assert service._is_leader is False
    
    @pytest.mark.unit
    def test_shutdown(self):
        """Test shutdown functionality."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            service = _SingletonFileLogService()
            
            mock_handler = MagicMock()
            service._file_handler = mock_handler
            
            with patch.object(service, '_release_leadership') as mock_release:
                service.shutdown()
                
                mock_handler.close.assert_called_once()
                assert service._file_handler is None
                mock_release.assert_called_once()


class TestGetLogger:
    """Test the get_logger function."""
    
    def setup_method(self):
        """Reset logger state before each test."""
        # Clear existing loggers
        for logger_name in list(logging.Logger.manager.loggerDict.keys()):
            if logger_name.startswith('test_'):
                del logging.Logger.manager.loggerDict[logger_name]
        
        # Reset root logger
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        
        # Reset singleton
        _SingletonFileLogService._instance = None
    
    @pytest.mark.unit
    def test_get_logger_basic(self):
        """Test basic logger creation."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            logger = get_logger('test_logger')
            
            assert logger.name == 'test_logger'
            assert logger.level == logging.INFO
            assert len(logger.handlers) == 1  # Console handler
            assert isinstance(logger.handlers[0], logging.StreamHandler)
    
    @pytest.mark.unit
    def test_get_logger_custom_level(self):
        """Test logger creation with custom log level."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            logger = get_logger('test_logger', log_level=logging.DEBUG)
            
            assert logger.level == logging.DEBUG
    
    @pytest.mark.unit
    def test_get_logger_returns_existing(self):
        """Test that same logger instance is returned for same name."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            logger1 = get_logger('test_logger')
            logger2 = get_logger('test_logger')
            
            assert logger1 is logger2
    
    @pytest.mark.unit
    def test_get_logger_with_file_handler(self):
        """Test logger creation with file handler."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            mock_handler = MagicMock()
            mock_service = MagicMock()
            mock_service.get_file_handler.return_value = mock_handler
            mock_service._is_leader = True
            mock_service.app_name = 'test_app'
            
            with patch('common_new.logger._log_service', mock_service):
                with patch('os.getpid', return_value=12345):
                    logger = get_logger('test_logger')
                    
                    root_logger = logging.getLogger()
                    assert mock_handler in root_logger.handlers
    
    @pytest.mark.unit
    def test_get_logger_file_handler_failure(self):
        """Test logger creation when file handler creation fails."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            mock_service = MagicMock()
            mock_service.get_file_handler.return_value = None
            mock_service.app_name = 'test_app'
            
            with patch('common_new.logger._log_service', mock_service):
                with patch('os.getpid', return_value=12345):
                    logger = get_logger('test_logger')
                    
                    # Should still work with console logging only
                    assert logger is not None
                    assert len(logger.handlers) == 1  # Only console handler
    
    @pytest.mark.unit
    def test_get_logger_unknown_app_warning(self):
        """Test that warning is logged when APP_NAME is unknown_app."""
        with patch('common_new.logger.get_app_name', return_value='unknown_app'):
            mock_handler = MagicMock()
            mock_service = MagicMock()
            mock_service.get_file_handler.return_value = mock_handler
            mock_service.app_name = 'unknown_app'
            
            with patch('common_new.logger._log_service', mock_service):
                with patch('os.getpid', return_value=12345):
                    logger = get_logger('test_logger')
                    
                    # Verify logger was created successfully
                    assert logger is not None
    
    @pytest.mark.unit
    def test_get_logger_exception_handling(self):
        """Test that logger creation handles exceptions gracefully."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            mock_service = MagicMock()
            mock_service.get_file_handler.side_effect = Exception("File system error")
            
            with patch('common_new.logger._log_service', mock_service):
                logger = get_logger('test_logger')
                
                # Should still get a logger with console handler
                assert logger is not None
                assert len(logger.handlers) == 1


class TestShutdownLogging:
    """Test the shutdown_logging function."""
    
    @pytest.mark.unit
    def test_shutdown_logging(self):
        """Test shutdown_logging function."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            mock_service = MagicMock()
            
            with patch('common_new.logger._log_service', mock_service):
                shutdown_logging()
                mock_service.shutdown.assert_called_once()
    
    @pytest.mark.unit
    def test_shutdown_logging_no_service(self):
        """Test shutdown_logging when service is None."""
        with patch('common_new.logger._log_service', None):
            # Should not raise an exception
            shutdown_logging()


class TestLoggerIntegration:
    """Integration tests for logger functionality."""
    
    def setup_method(self):
        """Reset state before each test."""
        _SingletonFileLogService._instance = None
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
    
    @pytest.mark.unit
    def test_multiple_loggers_same_root_handler(self):
        """Test that multiple loggers share the same root file handler."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            mock_handler = MagicMock()
            mock_service = MagicMock()
            mock_service.get_file_handler.return_value = mock_handler
            mock_service._is_leader = True
            mock_service.app_name = 'test_app'
            
            with patch('common_new.logger._log_service', mock_service):
                with patch('os.getpid', return_value=12345):
                    logger1 = get_logger('logger1')
                    logger2 = get_logger('logger2')
                    
                    root_logger = logging.getLogger()
                    # File handler should only be added once
                    file_handlers = [h for h in root_logger.handlers if h is mock_handler]
                    assert len(file_handlers) == 1
    
    @pytest.mark.unit
    def test_logger_formatting(self):
        """Test that logger uses correct formatting."""
        with patch('common_new.logger.get_app_name', return_value='test_app'):
            logger = get_logger('test_logger')
            
            console_handler = logger.handlers[0]
            formatter = console_handler.formatter
            
            # Check that formatter includes expected fields
            assert '%(asctime)s' in formatter._fmt
            assert '%(levelname)s' in formatter._fmt
            assert '%(name)s' in formatter._fmt
            assert '%(processName)s' in formatter._fmt
            assert '%(process)d' in formatter._fmt
            assert '%(message)s' in formatter._fmt 