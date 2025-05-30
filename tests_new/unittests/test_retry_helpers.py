"""
Comprehensive unit tests for common_new.retry_helpers module.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from common_new.retry_helpers import with_token_limit_retry, with_token_limit_retry_decorator


class TestWithTokenLimitRetry:
    """Test the with_token_limit_retry function."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_successful_first_attempt(self):
        """Test that function succeeds on first attempt without retry."""
        # Arrange
        mock_func = AsyncMock(return_value="success")
        mock_token_client = Mock()
        
        # Act
        result = await with_token_limit_retry(mock_func, mock_token_client, max_retries=3)
        
        # Assert
        assert result == "success"
        mock_func.assert_called_once()
        mock_token_client.get_status.assert_not_called()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_successful_with_args_kwargs(self):
        """Test that function succeeds with arguments and keyword arguments."""
        # Arrange
        mock_func = AsyncMock(return_value="success_with_args")
        mock_token_client = Mock()
        
        # Act
        result = await with_token_limit_retry(
            mock_func, 
            mock_token_client, 
            3,  # max_retries
            "arg1", 
            "arg2", 
            kwarg1="value1", 
            kwarg2="value2"
        )
        
        # Assert
        assert result == "success_with_args"
        mock_func.assert_called_once_with("arg1", "arg2", kwarg1="value1", kwarg2="value2")
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_token_limit_retry_success(self):
        """Test retry on token limit error that eventually succeeds."""
        # Arrange
        mock_func = AsyncMock()
        mock_func.side_effect = [
            ValueError("Token limit would be exceeded"),
            "success_after_retry"
        ]
        
        mock_token_client = AsyncMock()
        mock_token_client.get_status.return_value = {"reset_time_seconds": 0.1}
        
        # Act
        result = await with_token_limit_retry(mock_func, mock_token_client, max_retries=3)
        
        # Assert
        assert result == "success_after_retry"
        assert mock_func.call_count == 2
        mock_token_client.get_status.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_api_rate_limit_retry_success(self):
        """Test retry on API rate limit error that eventually succeeds."""
        # Arrange
        mock_func = AsyncMock()
        mock_func.side_effect = [
            ValueError("API Rate limit would be exceeded"),
            "success_after_retry"
        ]
        
        mock_token_client = AsyncMock()
        mock_token_client.get_status.return_value = {"reset_time_seconds": 0.1}
        
        # Act
        result = await with_token_limit_retry(mock_func, mock_token_client, max_retries=3)
        
        # Assert
        assert result == "success_after_retry"
        assert mock_func.call_count == 2
        mock_token_client.get_status.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_general_rate_limit_retry_success(self):
        """Test retry on general rate limit error that eventually succeeds."""
        # Arrange
        mock_func = AsyncMock()
        mock_func.side_effect = [
            ValueError("Rate limit would be exceeded"),
            "success_after_retry"
        ]
        
        mock_token_client = AsyncMock()
        mock_token_client.get_status.return_value = {"reset_time_seconds": 0.1}
        
        # Act
        result = await with_token_limit_retry(mock_func, mock_token_client, max_retries=3)
        
        # Assert
        assert result == "success_after_retry"
        assert mock_func.call_count == 2
        mock_token_client.get_status.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_max_retries_exceeded(self):
        """Test that ValueError is raised when max retries are exceeded."""
        # Arrange
        mock_func = AsyncMock()
        mock_func.side_effect = ValueError("Token limit would be exceeded")
        
        mock_token_client = AsyncMock()
        mock_token_client.get_status.return_value = {"reset_time_seconds": 0.1}
        
        # Act & Assert
        with pytest.raises(ValueError, match="Token limit would be exceeded"):
            await with_token_limit_retry(mock_func, mock_token_client, max_retries=2)
        
        assert mock_func.call_count == 2
        assert mock_token_client.get_status.call_count == 1
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_non_rate_limit_value_error_immediate_raise(self):
        """Test that non-rate-limit ValueError is raised immediately."""
        # Arrange
        mock_func = AsyncMock()
        mock_func.side_effect = ValueError("Some other error")
        
        mock_token_client = Mock()
        
        # Act & Assert
        with pytest.raises(ValueError, match="Some other error"):
            await with_token_limit_retry(mock_func, mock_token_client, max_retries=3)
        
        mock_func.assert_called_once()
        mock_token_client.get_status.assert_not_called()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_non_value_error_immediate_raise(self):
        """Test that non-ValueError exceptions are raised immediately."""
        # Arrange
        mock_func = AsyncMock()
        mock_func.side_effect = RuntimeError("Runtime error")
        
        mock_token_client = Mock()
        
        # Act & Assert
        with pytest.raises(RuntimeError, match="Runtime error"):
            await with_token_limit_retry(mock_func, mock_token_client, max_retries=3)
        
        mock_func.assert_called_once()
        mock_token_client.get_status.assert_not_called()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_invalid_token_status_response(self):
        """Test behavior when token client returns invalid status."""
        # Arrange
        mock_func = AsyncMock()
        mock_func.side_effect = ValueError("Token limit would be exceeded")
        
        mock_token_client = AsyncMock()
        mock_token_client.get_status.return_value = None  # Invalid response
        
        # Act & Assert
        with pytest.raises(ValueError, match="Token limit would be exceeded"):
            await with_token_limit_retry(mock_func, mock_token_client, max_retries=3)
        
        mock_func.assert_called_once()
        mock_token_client.get_status.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_token_status_missing_reset_time(self):
        """Test behavior when token status is missing reset_time_seconds."""
        # Arrange
        mock_func = AsyncMock()
        mock_func.side_effect = ValueError("Token limit would be exceeded")
        
        mock_token_client = AsyncMock()
        mock_token_client.get_status.return_value = {"available_tokens": 0}  # Missing reset_time_seconds
        
        # Act & Assert
        with pytest.raises(ValueError, match="Token limit would be exceeded"):
            await with_token_limit_retry(mock_func, mock_token_client, max_retries=3)
        
        mock_func.assert_called_once()
        mock_token_client.get_status.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_last_attempt_no_retry(self):
        """Test that last attempt doesn't retry even on rate limit error."""
        # Arrange
        mock_func = AsyncMock()
        mock_func.side_effect = ValueError("Token limit would be exceeded")
        
        mock_token_client = AsyncMock()
        mock_token_client.get_status.return_value = {"reset_time_seconds": 0.1}
        
        # Act & Assert
        with pytest.raises(ValueError, match="Token limit would be exceeded"):
            await with_token_limit_retry(mock_func, mock_token_client, max_retries=1)
        
        mock_func.assert_called_once()
        mock_token_client.get_status.assert_not_called()  # No retry on last attempt


class TestWithTokenLimitRetryDecorator:
    """Test the with_token_limit_retry_decorator function."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_decorator_successful_call(self):
        """Test that decorator works for successful function calls."""
        # Arrange
        mock_token_client = Mock()
        
        @with_token_limit_retry_decorator(mock_token_client, max_retries=3)
        async def test_function(arg1, arg2, kwarg1=None):
            return f"{arg1}_{arg2}_{kwarg1}"
        
        # Act
        result = await test_function("a", "b", kwarg1="c")
        
        # Assert
        assert result == "a_b_c"
        mock_token_client.get_status.assert_not_called()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_decorator_with_retry(self):
        """Test that decorator properly retries on rate limit errors."""
        # Arrange
        mock_token_client = AsyncMock()
        mock_token_client.get_status.return_value = {"reset_time_seconds": 0.1}
        
        call_count = 0
        
        @with_token_limit_retry_decorator(mock_token_client, max_retries=3)
        async def test_function():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Token limit would be exceeded")
            return "success"
        
        # Act
        result = await test_function()
        
        # Assert
        assert result == "success"
        assert call_count == 2
        mock_token_client.get_status.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_decorator_preserves_function_metadata(self):
        """Test that decorator preserves original function metadata."""
        # Arrange
        mock_token_client = Mock()
        
        @with_token_limit_retry_decorator(mock_token_client)
        async def test_function():
            """Test function docstring."""
            return "test"
        
        # Assert
        assert test_function.__name__ == "test_function"
        assert test_function.__doc__ == "Test function docstring."
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_decorator_max_retries_parameter(self):
        """Test that decorator respects max_retries parameter."""
        # Arrange
        mock_token_client = AsyncMock()
        mock_token_client.get_status.return_value = {"reset_time_seconds": 0.1}
        
        @with_token_limit_retry_decorator(mock_token_client, max_retries=1)
        async def test_function():
            raise ValueError("Token limit would be exceeded")
        
        # Act & Assert
        with pytest.raises(ValueError, match="Token limit would be exceeded"):
            await test_function()
        
        mock_token_client.get_status.assert_not_called()  # No retry on last attempt


class TestRetryHelperIntegration:
    """Integration tests for retry helper functionality."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_multiple_consecutive_retries(self):
        """Test multiple consecutive retry attempts."""
        # Arrange
        mock_func = AsyncMock()
        mock_func.side_effect = [
            ValueError("Token limit would be exceeded"),
            ValueError("API Rate limit would be exceeded"),
            "final_success"
        ]
        
        mock_token_client = AsyncMock()
        mock_token_client.get_status.return_value = {"reset_time_seconds": 0.05}
        
        # Act
        result = await with_token_limit_retry(mock_func, mock_token_client, max_retries=3)
        
        # Assert
        assert result == "final_success"
        assert mock_func.call_count == 3
        assert mock_token_client.get_status.call_count == 2
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_wait_time_calculation(self):
        """Test that wait time is calculated correctly with buffer."""
        # Arrange
        mock_func = AsyncMock()
        mock_func.side_effect = [ValueError("Token limit would be exceeded"), "success"]
        
        mock_token_client = AsyncMock()
        mock_token_client.get_status.return_value = {"reset_time_seconds": 2}
        
        # Use patch to monitor sleep calls
        with patch('asyncio.sleep') as mock_sleep:
            # Act
            result = await with_token_limit_retry(mock_func, mock_token_client, max_retries=3)
            
            # Assert
            assert result == "success"
            mock_sleep.assert_called_once_with(3)  # 2 + 1 second buffer 