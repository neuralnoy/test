"""
Comprehensive unit tests for common_new.token_client module.
"""
import pytest
import aiohttp
import time
from unittest.mock import patch
from aioresponses import aioresponses
from common_new.token_client import TokenClient
import asyncio
import aiohttp.web


class TestTokenClientInit:
    """Test TokenClient initialization."""
    
    @pytest.mark.unit
    def test_init_with_defaults(self):
        """Test initialization with default base URL."""
        # Mock os.getenv to return a test URL for COUNTER_APP_BASE_URL
        with patch('common_new.token_client.os.getenv') as mock_getenv:
            mock_getenv.return_value = "http://test.com"
            # Reload the module to pick up the mocked environment
            import importlib
            from common_new import token_client
            importlib.reload(token_client)
            client = token_client.TokenClient(app_id="test_app")
            assert client.app_id == "test_app"
            assert client.base_url == "http://test.com"
            # Verify that os.getenv was called with the right parameter
            mock_getenv.assert_called_with("COUNTER_APP_BASE_URL")
    
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
        # Mock os.getenv to return None for COUNTER_APP_BASE_URL
        with patch('common_new.token_client.os.getenv') as mock_getenv:
            mock_getenv.return_value = None
            # Reload the module to pick up the mocked environment
            import importlib
            from common_new import token_client
            importlib.reload(token_client)
            client = token_client.TokenClient(app_id="test_app")
            assert client.app_id == "test_app"
            assert client.base_url == "None"  # str(None) when env var is not set
            # Verify that os.getenv was called with the right parameter
            mock_getenv.assert_called_with("COUNTER_APP_BASE_URL")
    
    @pytest.mark.unit
    def test_init_with_empty_base_url_env(self):
        """Test initialization when BASE_URL environment variable is empty."""
        # Mock os.getenv to return empty string for COUNTER_APP_BASE_URL
        with patch('common_new.token_client.os.getenv') as mock_getenv:
            mock_getenv.return_value = ""
            # Reload the module to pick up the mocked environment
            import importlib
            from common_new import token_client
            importlib.reload(token_client)
            client = token_client.TokenClient(app_id="test_app")
            assert client.app_id == "test_app"
            assert client.base_url == ""
            # Verify that os.getenv was called with the right parameter
            mock_getenv.assert_called_with("COUNTER_APP_BASE_URL")
    
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
            assert error == "Request failed"
    
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
            assert error == "Request failed"

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
            assert error == "Request failed"

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
            assert error == "Request failed"

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
            assert error == "Request failed"

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
            assert error == "Request failed"

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

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_tokens_retry_on_timeout(self):
        """Test that the client retries on a timeout."""
        client = TokenClient(app_id="test_app", base_url="http://test.com")

        with aioresponses() as mock:
            # Fail first time with timeout
            mock.post("http://test.com/lock", exception=asyncio.TimeoutError())
            # Succeed second time
            mock.post("http://test.com/lock", payload={"allowed": True, "request_id": "req_123"})

            allowed, request_id, error = await client.lock_tokens(100)

            assert allowed is True
            assert request_id == "req_123"
            assert error is None


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
                    "available_tokens": 100000,
                    "used_tokens": 50000,
                    "locked_tokens": 10000,
                    "available_requests": 99,
                    "reset_time_seconds": 3600
                },
                status=200
            )
            
            with patch('time.time', return_value=1234567890.0):
                # Act
                status = await client.get_status()
                
                # Assert
                assert status is not None
                assert status["available_tokens"] == 100000
                assert status["used_tokens"] == 50000
                assert status["locked_tokens"] == 10000
                assert status["available_requests"] == 99
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
                assert status is None


class TestTokenClientLockEmbeddingTokens:
    """Test the lock_embedding_tokens method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_embedding_tokens_success(self):
        """Test successful embedding token locking."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/embedding/lock",
                payload={"allowed": True, "request_id": "emb_req_123"},
                status=200
            )
            
            # Act
            allowed, request_id, error = await client.lock_embedding_tokens(1000)
            
            # Assert
            assert allowed is True
            assert request_id == "emb_req_123"
            assert error is None
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_embedding_tokens_denied(self):
        """Test embedding token locking when request is denied."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/embedding/lock",
                payload={"allowed": False, "message": "Embedding token limit exceeded"},
                status=429
            )
            
            # Act
            allowed, request_id, error = await client.lock_embedding_tokens(1000)
            
            # Assert
            assert allowed is False
            assert request_id is None
            assert error == "Embedding token limit exceeded"
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_embedding_tokens_http_error(self):
        """Test embedding token locking with HTTP error."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/embedding/lock",
                exception=aiohttp.ClientError("Connection error")
            )
            
            # Act
            allowed, request_id, error = await client.lock_embedding_tokens(1000)
            
            # Assert
            assert allowed is False
            assert request_id is None
            assert error == "Request failed"
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_embedding_tokens_missing_fields(self):
        """Test embedding token locking when response is missing fields."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/embedding/lock",
                payload={},  # Missing allowed and request_id
                status=200
            )
            
            # Act
            allowed, request_id, error = await client.lock_embedding_tokens(1000)
            
            # Assert
            assert allowed is False
            assert request_id is None
            assert error == "Request failed"


class TestTokenClientReportEmbeddingUsage:
    """Test the report_embedding_usage method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_embedding_usage_success(self):
        """Test successful embedding usage reporting."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/embedding/report",
                status=200
            )
            
            # Act
            result = await client.report_embedding_usage("emb_req_123", 500)
            
            # Assert
            assert result is True
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_embedding_usage_http_error(self):
        """Test embedding usage reporting with HTTP error."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/embedding/report",
                exception=aiohttp.ClientError("Connection error")
            )
            
            # Act
            result = await client.report_embedding_usage("emb_req_123", 500)
            
            # Assert
            assert result is False
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_embedding_usage_server_error(self):
        """Test embedding usage reporting with server error response."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/embedding/report",
                status=500
            )
            
            # Act
            result = await client.report_embedding_usage("emb_req_123", 500)
            
            # Assert
            assert result is False

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_embedding_usage_with_rate_request_id(self):
        """Test successful embedding usage reporting with a composite request_id."""
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        with aioresponses() as mock:
            mock.post("http://test.com/embedding/report", status=200)
            result = await client.report_embedding_usage("emb_req_123:rate_456", 500)
            assert result is True
            mock.assert_called_once_with(
                url="http://test.com/embedding/report",
                method='POST',
                json={
                    'app_id': 'test_app',
                    'request_id': 'emb_req_123',
                    'rate_request_id': 'rate_456',
                    'prompt_tokens': 500
                }
            )


class TestTokenClientReleaseEmbeddingTokens:
    """Test the release_embedding_tokens method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_release_embedding_tokens_success(self):
        """Test successful embedding token release."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/embedding/release",
                status=200
            )
            
            # Act
            result = await client.release_embedding_tokens("emb_req_123")
            
            # Assert
            assert result is True
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_release_embedding_tokens_http_error(self):
        """Test embedding token release with HTTP error."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.post(
                "http://test.com/embedding/release",
                exception=Exception("Network error")
            )
            
            # Act
            result = await client.release_embedding_tokens("emb_req_123")
            
            # Assert
            assert result is False

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_release_embedding_tokens_with_rate_request_id(self):
        """Test successful embedding token release with a composite request_id."""
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        with aioresponses() as mock:
            mock.post("http://test.com/embedding/release", status=200)

            result = await client.release_embedding_tokens("emb_req_123:rate_456")

            assert result is True
            mock.assert_called_once_with(
                url="http://test.com/embedding/release",
                method='POST',
                json={
                    'app_id': 'test_app',
                    'request_id': 'emb_req_123',
                    'rate_request_id': 'rate_456'
                }
            )


class TestTokenClientGetEmbeddingStatus:
    """Test the get_embedding_status method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_embedding_status_success(self):
        """Test successful embedding status retrieval."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.get(
                "http://test.com/embedding/status",
                payload={
                    "available_tokens": 50000,
                    "used_tokens": 10000,
                    "locked_tokens": 5000,
                    "reset_time_seconds": 2400
                },
                status=200
            )
            
            with patch('time.time', return_value=1234567890.0):
                # Act
                status = await client.get_embedding_status()
                
                # Assert
                assert status is not None
                assert status["available_tokens"] == 50000
                assert status["used_tokens"] == 10000
                assert status["locked_tokens"] == 5000
                assert status["reset_time_seconds"] == 2400
                assert status["client_app_id"] == "test_app"
                assert status["client_timestamp"] == 1234567890.0
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_embedding_status_http_error(self):
        """Test embedding status retrieval with HTTP error."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.get(
                "http://test.com/embedding/status",
                exception=Exception("Connection error")
            )
            
            # Act
            status = await client.get_embedding_status()
            
            # Assert
            assert status is None
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_embedding_status_server_error(self):
        """Test embedding status retrieval with server error response."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            mock.get(
                "http://test.com/embedding/status",
                status=500
            )
            
            # Act
            status = await client.get_embedding_status()
            
            # Assert
            assert status is None
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_embedding_status_minimal_response(self):
        """Test embedding status retrieval with minimal response data."""
        # Arrange
        client = TokenClient(app_id="test_app", base_url="http://test.com")
    
        with aioresponses() as mock:
            mock.get(
                "http://test.com/embedding/status",
                payload={},  # Empty response
                status=200
            )
    
            with patch('time.time', return_value=1234567890.0):
                # Act
                status = await client.get_embedding_status()
    
                # Assert
                assert status is None


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
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_full_embedding_lifecycle(self):
        """Test the full lifecycle of locking, reporting, and releasing embedding tokens."""
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        
        with aioresponses() as mock:
            # Lock
            mock.post("http://test.com/embedding/lock", payload={"allowed": True, "request_id": "emb_req_789"})
            allowed, request_id, _ = await client.lock_embedding_tokens(2000)
            assert allowed and request_id == "emb_req_789"
            
            # Report
            mock.post("http://test.com/embedding/report", status=200)
            report_success = await client.report_embedding_usage(request_id, 1800)
            assert report_success
            
            # Release (should not be needed if reported)
            mock.post("http://test.com/embedding/release", status=200)
            release_success = await client.release_embedding_tokens(request_id)
            assert release_success


class TestTokenClientWhisper:
    """Test the Whisper rate limiting methods."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_whisper_rate_success(self):
        """Test successful whisper rate locking."""
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        with aioresponses() as mock:
            mock.post("http://test.com/whisper/lock", payload={"allowed": True, "request_id": "whisper_req_123"})
            allowed, request_id, error = await client.lock_whisper_rate()
            assert allowed is True
            assert request_id == "whisper_req_123"
            assert error is None

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_whisper_rate_denied(self):
        """Test whisper rate locking when denied."""
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        with aioresponses() as mock:
            mock.post("http://test.com/whisper/lock", payload={"allowed": False, "message": "Whisper rate limit exceeded"}, status=200)
            allowed, request_id, error = await client.lock_whisper_rate()
            assert allowed is False
            assert request_id is None
            assert error == "Whisper rate limit exceeded"
            
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_whisper_rate_denied_no_message(self):
        """Test whisper rate locking when denied with no message."""
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        with aioresponses() as mock:
            mock.post("http://test.com/whisper/lock", payload={"allowed": False}, status=200)
            allowed, request_id, error = await client.lock_whisper_rate()
            assert allowed is False
            assert request_id is None
            assert error == "Whisper rate limit exceeded"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_lock_whisper_rate_http_error(self):
        """Test whisper rate locking with HTTP error."""
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        with aioresponses() as mock:
            mock.post("http://test.com/whisper/lock", exception=aiohttp.ClientError("Connection error"))
            allowed, request_id, error = await client.lock_whisper_rate()
            assert allowed is False
            assert request_id is None
            assert error == "Request failed"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_whisper_usage_success(self):
        """Test successful whisper usage reporting."""
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        with aioresponses() as mock:
            mock.post("http://test.com/whisper/report", status=200)
            result = await client.report_whisper_usage("whisper_req_123")
            assert result is True

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_report_whisper_usage_http_error(self):
        """Test whisper usage reporting with HTTP error."""
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        with aioresponses() as mock:
            mock.post("http://test.com/whisper/report", exception=aiohttp.ClientError("Connection error"))
            result = await client.report_whisper_usage("whisper_req_123")
            assert result is False

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_release_whisper_rate_success(self):
        """Test successful whisper rate release."""
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        with aioresponses() as mock:
            mock.post("http://test.com/whisper/release", status=200)
            result = await client.release_whisper_rate("whisper_req_123")
            assert result is True

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_release_whisper_rate_http_error(self):
        """Test whisper rate release with HTTP error."""
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        with aioresponses() as mock:
            mock.post("http://test.com/whisper/release", exception=aiohttp.ClientError("Connection error"))
            result = await client.release_whisper_rate("whisper_req_123")
            assert result is False

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_whisper_status_success(self):
        """Test successful whisper status retrieval."""
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        with aioresponses() as mock:
            payload = {
                "available_requests": 10,
                "reset_time_seconds": 50
            }
            mock.get("http://test.com/whisper/status", payload=payload)
            with patch('time.time', return_value=1234567890.0):
                status = await client.get_whisper_status()
                assert status is not None
                assert status["available_requests"] == 10
                assert status["reset_time_seconds"] == 50
                assert status["client_app_id"] == "test_app"
                assert status["client_timestamp"] == 1234567890.0

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_whisper_status_http_error(self):
        """Test whisper status retrieval with HTTP error."""
        client = TokenClient(app_id="test_app", base_url="http://test.com")
        with aioresponses() as mock:
            mock.get("http://test.com/whisper/status", exception=aiohttp.ClientError("Connection error"))
            status = await client.get_whisper_status()
            assert status is None

