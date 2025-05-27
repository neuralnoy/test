import pytest
import asyncio
from httpx import AsyncClient
import json
import os
import uuid
from datetime import datetime

from app_counter.main import app

class TestCounterAPI:
    """Integration tests for the Token Counter API"""

    @pytest.fixture
    async def client(self):
        """Create a test client for the FastAPI app"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client

    @pytest.mark.asyncio
    async def test_read_root(self, client):
        """Test the root endpoint returns the correct information"""
        response = await client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["app"] == "OpenAI Token Counter"
        assert data["status"] == "running"
        assert "token_limit_per_minute" in data
        assert "rate_limit_per_minute" in data

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """Test the health check endpoint"""
        response = await client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_lock_tokens_success(self, client):
        """Test successfully locking tokens when under the limit"""
        # Generate a unique app ID for this test
        app_id = f"test-app-{uuid.uuid4()}"
        
        # Request a reasonable number of tokens (should be allowed)
        response = await client.post(
            "/lock",
            json={
                "app_id": app_id,
                "token_count": 5000  # Small enough to be within limit
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is True
        assert "request_id" in data
        assert data["request_id"] is not None
        # Verify the request_id contains the combined token and rate IDs
        assert ":" in data["request_id"]

    @pytest.mark.asyncio
    async def test_lock_tokens_over_limit(self, client):
        """Test locking tokens when exceeding the limit"""
        # Generate a unique app ID for this test
        app_id = f"test-app-{uuid.uuid4()}"
        
        # Get the current token limit
        root_response = await client.get("/")
        token_limit = root_response.json()["token_limit_per_minute"]
        
        # Request more tokens than the limit
        response = await client.post(
            "/lock",
            json={
                "app_id": app_id,
                "token_count": token_limit + 10000  # Exceeds the limit
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is False
        assert "message" in data
        assert "limit" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_lock_report_release_flow(self, client):
        """Test the complete flow: lock tokens, report usage, and check status"""
        # Generate a unique app ID for this test
        app_id = f"test-app-{uuid.uuid4()}"
        
        # Step 1: Lock tokens
        lock_response = await client.post(
            "/lock",
            json={
                "app_id": app_id,
                "token_count": 5000
            }
        )
        
        assert lock_response.status_code == 200
        lock_data = lock_response.json()
        assert lock_data["allowed"] is True
        request_id = lock_data["request_id"]
        
        # Step 2: Get status to verify tokens are locked
        status_response_1 = await client.get("/status")
        status_data_1 = status_response_1.json()
        assert status_data_1["locked_tokens"] >= 5000  # At least our tokens are locked
        
        # Step 3: Report usage
        report_response = await client.post(
            "/report",
            json={
                "app_id": app_id,
                "request_id": request_id,
                "prompt_tokens": 2000,
                "completion_tokens": 1000
            }
        )
        
        assert report_response.status_code == 200
        
        # Step 4: Get status to verify tokens are now used instead of locked
        status_response_2 = await client.get("/status")
        status_data_2 = status_response_2.json()
        assert status_data_2["locked_tokens"] <= status_data_1["locked_tokens"] - 5000  # Tokens are no longer locked
        assert status_data_2["used_tokens"] >= status_data_1["used_tokens"] + 3000  # Tokens are now used

    @pytest.mark.asyncio
    async def test_multiple_concurrent_requests(self, client):
        """Test handling multiple concurrent token requests"""
        # Generate a unique base app ID
        base_app_id = f"test-app-{uuid.uuid4()}"
        
        # Create multiple concurrent lock requests
        async def lock_request(app_id_suffix, tokens):
            return await client.post(
                "/lock",
                json={
                    "app_id": f"{base_app_id}-{app_id_suffix}",
                    "token_count": tokens
                }
            )
        
        # Execute requests concurrently
        responses = await asyncio.gather(
            lock_request("1", 10000),
            lock_request("2", 15000),
            lock_request("3", 20000),
            lock_request("4", 25000)
        )
        
        # Check each response
        allowed_count = 0
        for response in responses:
            assert response.status_code == 200
            data = response.json()
            if data["allowed"]:
                allowed_count += 1
        
        # Some requests should be allowed (we don't know exactly how many due to concurrency)
        assert allowed_count > 0
        
        # Get status to verify token accounting
        status_response = await client.get("/status")
        status_data = status_response.json()
        
        # Token limit should be respected
        root_response = await client.get("/")
        token_limit = root_response.json()["token_limit_per_minute"]
        assert status_data["locked_tokens"] + status_data["used_tokens"] <= token_limit

    @pytest.mark.asyncio
    async def test_release_tokens(self, client):
        """Test releasing locked tokens"""
        # Generate a unique app ID for this test
        app_id = f"test-app-{uuid.uuid4()}"
        
        # Step 1: Lock tokens
        lock_response = await client.post(
            "/lock",
            json={
                "app_id": app_id,
                "token_count": 5000
            }
        )
        
        assert lock_response.status_code == 200
        lock_data = lock_response.json()
        request_id = lock_data["request_id"]
        
        # Get status before release
        status_before = await client.get("/status")
        locked_before = status_before.json()["locked_tokens"]
        
        # Step 2: Release tokens
        release_response = await client.post(
            "/release",
            json={
                "app_id": app_id,
                "request_id": request_id
            }
        )
        
        assert release_response.status_code == 200
        
        # Get status after release
        status_after = await client.get("/status")
        locked_after = status_after.json()["locked_tokens"]
        
        # Verify tokens were released
        assert locked_after <= locked_before - 5000

    @pytest.mark.asyncio
    async def test_invalid_request_id(self, client):
        """Test handling of invalid request IDs"""
        # Generate a unique app ID for this test
        app_id = f"test-app-{uuid.uuid4()}"
        
        # Try to report usage with an invalid request ID
        response = await client.post(
            "/report",
            json={
                "app_id": app_id,
                "request_id": "invalid-request-id",
                "prompt_tokens": 2000,
                "completion_tokens": 1000
            }
        )
        
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_app_id_mismatch(self, client):
        """Test handling of app ID mismatches"""
        # Generate unique app IDs for this test
        app_id_1 = f"test-app-1-{uuid.uuid4()}"
        app_id_2 = f"test-app-2-{uuid.uuid4()}"
        
        # Step 1: Lock tokens with first app ID
        lock_response = await client.post(
            "/lock",
            json={
                "app_id": app_id_1,
                "token_count": 5000
            }
        )
        
        assert lock_response.status_code == 200
        lock_data = lock_response.json()
        request_id = lock_data["request_id"]
        
        # Step 2: Try to report usage with different app ID
        report_response = await client.post(
            "/report",
            json={
                "app_id": app_id_2,  # Different app ID
                "request_id": request_id,
                "prompt_tokens": 2000,
                "completion_tokens": 1000
            }
        )
        
        assert report_response.status_code == 400

    @pytest.mark.asyncio
    async def test_status_reset(self, client, monkeypatch):
        """Test that token counter resets after a minute"""
        # This test requires mocking time.time() to simulate passage of time
        # Note: In a real integration test, we might skip this as it requires waiting
        
        # For API tests, we can mock the token_counter's last_reset time
        # First, get access to the token_counter through the app state
        token_counter = app.state.token_counter
        
        # Lock some tokens to create usage
        app_id = f"test-app-{uuid.uuid4()}"
        await client.post(
            "/lock",
            json={
                "app_id": app_id,
                "token_count": 5000
            }
        )
        
        # Verify tokens are locked
        status_before = await client.get("/status")
        assert status_before.json()["locked_tokens"] >= 5000
        
        # Manually reset the last_reset time to simulate passage of time
        original_last_reset = token_counter.last_reset
        token_counter.last_reset = original_last_reset - 61  # 61 seconds ago
        
        # Get status again to trigger reset
        status_after = await client.get("/status")
        
        # Verify counters were reset
        assert status_after.json()["used_tokens"] == 0
        assert status_after.json()["locked_tokens"] == 0

    @pytest.mark.asyncio
    async def test_status_contains_rate_info(self, client):
        """Test that status endpoint includes rate limit information"""
        response = await client.get("/status")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check token counter fields
        assert "available_tokens" in data
        assert "used_tokens" in data
        assert "locked_tokens" in data
        
        # Check rate counter fields
        assert "available_requests" in data
        assert "used_requests" in data
        assert "locked_requests" in data
        
        assert "reset_time_seconds" in data 