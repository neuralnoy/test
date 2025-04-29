import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import json

from apps.app_counter.services.token_client import TokenClient
from apps.app_counter.models.schemas import TokenResponse

class TestTokenClient:
    """Test suite for the TokenClient class"""

    @pytest.fixture
    def token_client(self):
        """Create a token client instance for testing"""
        with patch('httpx.AsyncClient') as mock_client:
            client = TokenClient(
                counter_api_url="http://localhost:8000",
                app_id="test_app"
            )
            client._http_client = mock_client
            yield client

    @pytest.mark.asyncio
    async def test_lock_tokens_success(self, token_client):
        """Test successfully locking tokens"""
        # Mock the post method to return a successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "allowed": True,
            "request_id": "test-request-id",
            "message": None
        }
        token_client._http_client.post = AsyncMock(return_value=mock_response)
        
        # Call the method
        result = await token_client.lock_tokens(5000)
        
        # Assertions
        token_client._http_client.post.assert_called_once()
        assert result["allowed"] is True
        assert result["request_id"] == "test-request-id"

    @pytest.mark.asyncio
    async def test_lock_tokens_not_allowed(self, token_client):
        """Test locking tokens when not allowed"""
        # Mock the post method to return a not allowed response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "allowed": False,
            "request_id": None,
            "message": "Rate limit exceeded"
        }
        token_client._http_client.post = AsyncMock(return_value=mock_response)
        
        # Call the method
        result = await token_client.lock_tokens(5000)
        
        # Assertions
        token_client._http_client.post.assert_called_once()
        assert result["allowed"] is False
        assert result["message"] == "Rate limit exceeded"

    @pytest.mark.asyncio
    async def test_lock_tokens_http_error(self, token_client):
        """Test handling HTTP errors when locking tokens"""
        # Mock the post method to raise an exception
        token_client._http_client.post = AsyncMock(side_effect=Exception("Connection error"))
        
        # Call the method
        result = await token_client.lock_tokens(5000)
        
        # Assertions
        token_client._http_client.post.assert_called_once()
        assert result["allowed"] is False
        assert "Connection error" in result["message"]

    @pytest.mark.asyncio
    async def test_report_usage_success(self, token_client):
        """Test successfully reporting token usage"""
        # Mock the post method to return a successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        token_client._http_client.post = AsyncMock(return_value=mock_response)
        
        # Call the method
        success = await token_client.report_usage("test-request-id", 2000, 1000)
        
        # Assertions
        token_client._http_client.post.assert_called_once()
        assert success is True

    @pytest.mark.asyncio
    async def test_report_usage_error(self, token_client):
        """Test handling errors when reporting usage"""
        # Mock the post method to return an error response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Invalid request ID"}
        token_client._http_client.post = AsyncMock(return_value=mock_response)
        
        # Call the method
        success = await token_client.report_usage("test-request-id", 2000, 1000)
        
        # Assertions
        token_client._http_client.post.assert_called_once()
        assert success is False

    @pytest.mark.asyncio
    async def test_report_usage_http_error(self, token_client):
        """Test handling HTTP errors when reporting usage"""
        # Mock the post method to raise an exception
        token_client._http_client.post = AsyncMock(side_effect=Exception("Connection error"))
        
        # Call the method
        success = await token_client.report_usage("test-request-id", 2000, 1000)
        
        # Assertions
        token_client._http_client.post.assert_called_once()
        assert success is False

    @pytest.mark.asyncio
    async def test_release_tokens_success(self, token_client):
        """Test successfully releasing tokens"""
        # Mock the post method to return a successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        token_client._http_client.post = AsyncMock(return_value=mock_response)
        
        # Call the method
        success = await token_client.release_tokens("test-request-id")
        
        # Assertions
        token_client._http_client.post.assert_called_once()
        assert success is True

    @pytest.mark.asyncio
    async def test_release_tokens_error(self, token_client):
        """Test handling errors when releasing tokens"""
        # Mock the post method to return an error response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Invalid request ID"}
        token_client._http_client.post = AsyncMock(return_value=mock_response)
        
        # Call the method
        success = await token_client.release_tokens("test-request-id")
        
        # Assertions
        token_client._http_client.post.assert_called_once()
        assert success is False

    @pytest.mark.asyncio
    async def test_release_tokens_http_error(self, token_client):
        """Test handling HTTP errors when releasing tokens"""
        # Mock the post method to raise an exception
        token_client._http_client.post = AsyncMock(side_effect=Exception("Connection error"))
        
        # Call the method
        success = await token_client.release_tokens("test-request-id")
        
        # Assertions
        token_client._http_client.post.assert_called_once()
        assert success is False

    @pytest.mark.asyncio
    async def test_get_status_success(self, token_client):
        """Test successfully getting token counter status"""
        # Mock the get method to return a successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "available_tokens": 90000,
            "used_tokens": 5000,
            "locked_tokens": 5000,
            "reset_time_seconds": 30
        }
        token_client._http_client.get = AsyncMock(return_value=mock_response)
        
        # Call the method
        status = await token_client.get_status()
        
        # Assertions
        token_client._http_client.get.assert_called_once()
        assert status["available_tokens"] == 90000
        assert status["used_tokens"] == 5000
        assert status["locked_tokens"] == 5000
        assert status["reset_time_seconds"] == 30

    @pytest.mark.asyncio
    async def test_get_status_error(self, token_client):
        """Test handling errors when getting status"""
        # Mock the get method to return an error response
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal server error"}
        token_client._http_client.get = AsyncMock(return_value=mock_response)
        
        # Call the method
        status = await token_client.get_status()
        
        # Assertions
        token_client._http_client.get.assert_called_once()
        assert status == {
            "available_tokens": 0,
            "used_tokens": 0,
            "locked_tokens": 0,
            "reset_time_seconds": 0
        }

    @pytest.mark.asyncio
    async def test_get_status_http_error(self, token_client):
        """Test handling HTTP errors when getting status"""
        # Mock the get method to raise an exception
        token_client._http_client.get = AsyncMock(side_effect=Exception("Connection error"))
        
        # Call the method
        status = await token_client.get_status()
        
        # Assertions
        token_client._http_client.get.assert_called_once()
        assert status == {
            "available_tokens": 0,
            "used_tokens": 0,
            "locked_tokens": 0,
            "reset_time_seconds": 0
        }

    @pytest.mark.asyncio
    async def test_request_with_tokens_success(self, token_client):
        """Test successfully making a request with token management"""
        # Mock lock_tokens to succeed
        token_client.lock_tokens = AsyncMock(return_value={
            "allowed": True,
            "request_id": "test-request-id"
        })
        
        # Mock report_usage to succeed
        token_client.report_usage = AsyncMock(return_value=True)
        
        # Create a mock API call that succeeds
        async def mock_api_call(*args, **kwargs):
            return {"result": "success", "tokens": {"prompt": 100, "completion": 50}}
        
        # Call the method
        result = await token_client.request_with_tokens(
            api_call=mock_api_call,
            token_estimate=200,
            api_call_args=["arg1", "arg2"],
            api_call_kwargs={"kwarg1": "value1"}
        )
        
        # Assertions
        token_client.lock_tokens.assert_called_once_with(200)
        token_client.report_usage.assert_called_once_with(
            "test-request-id", 100, 50
        )
        assert result == {"result": "success", "tokens": {"prompt": 100, "completion": 50}}

    @pytest.mark.asyncio
    async def test_request_with_tokens_not_allowed(self, token_client):
        """Test request_with_tokens when tokens are not allowed"""
        # Mock lock_tokens to fail
        token_client.lock_tokens = AsyncMock(return_value={
            "allowed": False,
            "message": "Rate limit exceeded"
        })
        
        # Create a mock API call that shouldn't be called
        async def mock_api_call(*args, **kwargs):
            raise Exception("This shouldn't be called")
        
        # Call the method
        result = await token_client.request_with_tokens(
            api_call=mock_api_call,
            token_estimate=200
        )
        
        # Assertions
        token_client.lock_tokens.assert_called_once_with(200)
        assert result["error"] == "Token limit exceeded: Rate limit exceeded"

    @pytest.mark.asyncio
    async def test_request_with_tokens_api_error(self, token_client):
        """Test request_with_tokens when the API call fails"""
        # Mock lock_tokens to succeed
        token_client.lock_tokens = AsyncMock(return_value={
            "allowed": True,
            "request_id": "test-request-id"
        })
        
        # Mock release_tokens to succeed
        token_client.release_tokens = AsyncMock(return_value=True)
        
        # Create a mock API call that fails
        async def mock_api_call(*args, **kwargs):
            raise Exception("API error")
        
        # Call the method
        result = await token_client.request_with_tokens(
            api_call=mock_api_call,
            token_estimate=200
        )
        
        # Assertions
        token_client.lock_tokens.assert_called_once_with(200)
        token_client.release_tokens.assert_called_once_with("test-request-id")
        assert "error" in result
        assert "API error" in result["error"]

    @pytest.mark.asyncio
    async def test_request_with_tokens_missing_token_info(self, token_client):
        """Test request_with_tokens when API response doesn't include token info"""
        # Mock lock_tokens to succeed
        token_client.lock_tokens = AsyncMock(return_value={
            "allowed": True,
            "request_id": "test-request-id"
        })
        
        # Mock report_usage to succeed
        token_client.report_usage = AsyncMock(return_value=True)
        
        # Create a mock API call that succeeds but doesn't return token info
        async def mock_api_call(*args, **kwargs):
            return {"result": "success"}  # No token info
        
        # Call the method
        result = await token_client.request_with_tokens(
            api_call=mock_api_call,
            token_estimate=200,
            fallback_prompt_tokens=50,
            fallback_completion_tokens=30
        )
        
        # Assertions
        token_client.lock_tokens.assert_called_once_with(200)
        token_client.report_usage.assert_called_once_with(
            "test-request-id", 50, 30
        )
        assert result == {"result": "success"} 