import pytest
import asyncio
import json
import uuid
from unittest.mock import patch, AsyncMock, MagicMock
from dataclasses import dataclass

from apps.app_feedbackform.main import app
from apps.app_feedbackform.services.data_processor import process_data
from common.service_bus import AsyncServiceBusHandler

@dataclass
class MockMessage:
    """Mocks a service bus message for testing"""
    body: bytes
    message_id: str = "test-message-id"
    
    async def complete(self):
        """Mock completing a message"""
        pass
    
    async def abandon(self):
        """Mock abandoning a message"""
        pass

class TestFeedbackForm:
    """Integration tests for the Feedback Form service"""

    @pytest.fixture
    def mock_service_bus(self):
        """Mock the service bus handler"""
        with patch('apps.app_feedbackform.main.AsyncServiceBusHandler') as mock_sb:
            # Configure mock
            mock_instance = MagicMock()
            mock_instance.listen = AsyncMock()
            mock_instance.stop = AsyncMock()
            mock_instance.running = True
            
            # Make the mock return itself when called
            mock_sb.return_value = mock_instance
            
            yield mock_instance

    @pytest.fixture
    async def client(self, mock_service_bus):
        """Create a test client for the FastAPI app"""
        from httpx import AsyncClient
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client

    @pytest.mark.asyncio
    async def test_read_root(self, client):
        """Test the root endpoint returns the correct information"""
        response = await client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["app"] == "Feedback Form Processor"
        assert data["status"] == "running"
        assert "queues" in data
        assert "in" in data["queues"]
        assert "out" in data["queues"]

    @pytest.mark.asyncio
    async def test_health_check(self, client, mock_service_bus):
        """Test the health check endpoint"""
        # Configure the mock service bus to report as running
        mock_service_bus.running = True
        
        response = await client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service_bus_running"] is True
        
        # Test when service bus is not running
        mock_service_bus.running = False
        
        response = await client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service_bus_running"] is False

    @pytest.mark.asyncio
    @patch('apps.app_feedbackform.services.prompts.process_feedback')
    async def test_process_data_integration(self, mock_process_feedback):
        """Test the data processor integration with mocked Azure OpenAI"""
        # Mock the Azure OpenAI call
        mock_process_feedback.return_value = (
            True, 
            {
                "ai_hashtag": "#positive",
                "hashtag": "#feedback",
                "summary": "The user had a good experience"
            }
        )
        
        # Create test input data
        test_data = {
            "id": str(uuid.uuid4()),
            "taskId": "task-123",
            "language": "en",
            "text": "I had a great experience using this service!"
        }
        
        # Process the data
        result = await process_data(json.dumps(test_data))
        
        # Verify the result
        assert result is not None
        assert result["id"] == test_data["id"]
        assert result["taskId"] == test_data["taskId"]
        assert result["ai_hashtag"] == "#positive"
        assert result["hashtag"] == "#feedback"
        assert result["summary"] == "The user had a good experience"
        assert result["message"] == "SUCCESS"

    @pytest.mark.asyncio
    @patch('apps.app_feedbackform.services.prompts.process_feedback')
    async def test_service_bus_message_processing(self, mock_process_feedback):
        """Test processing a message via the service bus handler"""
        # Mock the Azure OpenAI call
        mock_process_feedback.return_value = (
            True, 
            {
                "ai_hashtag": "#positive",
                "hashtag": "#feedback",
                "summary": "The user had a good experience"
            }
        )
        
        # Create a mock service bus handler directly
        mock_sender = AsyncMock()
        handler = AsyncServiceBusHandler(
            processor_function=process_data,
            in_queue_name="test-in-queue",
            out_queue_name="test-out-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        handler._sender = mock_sender
        
        # Create test input data
        test_data = {
            "id": str(uuid.uuid4()),
            "taskId": "task-123",
            "language": "en",
            "text": "I had a great experience using this service!"
        }
        
        # Create a mock message
        message = MockMessage(body=json.dumps(test_data).encode('utf-8'))
        
        # Process the message
        await handler._process_message(message)
        
        # Verify the sender was called with processed data
        mock_sender.send_messages.assert_called_once()
        # Extract the sent message
        sent_message = mock_sender.send_messages.call_args[0][0]
        sent_data = json.loads(sent_message.body)
        
        # Verify the data
        assert sent_data["id"] == test_data["id"]
        assert sent_data["ai_hashtag"] == "#positive"
        assert sent_data["hashtag"] == "#feedback"
        assert sent_data["message"] == "SUCCESS"

    @pytest.mark.asyncio
    @patch('apps.app_feedbackform.services.prompts.process_feedback')
    async def test_service_bus_error_handling(self, mock_process_feedback):
        """Test error handling in the service bus handler"""
        # Mock the Azure OpenAI call to fail
        mock_process_feedback.side_effect = Exception("Simulated processing error")
        
        # Create a mock service bus handler
        mock_sender = AsyncMock()
        handler = AsyncServiceBusHandler(
            processor_function=process_data,
            in_queue_name="test-in-queue",
            out_queue_name="test-out-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        handler._sender = mock_sender
        
        # Create test input data
        test_data = {
            "id": str(uuid.uuid4()),
            "taskId": "task-123",
            "language": "en",
            "text": "This will cause an error"
        }
        
        # Create a mock message
        message = MockMessage(body=json.dumps(test_data).encode('utf-8'))
        
        # Process the message
        await handler._process_message(message)
        
        # Verify the message was abandoned
        # No direct way to verify this due to using AsyncMock
        
        # Verify the sender was NOT called (no output message)
        mock_sender.send_messages.assert_not_called()

    @pytest.mark.asyncio
    async def test_lifespan(self, mock_service_bus):
        """Test the lifespan context manager for app startup/shutdown"""
        # Test app startup by simulating the lifespan context manager
        async with app.router.lifespan_context(app):
            # Verify service bus handler was started
            mock_service_bus.listen.assert_called_once()
        
        # After exiting the context, verify service bus handler was stopped
        mock_service_bus.stop.assert_called_once()

    @pytest.mark.asyncio
    @patch('apps.app_feedbackform.services.prompts.process_feedback')
    async def test_invalid_message_handling(self, mock_process_feedback):
        """Test handling of invalid messages"""
        # Create a mock service bus handler
        mock_sender = AsyncMock()
        handler = AsyncServiceBusHandler(
            processor_function=process_data,
            in_queue_name="test-in-queue",
            out_queue_name="test-out-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        handler._sender = mock_sender
        
        # Create an invalid message (not JSON)
        message = MockMessage(body=b"This is not valid JSON")
        
        # Process the message
        await handler._process_message(message)
        
        # Verify the sender was called with error information
        mock_sender.send_messages.assert_called_once()
        # Extract the sent message
        sent_message = mock_sender.send_messages.call_args[0][0]
        sent_data = json.loads(sent_message.body)
        
        # Verify the error response
        assert sent_data["id"] == "unknown"
        assert sent_data["taskId"] == "unknown"
        assert "#error" in sent_data["ai_hashtag"]
        assert "JSON" in sent_data["summary"]
        assert sent_data["message"] == "failed" 