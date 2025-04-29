import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, call

from common.retry_helpers import RetryConfig, retry_async_with_timeout, retry_async

class TestRetryHelpers:
    """Test suite for the retry_helpers module"""

    @pytest.fixture
    def retry_config(self):
        """Create a retry configuration for testing"""
        return RetryConfig(
            max_retries=3,
            min_retry_delay=0.1,
            max_retry_delay=1.0,
            retry_codes=[429, 500, 503]
        )

    @pytest.mark.asyncio
    @patch('common.retry_helpers.random.uniform')
    @patch('common.retry_helpers.asyncio.sleep')
    async def test_retry_async_success_first_try(self, mock_sleep, mock_uniform, retry_config):
        """Test when the function succeeds on first try without retries"""
        # Mock the function to succeed
        mock_func = AsyncMock(return_value="success")
        mock_uniform.return_value = 0.1  # Fixed return for random.uniform

        # Call the retry function
        result = await retry_async(
            mock_func,
            func_args=("arg1", "arg2"),
            func_kwargs={"kwarg1": "value1"},
            retry_config=retry_config
        )

        # Verify the function was called once with correct arguments
        mock_func.assert_called_once_with("arg1", "arg2", kwarg1="value1")
        
        # Sleep should not be called as there were no retries
        mock_sleep.assert_not_called()
        
        # Result should be the success return value
        assert result == "success"

    @pytest.mark.asyncio
    @patch('common.retry_helpers.random.uniform')
    @patch('common.retry_helpers.asyncio.sleep')
    async def test_retry_async_success_after_retries(self, mock_sleep, mock_uniform, retry_config):
        """Test when the function succeeds after a few retries"""
        # Mock the function to fail twice with exceptions, then succeed
        mock_func = AsyncMock(side_effect=[
            Exception("First failure"),
            Exception("Second failure"),
            "success"
        ])
        mock_uniform.return_value = 0.1  # Fixed return for random.uniform
        
        # Call the retry function
        result = await retry_async(
            mock_func,
            retry_config=retry_config
        )
        
        # Verify the function was called three times
        assert mock_func.call_count == 3
        
        # Sleep should be called twice for the retries
        assert mock_sleep.call_count == 2
        mock_sleep.assert_has_calls([call(0.1), call(0.2)])  # Increasing delays
        
        # Result should be the success return value
        assert result == "success"

    @pytest.mark.asyncio
    @patch('common.retry_helpers.random.uniform')
    @patch('common.retry_helpers.asyncio.sleep')
    async def test_retry_async_all_attempts_fail(self, mock_sleep, mock_uniform, retry_config):
        """Test when all retry attempts fail"""
        # Mock the function to always fail
        mock_func = AsyncMock(side_effect=Exception("Persistent failure"))
        mock_uniform.return_value = 0.1  # Fixed return for random.uniform
        
        # Call the retry function and expect it to raise the exception
        with pytest.raises(Exception) as excinfo:
            await retry_async(
                mock_func,
                retry_config=retry_config
            )
        
        # Verify the function was called max_retries+1 times (initial + retries)
        assert mock_func.call_count == retry_config.max_retries + 1
        
        # Sleep should be called max_retries times
        assert mock_sleep.call_count == retry_config.max_retries
        
        # Exception should be the last one raised
        assert "Persistent failure" in str(excinfo.value)

    @pytest.mark.asyncio
    @patch('common.retry_helpers.random.uniform')
    @patch('common.retry_helpers.asyncio.sleep')
    async def test_retry_async_http_error_retries(self, mock_sleep, mock_uniform, retry_config):
        """Test retries for HTTP errors with specific status codes"""
        # Create mock HTTP errors with different status codes
        class MockHTTPError(Exception):
            def __init__(self, status_code):
                self.status_code = status_code
        
        # Mock function that raises HTTP errors then succeeds
        mock_func = AsyncMock(side_effect=[
            MockHTTPError(429),  # Rate limit error (should retry)
            MockHTTPError(500),  # Server error (should retry)
            "success"
        ])
        mock_uniform.return_value = 0.1  # Fixed return for random.uniform
        
        # Call the retry function
        result = await retry_async(
            mock_func,
            retry_config=retry_config
        )
        
        # Verify the function was called three times
        assert mock_func.call_count == 3
        
        # Sleep should be called twice for the retries
        assert mock_sleep.call_count == 2
        
        # Result should be the success return value
        assert result == "success"

    @pytest.mark.asyncio
    @patch('common.retry_helpers.random.uniform')
    @patch('common.retry_helpers.asyncio.sleep')
    async def test_retry_async_non_retryable_http_error(self, mock_sleep, mock_uniform, retry_config):
        """Test that HTTP errors with non-retryable status codes are not retried"""
        # Create a mock HTTP error with a non-retryable status code
        class MockHTTPError(Exception):
            def __init__(self, status_code):
                self.status_code = status_code
        
        # Mock function that raises a non-retryable HTTP error
        mock_func = AsyncMock(side_effect=MockHTTPError(400))  # Bad request (shouldn't retry)
        mock_uniform.return_value = 0.1  # Fixed return for random.uniform
        
        # Call the retry function and expect it to raise the exception
        with pytest.raises(Exception) as excinfo:
            await retry_async(
                mock_func,
                retry_config=retry_config
            )
        
        # Verify the function was called only once (no retries)
        mock_func.assert_called_once()
        
        # Sleep should not be called
        mock_sleep.assert_not_called()
        
        # The exception should be propagated
        assert hasattr(excinfo.value, 'status_code')
        assert excinfo.value.status_code == 400

    @pytest.mark.asyncio
    @patch('common.retry_helpers.random.uniform')
    @patch('common.retry_helpers.asyncio.sleep')
    async def test_retry_async_with_jitter(self, mock_sleep, mock_uniform, retry_config):
        """Test that retry delay includes jitter"""
        # Mock the function to fail twice, then succeed
        mock_func = AsyncMock(side_effect=[
            Exception("First failure"),
            Exception("Second failure"),
            "success"
        ])
        # Set different values for the jitter
        mock_uniform.side_effect = [0.05, 0.08]  
        
        # Call the retry function
        result = await retry_async(
            mock_func,
            retry_config=retry_config
        )
        
        # Verify random uniform was called to add jitter
        assert mock_uniform.call_count == 2
        mock_uniform.assert_has_calls([
            call(0.1 * 0.8, 0.1 * 1.2),  # jitter for first retry
            call(0.2 * 0.8, 0.2 * 1.2)   # jitter for second retry
        ])
        
        # Verify sleep was called with the jittered values
        mock_sleep.assert_has_calls([
            call(0.05),  # first jittered delay
            call(0.08)   # second jittered delay
        ])
        
        # Result should be the success return value
        assert result == "success"

    @pytest.mark.asyncio
    @patch('common.retry_helpers.asyncio.wait_for')
    async def test_retry_async_with_timeout_success(self, mock_wait_for):
        """Test retry_async_with_timeout with successful execution"""
        # Mock wait_for to return success
        mock_wait_for.return_value = "success"
        
        # Create a mock function (should not be called directly)
        mock_func = AsyncMock()
        
        # Call the retry function with timeout
        result = await retry_async_with_timeout(
            mock_func,
            timeout=5.0,
            func_args=("arg1",),
            func_kwargs={"kwarg1": "value1"}
        )
        
        # Verify wait_for was called with the correct arguments
        mock_wait_for.assert_called_once()
        args, kwargs = mock_wait_for.call_args
        assert args[1] == 5.0  # timeout value
        # The first arg should be a coroutine from mock_func
        
        # Result should be the success return value
        assert result == "success"

    @pytest.mark.asyncio
    @patch('common.retry_helpers.asyncio.wait_for')
    async def test_retry_async_with_timeout_timeout_error(self, mock_wait_for):
        """Test retry_async_with_timeout when a timeout occurs"""
        # Mock wait_for to raise a timeout error
        mock_wait_for.side_effect = asyncio.TimeoutError()
        
        # Create a mock function (should not be called directly)
        mock_func = AsyncMock()
        
        # Call the retry function with timeout and expect timeout error
        with pytest.raises(asyncio.TimeoutError):
            await retry_async_with_timeout(
                mock_func,
                timeout=5.0
            )
        
        # Verify wait_for was called
        mock_wait_for.assert_called_once()

    @pytest.mark.asyncio
    @patch('common.retry_helpers.asyncio.wait_for')
    async def test_retry_async_with_timeout_other_error(self, mock_wait_for):
        """Test retry_async_with_timeout when another error occurs"""
        # Mock wait_for to raise a non-timeout error
        mock_wait_for.side_effect = ValueError("Some other error")
        
        # Create a mock function (should not be called directly)
        mock_func = AsyncMock()
        
        # Call the retry function with timeout and expect the original error
        with pytest.raises(ValueError) as excinfo:
            await retry_async_with_timeout(
                mock_func,
                timeout=5.0
            )
        
        # Verify wait_for was called
        mock_wait_for.assert_called_once()
        
        # The exception should be propagated
        assert "Some other error" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_retry_config_defaults(self):
        """Test that RetryConfig provides reasonable defaults"""
        # Create a config with minimal parameters
        config = RetryConfig()
        
        # Verify defaults are set
        assert config.max_retries > 0
        assert config.min_retry_delay > 0
        assert config.max_retry_delay >= config.min_retry_delay
        assert isinstance(config.retry_codes, list)

    @pytest.mark.asyncio
    async def test_retry_config_custom_values(self):
        """Test creating RetryConfig with custom values"""
        # Create a config with custom parameters
        config = RetryConfig(
            max_retries=5,
            min_retry_delay=0.5,
            max_retry_delay=2.0,
            retry_codes=[429, 500]
        )
        
        # Verify custom values are set
        assert config.max_retries == 5
        assert config.min_retry_delay == 0.5
        assert config.max_retry_delay == 2.0
        assert config.retry_codes == [429, 500] 