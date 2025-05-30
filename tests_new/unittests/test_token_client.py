"""
Comprehensive unit tests for common_new.token_client module.
"""
import pytest
import aiohttp
import time
from unittest.mock import AsyncMock, Mock, patch
from common_new.token_client import TokenClient


class TestTokenClientInit:
    """Test TokenClient initialization."""
    
    @pytest.mark.unit
    def test_init_with_defaults(self):
        """Test initialization with default base URL."""
        with patch('common_new.token_client.BASE_URL', 'http://test.com'):
            client = TokenClient(app_id="test_app")
            assert client.app_id == "test_app"
            assert client.base_url == "http://test.com"
    
    @pytest.mark.unit
    def test_init_with_custom_base_url(self):
        """Test initialization with custom base URL."""
        client = TokenClient(app_id="test_app", base_url="http://custom.com/")
        assert client.app_id == "test_app"
        assert client.base_url == "http://custom.com"  # Trailing slash should be stripped
    
    @pytest.mark.unit
    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is stripped from base URL."""
        client = TokenClient(app_id="test_app", base_url="http://test.com/api/")
        assert client.base_url == "http://test.com/api"


class TestTokenClientLockTokens:
    """Test the lock_tokens method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_tokens_success(self):
        """Test successful token locking."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "allowed": True,
            "request_id": "req_123"
        }
        
        mock_session = AsyncMock()
        mock_session.post.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            # Act
            allowed, request_id, error = await client.lock_tokens(100)
            
            # Assert
            assert allowed is True
            assert request_id == "req_123"
            assert error is None
            
            mock_session.post.assert_called_once_with(
                "http://test.com/lock",
                json={"app_id": "test_app", "token_count": 100}
            )
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_tokens_denied(self):
        """Test token locking when request is denied."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.json.return_value = {
            "allowed": False,
            "message": "Rate limit exceeded"
        }
        
        mock_session = AsyncMock()
        mock_session.post.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            # Act
            allowed, request_id, error = await client.lock_tokens(100)
            
            # Assert
            assert allowed is False
            assert request_id is None
            assert error == "Rate limit exceeded"
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_tokens_http_error(self):
        """Test token locking with HTTP error."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        mock_session = AsyncMock()
        mock_session.post.side_effect = aiohttp.ClientError("Connection error")
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            # Act
            allowed, request_id, error = await client.lock_tokens(100)
            
            # Assert
            assert allowed is False
            assert request_id is None
            assert "Client error: Connection error" in error
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_tokens_response_missing_fields(self):
        """Test token locking when response is missing fields."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {}  # Missing allowed and request_id
        
        mock_session = AsyncMock()
        mock_session.post.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            # Act
            allowed, request_id, error = await client.lock_tokens(100)
            
            # Assert
            assert allowed is False
            assert request_id is None
            assert error == "Unknown error"


class TestTokenClientReportUsage:
    """Test the report_usage method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_usage_success(self):
        """Test successful usage reporting."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        mock_response = AsyncMock()
        mock_response.status = 200
        
        mock_session = AsyncMock()
        mock_session.post.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            # Act
            result = await client.report_usage("req_123", 50, 25)
            
            # Assert
            assert result is True
            mock_session.post.assert_called_once_with(
                "http://test.com/report",
                json={
                    "app_id": "test_app",
                    "request_id": "req_123",
                    "prompt_tokens": 50,
                    "completion_tokens": 25
                }
            )
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_usage_with_rate_request_id(self):
        """Test usage reporting with compound request ID."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        mock_response = AsyncMock()
        mock_response.status = 200
        
        mock_session = AsyncMock()
        mock_session.post.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            # Act
            result = await client.report_usage("token_123:rate_456", 50, 25)
            
            # Assert
            assert result is True
            mock_session.post.assert_called_once_with(
                "http://test.com/report",
                json={
                    "app_id": "test_app",
                    "request_id": "token_123",
                    "rate_request_id": "rate_456",
                    "prompt_tokens": 50,
                    "completion_tokens": 25
                }
            )
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_usage_http_error(self):
        """Test usage reporting with HTTP error."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        mock_session = AsyncMock()
        mock_session.post.side_effect = aiohttp.ClientError("Connection error")
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            # Act
            result = await client.report_usage("req_123", 50, 25)
            
            # Assert
            assert result is False
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_usage_server_error(self):
        """Test usage reporting with server error response."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        mock_response = AsyncMock()
        mock_response.status = 500
        
        mock_session = AsyncMock()
        mock_session.post.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            # Act
            result = await client.report_usage("req_123", 50, 25)
            
            # Assert
            assert result is False


class TestTokenClientReleaseTokens:
    """Test the release_tokens method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_release_tokens_success(self):
        """Test successful token release."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        mock_response = AsyncMock()
        mock_response.status = 200
        
        mock_session = AsyncMock()
        mock_session.post.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            # Act
            result = await client.release_tokens("req_123")
            
            # Assert
            assert result is True
            mock_session.post.assert_called_once_with(
                "http://test.com/release",
                json={
                    "app_id": "test_app",
                    "request_id": "req_123"
                }
            )
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_release_tokens_with_rate_request_id(self):
        """Test token release with compound request ID."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        mock_response = AsyncMock()
        mock_response.status = 200
        
        mock_session = AsyncMock()
        mock_session.post.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            # Act
            result = await client.release_tokens("token_123:rate_456")
            
            # Assert
            assert result is True
            mock_session.post.assert_called_once_with(
                "http://test.com/release",
                json={
                    "app_id": "test_app",
                    "request_id": "token_123",
                    "rate_request_id": "rate_456"
                }
            )
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_release_tokens_http_error(self):
        """Test token release with HTTP error."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        mock_session = AsyncMock()
        mock_session.post.side_effect = Exception("Network error")
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            # Act
            result = await client.release_tokens("req_123")
            
            # Assert
            assert result is False


class TestTokenClientGetStatus:
    """Test the get_status method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_status_success(self):
        """Test successful status retrieval."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "available_tokens": 1000,
            "used_tokens": 500,
            "available_requests": 100,
            "reset_time_seconds": 3600
        }
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            with patch('time.time', return_value=1234567890.0):
                # Act
                status = await client.get_status()
                
                # Assert
                assert status is not None
                assert status["available_tokens"] == 1000
                assert status["used_tokens"] == 500
                assert status["available_requests"] == 100
                assert status["reset_time_seconds"] == 3600
                assert status["client_app_id"] == "test_app"
                assert status["client_timestamp"] == 1234567890.0
                
                mock_session.get.assert_called_once_with("http://test.com/status")
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_status_http_error(self):
        """Test status retrieval with HTTP error."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        mock_session = AsyncMock()
        mock_session.get.side_effect = Exception("Connection error")
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            # Act
            status = await client.get_status()
            
            # Assert
            assert status is None
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_status_server_error(self):
        """Test status retrieval with server error response."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        mock_response = AsyncMock()
        mock_response.status = 500
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            # Act
            status = await client.get_status()
            
            # Assert
            assert status is None
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_status_minimal_response(self):
        """Test status retrieval with minimal response data."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {}  # Empty response
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            with patch('time.time', return_value=1234567890.0):
                # Act
                status = await client.get_status()
                
                # Assert
                assert status is not None
                assert status["client_app_id"] == "test_app"
                assert status["client_timestamp"] == 1234567890.0


class TestTokenClientIntegration:
    """Integration tests for TokenClient functionality."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_full_token_lifecycle(self):
        """Test complete token usage lifecycle."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        # Mock responses for different endpoints
        lock_response = AsyncMock()
        lock_response.status = 200
        lock_response.json.return_value = {"allowed": True, "request_id": "req_123"}
        
        report_response = AsyncMock()
        report_response.status = 200
        
        release_response = AsyncMock()
        release_response.status = 200
        
        mock_session = AsyncMock()
        mock_session.post.return_value.__aenter__.side_effect = [
            lock_response,
            report_response,
            release_response
        ]
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            # Act - Lock tokens
            allowed, request_id, error = await client.lock_tokens(100)
            assert allowed is True
            assert request_id == "req_123"
            
            # Act - Report usage
            report_success = await client.report_usage(request_id, 75, 25)
            assert report_success is True
            
            # Act - Release tokens (shouldn't be needed after report, but testing)
            release_success = await client.release_tokens(request_id)
            assert release_success is True
            
            # Assert all calls were made
            assert mock_session.post.call_count == 3 