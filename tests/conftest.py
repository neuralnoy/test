import asyncio
import os
import pytest
from typing import Dict, Any, List, Optional, AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch
from azure.servicebus import ServiceBusMessage
from azure.servicebus.aio import ServiceBusClient, ServiceBusReceiver, ServiceBusSender
from azure.identity.aio import DefaultAzureCredential
from fastapi.testclient import TestClient
from fastapi import FastAPI

# Set test environment variables
os.environ["SERVICE_BUS_NAMESPACE"] = "test.servicebus.windows.net"
os.environ["FEEDBACK_FORM_IN_QUEUE"] = "test-feedback-in"
os.environ["FEEDBACK_FORM_OUT_QUEUE"] = "test-feedback-out"


@pytest.fixture
def sample_feedback_data() -> Dict[str, Any]:
    """Sample feedback form data for testing."""
    return {
        "id": "test-id-123",
        "taskId": "task-abc",
        "language": "en",
        "text": "This is a test feedback message for processing"
    }


@pytest.fixture
def sample_feedback_message(sample_feedback_data) -> MagicMock:
    """Create a mock ServiceBusMessage with sample data."""
    import json
    message_mock = MagicMock()
    message_mock.body = json.dumps(sample_feedback_data).encode('utf-8')
    message_mock.message_id = "msg-123"
    return message_mock


@pytest.fixture
def mock_service_bus_receiver() -> AsyncMock:
    """Mock for ServiceBusReceiver."""
    receiver = AsyncMock(spec=ServiceBusReceiver)
    receiver.receive_messages = AsyncMock()
    receiver.complete_message = AsyncMock()
    receiver.abandon_message = AsyncMock()
    receiver.renew_message_lock = AsyncMock()
    return receiver


@pytest.fixture
def mock_service_bus_sender() -> AsyncMock:
    """Mock for ServiceBusSender."""
    sender = AsyncMock(spec=ServiceBusSender)
    sender.send_messages = AsyncMock()
    return sender


@pytest.fixture
def mock_service_bus_client() -> AsyncMock:
    """Mock for ServiceBusClient."""
    client = AsyncMock(spec=ServiceBusClient)
    client.get_queue_sender = AsyncMock()
    client.get_queue_receiver = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_azure_credential() -> AsyncMock:
    """Mock for DefaultAzureCredential."""
    credential = AsyncMock(spec=DefaultAzureCredential)
    credential.close = AsyncMock()
    return credential


# Fixture for running async tests
@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def mock_service_bus_handler(
    mock_service_bus_client,
    mock_service_bus_receiver,
    mock_service_bus_sender,
    mock_azure_credential
):
    """Create a mocked service bus handler."""
    from common.service_bus import AsyncServiceBusHandler
    
    # Set up the mock return values
    mock_service_bus_client.get_queue_receiver.return_value = mock_service_bus_receiver
    mock_service_bus_client.get_queue_sender.return_value = mock_service_bus_sender
    
    with patch('azure.servicebus.aio.ServiceBusClient', return_value=mock_service_bus_client), \
         patch('azure.identity.aio.DefaultAzureCredential', return_value=mock_azure_credential):
        
        # Create handler with a simple mock processor function
        processor_func = AsyncMock(return_value={"id": "test-id", "result": "processed"})
        handler = AsyncServiceBusHandler(
            processor_function=processor_func,
            in_queue_name="test-in",
            out_queue_name="test-out",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        # Initialize without actually connecting to service bus
        await handler.initialize()
        
        yield handler
        
        # Cleanup
        await handler.stop()


@pytest.fixture
def test_app_client() -> Generator[TestClient, None, None]:
    """
    Create a test client for the FastAPI app with mocked service bus handler.
    """
    with patch('common.service_bus.AsyncServiceBusHandler') as mock_handler_class, \
         patch('apps.app_feedbackform.services.data_processor.process_data'):
        
        # Import app after mocking dependencies
        from apps.app_feedbackform.main import app
        
        # Configure the mock handler
        mock_handler = mock_handler_class.return_value
        mock_handler.running = True
        mock_handler.listen = AsyncMock()
        mock_handler.stop = AsyncMock()
        
        # Create test client
        with TestClient(app) as client:
            yield client 