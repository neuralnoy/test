import pytest
import asyncio
import time
from unittest.mock import patch, MagicMock

from app_counter.services.token_counter import TokenCounter

class TestTokenCounter:
    """Test suite for the TokenCounter class"""

    @pytest.fixture
    def token_counter(self):
        """Create a token counter instance for testing"""
        return TokenCounter(tokens_per_minute=100000)

    @pytest.mark.asyncio
    async def test_lock_tokens_success(self, token_counter):
        """Test successfully locking tokens when sufficient tokens are available"""
        result = await token_counter.lock_tokens("test_app", 5000)
        
        assert result["allowed"] is True
        assert "request_id" in result
        assert token_counter.locked_tokens == 5000
        assert token_counter.used_tokens == 0
        assert len(token_counter.requests) == 1

    @pytest.mark.asyncio
    async def test_lock_tokens_insufficient(self, token_counter):
        """Test locking tokens when insufficient tokens are available"""
        # First, use most of the tokens
        await token_counter.lock_tokens("test_app", 90000)
        
        # Try to lock more tokens than available
        result = await token_counter.lock_tokens("test_app", 15000)
        
        assert result["allowed"] is False
        assert "message" in result
        assert token_counter.locked_tokens == 90000  # Should remain the same

    @pytest.mark.asyncio
    async def test_report_usage_success(self, token_counter):
        """Test successfully reporting token usage"""
        # First lock some tokens
        lock_result = await token_counter.lock_tokens("test_app", 5000)
        request_id = lock_result["request_id"]
        
        # Report usage
        result = await token_counter.report_usage("test_app", request_id, 2000, 1000)
        
        assert result is True
        assert token_counter.locked_tokens == 0  # Tokens should be unlocked
        assert token_counter.used_tokens == 3000  # 2000 prompt + 1000 completion
        assert request_id not in token_counter.requests  # Request should be removed

    @pytest.mark.asyncio
    async def test_report_usage_invalid_request_id(self, token_counter):
        """Test reporting usage with an invalid request ID"""
        result = await token_counter.report_usage("test_app", "invalid_id", 2000, 1000)
        
        assert result is False
        assert token_counter.locked_tokens == 0
        assert token_counter.used_tokens == 0

    @pytest.mark.asyncio
    async def test_report_usage_app_id_mismatch(self, token_counter):
        """Test reporting usage with a mismatched app ID"""
        # First lock some tokens
        lock_result = await token_counter.lock_tokens("test_app", 5000)
        request_id = lock_result["request_id"]
        
        # Report usage with wrong app_id
        result = await token_counter.report_usage("different_app", request_id, 2000, 1000)
        
        assert result is False
        assert token_counter.locked_tokens == 5000  # Tokens should still be locked
        assert token_counter.used_tokens == 0

    @pytest.mark.asyncio
    async def test_release_tokens_success(self, token_counter):
        """Test successfully releasing tokens"""
        # First lock some tokens
        lock_result = await token_counter.lock_tokens("test_app", 5000)
        request_id = lock_result["request_id"]
        
        # Release tokens
        result = await token_counter.release_tokens("test_app", request_id)
        
        assert result is True
        assert token_counter.locked_tokens == 0  # Tokens should be released
        assert token_counter.used_tokens == 0  # No tokens should be used
        assert request_id not in token_counter.requests  # Request should be removed

    @pytest.mark.asyncio
    async def test_release_tokens_invalid_request_id(self, token_counter):
        """Test releasing tokens with an invalid request ID"""
        result = await token_counter.release_tokens("test_app", "invalid_id")
        
        assert result is False
        assert token_counter.locked_tokens == 0
        assert token_counter.used_tokens == 0

    @pytest.mark.asyncio
    async def test_release_tokens_app_id_mismatch(self, token_counter):
        """Test releasing tokens with a mismatched app ID"""
        # First lock some tokens
        lock_result = await token_counter.lock_tokens("test_app", 5000)
        request_id = lock_result["request_id"]
        
        # Release tokens with wrong app_id
        result = await token_counter.release_tokens("different_app", request_id)
        
        assert result is False
        assert token_counter.locked_tokens == 5000  # Tokens should still be locked
        assert token_counter.used_tokens == 0

    @pytest.mark.asyncio
    async def test_get_status(self, token_counter):
        """Test getting the token counter status"""
        # Lock some tokens and report usage to set up a state
        lock_result = await token_counter.lock_tokens("test_app", 5000)
        await token_counter.report_usage("test_app", lock_result["request_id"], 2000, 1000)
        
        # Lock more tokens
        await token_counter.lock_tokens("test_app", 10000)
        
        # Get status
        status = await token_counter.get_status()
        
        assert "available_tokens" in status
        assert "used_tokens" in status
        assert "locked_tokens" in status
        assert "reset_time_seconds" in status
        assert status["used_tokens"] == 3000
        assert status["locked_tokens"] == 10000
        assert status["available_tokens"] == 100000 - 3000 - 10000

    @pytest.mark.asyncio
    async def test_reset_counter(self, token_counter):
        """Test that counter resets after a minute"""
        # Set up initial state
        lock_result = await token_counter.lock_tokens("test_app", 5000)
        await token_counter.report_usage("test_app", lock_result["request_id"], 2000, 1000)
        
        assert token_counter.used_tokens == 3000
        
        # Mock time to be 61 seconds later
        with patch('time.time', return_value=time.time() + 61):
            # Trigger reset by getting status
            status = await token_counter.get_status()
            
            assert status["used_tokens"] == 0  # Should be reset to 0

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, token_counter):
        """Test that token counter handles concurrent requests properly"""
        async def lock_and_report(app_id, tokens):
            lock_result = await token_counter.lock_tokens(app_id, tokens)
            if lock_result["allowed"]:
                await token_counter.report_usage(app_id, lock_result["request_id"], tokens // 2, tokens // 2)
                return True
            return False
        
        # Create multiple concurrent tasks
        tasks = [
            lock_and_report("app1", 20000),
            lock_and_report("app2", 30000),
            lock_and_report("app3", 40000),
            lock_and_report("app4", 15000)
        ]
        
        # Run them concurrently
        results = await asyncio.gather(*tasks)
        
        # All should succeed since total is within limit
        assert all(results)
        
        # Check total usage
        status = await token_counter.get_status()
        assert status["used_tokens"] == 105000  # Sum of all tokens
        assert status["locked_tokens"] == 0  # All tokens should be reported, not locked

    @pytest.mark.asyncio
    async def test_exceed_limit_with_concurrent_requests(self, token_counter):
        """Test behavior when concurrent requests exceed the token limit"""
        # Use a smaller limit for this test
        token_counter.tokens_per_minute = 50000
        
        async def lock_and_report(app_id, tokens):
            lock_result = await token_counter.lock_tokens(app_id, tokens)
            if lock_result["allowed"]:
                await asyncio.sleep(0.1)  # Simulate some processing time
                await token_counter.report_usage(app_id, lock_result["request_id"], tokens // 2, tokens // 2)
                return True
            return False
        
        # Create tasks that together exceed the limit
        tasks = [
            lock_and_report("app1", 20000),
            lock_and_report("app2", 20000),
            lock_and_report("app3", 20000)  # This one should fail
        ]
        
        # Run them concurrently
        results = await asyncio.gather(*tasks)
        
        # At least one should fail
        assert not all(results)
        
        # Check usage is within limit
        status = await token_counter.get_status()
        assert status["used_tokens"] <= 50000 