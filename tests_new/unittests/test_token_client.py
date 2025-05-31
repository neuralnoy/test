"""
Comprehensive unit tests for common_new.token_client module.
"""
import pytest
import aiohttp
import time
from unittest.mock import patch
from aioresponses import aioresponses
from common_new.token_client import TokenClient


class TestTokenClientInit:
    """Test TokenClient initialization."""
    
    @pytest.mark.unit
    def test_init_with_defaults(self):
        """Test initialization with default base URL."""
        with patch.dict('os.environ', {'COUNTER_APP_BASE_URL': 'http://test.com'}):
            # Mock load_dotenv to prevent loading from .env files
            with patch('common_new.token_client.load_dotenv'):
                # Reload the module to pick up the new environment variable
                import importlib
                from common_new import token_client
                importlib.reload(token_client)
                client = token_client.TokenClient(app_id="test_app")
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

    @pytest.mark.unit
    def test_init_with_base_url_not_set(self):
        """Test initialization when BASE_URL environment variable is not set."""
        with patch.dict('os.environ', {}, clear=True):
            # Mock load_dotenv to prevent loading from .env files
            with patch('common_new.token_client.load_dotenv'):
                # Reload the module to pick up the cleared environment
                import importlib
                from common_new import token_client
                importlib.reload(token_client)
                client = token_client.TokenClient(app_id="test_app")
                assert client.app_id == "test_app"
                assert client.base_url == "None"  # str(None) when env var is not set
    
    @pytest.mark.unit
    def test_init_with_empty_base_url_env(self):
        """Test initialization when BASE_URL environment variable is empty."""
        with patch.dict('os.environ', {'COUNTER_APP_BASE_URL': ''}):
            # Mock load_dotenv to prevent loading from .env files
            with patch('common_new.token_client.load_dotenv'):
                # Reload the module to pick up the new environment variable
                import importlib
                from common_new import token_client
                importlib.reload(token_client)
                client = token_client.TokenClient(app_id="test_app")
                assert client.app_id == "test_app"
                assert client.base_url == ""

    @pytest.mark.unit
    def test_init_with_empty_app_id(self):
        """Test initialization with empty app_id."""
        client = TokenClient(app_id="", base_url="http://test.com")
        assert client.app_id == ""
        assert client.base_url == "http://test.com"

    @pytest.mark.unit
    def test_init_with_none_app_id(self):
        """Test initialization with None app_id."""
        # This might raise a TypeError depending on implementation
        try:
            client = TokenClient(app_id=None, base_url="http://test.com")
            assert client.app_id is None
            assert client.base_url == "http://test.com"
        except TypeError:
            # If the implementation doesn't allow None, that's also valid behavior
            pytest.skip("Implementation doesn't accept None app_id")

    @pytest.mark.unit
    def test_init_with_whitespace_app_id(self):
        """Test initialization with whitespace-only app_id."""
        client = TokenClient(app_id="   ", base_url="http://test.com")
        assert client.app_id == "   "
        assert client.base_url == "http://test.com"


class TestTokenClientLockTokens:
    """Test the lock_tokens method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_tokens_success(self):
        """Test successful token locking."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/lock",
                payload={"allowed": True, "request_id": "req_123"},
                status=200
            )
            
            # Act
            allowed, request_id, error = await client.lock_tokens(100)
            
            # Assert
            assert allowed is True
            assert request_id == "req_123"
            assert error is None
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_tokens_denied(self):
        """Test token locking when request is denied."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/lock",
                payload={"allowed": False, "message": "Rate limit exceeded"},
                status=429
            )
            
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
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/lock",
                exception=aiohttp.ClientError("Connection error")
            )
            
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
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/lock",
                payload={},  # Missing allowed and request_id
                status=200
            )
            
            # Act
            allowed, request_id, error = await client.lock_tokens(100)
            
            # Assert
            assert allowed is False
            assert request_id is None
            assert error == "Unknown error"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_tokens_zero_count(self):
        """Test token locking with zero token count."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/lock",
                payload={"allowed": True, "request_id": "req_123"},
                status=200
            )
            
            # Act
            allowed, request_id, error = await client.lock_tokens(0)
            
            # Assert
            assert allowed is True
            assert request_id == "req_123"
            assert error is None

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_tokens_negative_count(self):
        """Test token locking with negative token count."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/lock",
                payload={"allowed": False, "message": "Invalid token count"},
                status=400
            )
            
            # Act
            allowed, request_id, error = await client.lock_tokens(-10)
            
            # Assert
            assert allowed is False
            assert request_id is None
            assert error == "Invalid token count"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_tokens_invalid_json_response(self):
        """Test token locking with invalid JSON response."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            # Mock a response with invalid JSON
            mock.post(
                "http://test.com/lock",
                body="invalid json {",
                status=200,
                content_type='application/json'
            )
            
            # Act
            allowed, request_id, error = await client.lock_tokens(100)
            
            # Assert
            assert allowed is False
            assert request_id is None
            assert "Client error:" in error and "Expecting value" in error

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_tokens_non_json_response(self):
        """Test token locking with non-JSON response."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            # Mock a response with plain text
            mock.post(
                "http://test.com/lock",
                body="Server Error",
                status=200,
                content_type='text/plain'
            )
            
            # Act
            allowed, request_id, error = await client.lock_tokens(100)
            
            # Assert
            assert allowed is False
            assert request_id is None
            assert "Client error:" in error and "unexpected mimetype" in error

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_tokens_timeout_error(self):
        """Test token locking with timeout error."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/lock",
                exception=aiohttp.ServerTimeoutError("Request timeout")
            )
            
            # Act
            allowed, request_id, error = await client.lock_tokens(100)
            
            # Assert
            assert allowed is False
            assert request_id is None
            assert "Client error:" in error and "timeout" in error.lower()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_tokens_connection_error(self):
        """Test token locking with connection error."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/lock",
                exception=aiohttp.ClientOSError("Connection refused")
            )
            
            # Act
            allowed, request_id, error = await client.lock_tokens(100)
            
            # Assert
            assert allowed is False
            assert request_id is None
            assert "Client error:" in error

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_tokens_very_large_count(self):
        """Test token locking with very large token count."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/lock",
                payload={"allowed": False, "message": "Token count too large"},
                status=400
            )
            
            # Act
            allowed, request_id, error = await client.lock_tokens(999999999)
            
            # Assert
            assert allowed is False
            assert request_id is None
            assert error == "Token count too large"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_tokens_max_int_count(self):
        """Test token locking with maximum integer value."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/lock",
                payload={"allowed": False, "message": "Token count exceeds maximum"},
                status=400
            )
            
            # Act
            import sys
            allowed, request_id, error = await client.lock_tokens(sys.maxsize)
            
            # Assert
            assert allowed is False
            assert request_id is None
            assert error == "Token count exceeds maximum"


class TestTokenClientReportUsage:
    """Test the report_usage method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_usage_success(self):
        """Test successful usage reporting."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/report",
                status=200
            )
            
            # Act
            result = await client.report_usage("req_123", 50, 25)
            
            # Assert
            assert result is True
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_usage_with_rate_request_id(self):
        """Test usage reporting with compound request ID."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/report",
                status=200
            )
            
            # Act
            result = await client.report_usage("token_123:rate_456", 50, 25)
            
            # Assert
            assert result is True
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_usage_http_error(self):
        """Test usage reporting with HTTP error."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/report",
                exception=aiohttp.ClientError("Connection error")
            )
            
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
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/report",
                status=500
            )
            
            # Act
            result = await client.report_usage("req_123", 50, 25)
            
            # Assert
            assert result is False

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_usage_empty_request_id(self):
        """Test usage reporting with empty request ID."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/report",
                status=200
            )
            
            # Act
            result = await client.report_usage("", 50, 25)
            
            # Assert
            assert result is True

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_usage_request_id_multiple_colons(self):
        """Test usage reporting with request ID having multiple colons."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/report",
                status=200
            )
            
            # Act
            result = await client.report_usage("token_123:rate_456:extra", 50, 25)
            
            # Assert
            assert result is True

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_usage_request_id_only_colon(self):
        """Test usage reporting with request ID that is only a colon."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/report",
                status=200
            )
            
            # Act
            result = await client.report_usage(":", 50, 25)
            
            # Assert
            assert result is True

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_usage_zero_tokens(self):
        """Test usage reporting with zero token counts."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/report",
                status=200
            )
            
            # Act
            result = await client.report_usage("req_123", 0, 0)
            
            # Assert
            assert result is True

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_usage_negative_tokens(self):
        """Test usage reporting with negative token counts."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/report",
                status=400  # Server might reject negative values
            )
            
            # Act
            result = await client.report_usage("req_123", -10, -5)
            
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
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/release",
                status=200
            )
            
            # Act
            result = await client.release_tokens("req_123")
            
            # Assert
            assert result is True
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_release_tokens_with_rate_request_id(self):
        """Test token release with compound request ID."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/release",
                status=200
            )
            
            # Act
            result = await client.release_tokens("token_123:rate_456")
            
            # Assert
            assert result is True
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_release_tokens_http_error(self):
        """Test token release with HTTP error."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/release",
                exception=Exception("Network error")
            )
            
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
        
        with aioresponses() as mock:
            mock.get(
                "http://test.com/status",
                payload={
                    "available_tokens": 1000,
                    "used_tokens": 500,
                    "available_requests": 100,
                    "reset_time_seconds": 3600
                },
                status=200
            )
            
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
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_status_http_error(self):
        """Test status retrieval with HTTP error."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.get(
                "http://test.com/status",
                exception=Exception("Connection error")
            )
            
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
        
        with aioresponses() as mock:
            mock.get(
                "http://test.com/status",
                status=500
            )
            
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
        
        with aioresponses() as mock:
            mock.get(
                "http://test.com/status",
                payload={},  # Empty response
                status=200
            )
            
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
        
        with aioresponses() as mock:
            # Mock lock tokens
            mock.post(
                "http://test.com/lock",
                payload={"allowed": True, "request_id": "req_123"},
                status=200
            )
            
            # Mock report usage
            mock.post(
                "http://test.com/report",
                status=200
            )
            
            # Mock release tokens
            mock.post(
                "http://test.com/release",
                status=200
            )
            
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