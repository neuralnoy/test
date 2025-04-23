import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from azure.servicebus import ServiceBusMessage
from azure.core.exceptions import ServiceBusError

from common.service_bus import AsyncServiceBusHandler


class TestAsyncServiceBusHandler:
    """Unit tests for AsyncServiceBusHandler."""
    
    @pytest.mark.asyncio
    async def test_initialize_creates_client_with_default_credentials(self, 
                                                               mock_service_bus_client,
                                                               mock_azure_credential):
        """Test that initialize creates a ServiceBusClient with DefaultAzureCredential."""
        with patch('azure.servicebus.aio.ServiceBusClient', return_value=mock_service_bus_client) as mock_client_class, \
             patch('azure.identity.aio.DefaultAzureCredential', return_value=mock_azure_credential) as mock_credential_class:
            
            # Create handler
            handler = AsyncServiceBusHandler(
                processor_function=AsyncMock(),
                in_queue_name="test-in",
                out_queue_name="test-out",
                fully_qualified_namespace="test.servicebus.windows.net"
            )
            
            # Initialize the handler
            await handler.initialize()
            
            # Assert DefaultAzureCredential was created
            mock_credential_class.assert_called_once()
            
            # Assert ServiceBusClient was created with the credential
            mock_client_class.assert_called_once_with(
                fully_qualified_namespace="test.servicebus.windows.net",
                credential=mock_azure_credential
            )
            
            # Assert getter methods were called for receiver and sender
            mock_service_bus_client.get_queue_receiver.assert_called_once_with(queue_name="test-in")
            mock_service_bus_client.get_queue_sender.assert_called_once_with(queue_name="test-out")
    
    @pytest.mark.asyncio
    async def test_process_message_success(self, mock_service_bus_handler, sample_feedback_message):
        """Test processing a message successfully."""
        # Configure the mocks
        mock_service_bus_handler.processor_function = AsyncMock(
            return_value={"id": "test-id-123", "result": "success"}
        )
        
        # Process the message
        await mock_service_bus_handler.process_message(sample_feedback_message)
        
        # Assert processor function was called with decoded message body
        mock_service_bus_handler.processor_function.assert_called_once()
        
        # Assert message was completed
        mock_service_bus_handler.receiver.complete_message.assert_called_once_with(sample_feedback_message)
        
        # Assert result was sent to out queue
        mock_service_bus_handler.send_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_message_failure(self, mock_service_bus_handler, sample_feedback_message):
        """Test processing a message with failure."""
        # Configure the processor to raise an exception
        mock_service_bus_handler.processor_function = AsyncMock(side_effect=Exception("Processing error"))
        
        # Process the message
        await mock_service_bus_handler.process_message(sample_feedback_message)
        
        # Assert processor function was called
        mock_service_bus_handler.processor_function.assert_called_once()
        
        # Assert message was abandoned, not completed
        mock_service_bus_handler.receiver.abandon_message.assert_called_once_with(sample_feedback_message)
        mock_service_bus_handler.receiver.complete_message.assert_not_called()
        
        # Assert no message was sent to out queue
        mock_service_bus_handler.send_message.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_send_message_success(self, mock_service_bus_handler):
        """Test sending a message successfully."""
        # Send a message
        test_message = {"id": "test-id", "data": "test-data"}
        await mock_service_bus_handler.send_message(test_message)
        
        # Assert send_messages was called on the sender
        mock_service_bus_handler.sender.send_messages.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_message_string_payload(self, mock_service_bus_handler):
        """Test sending a message with string payload."""
        # Send a string message
        test_message = "test-message-string"
        await mock_service_bus_handler.send_message(test_message)
        
        # Assert send_messages was called on the sender
        mock_service_bus_handler.sender.send_messages.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_message_retry_on_failure(self, mock_service_bus_handler):
        """Test sending a message with retry on failure."""
        # Configure sender to fail twice then succeed
        mock_service_bus_handler.sender.send_messages.side_effect = [
            Exception("First failure"),
            Exception("Second failure"),
            None  # Success on third try
        ]
        
        # Set retry parameters
        mock_service_bus_handler.max_retries = 3
        mock_service_bus_handler.retry_delay = 0.1
        
        # Send a message
        test_message = {"id": "test-id", "data": "test-data"}
        await mock_service_bus_handler.send_message(test_message)
        
        # Assert send_messages was called three times
        assert mock_service_bus_handler.sender.send_messages.call_count == 3
    
    @pytest.mark.asyncio
    async def test_listen_processes_messages(self, mock_service_bus_handler, sample_feedback_message):
        """Test that listen processes messages from the queue."""
        # Configure the receiver to return messages once then empty list to stop the test
        mock_service_bus_handler.receiver.receive_messages.side_effect = [
            [sample_feedback_message],  # First call returns one message
            []  # Second call returns no messages to exit the loop
        ]
        
        # Make handler stop after processing messages
        mock_service_bus_handler.running = True
        
        def stop_after_one_iteration(*args, **kwargs):
            mock_service_bus_handler.running = False
            return None
        
        # Configure processor to stop the handler after processing
        mock_service_bus_handler.process_message = AsyncMock(side_effect=stop_after_one_iteration)
        
        # Start listening
        await mock_service_bus_handler.listen()
        
        # Assert receive_messages was called
        mock_service_bus_handler.receiver.receive_messages.assert_called_once()
        
        # Assert process_message was called for each message
        mock_service_bus_handler.process_message.assert_called_once_with(sample_feedback_message)
    
    @pytest.mark.asyncio
    async def test_stop_cleans_up_resources(self, mock_service_bus_handler):
        """Test that stop cleans up resources properly."""
        # Create a mock task for lock renewal
        mock_task = AsyncMock()
        mock_task.cancel = MagicMock()
        mock_service_bus_handler.lock_renewal_tasks = {"msg-123": mock_task}
        
        # Stop the handler
        await mock_service_bus_handler.stop()
        
        # Assert running flag is set to False
        assert mock_service_bus_handler.running == False
        
        # Assert lock renewal task was cancelled
        mock_task.cancel.assert_called_once()
        
        # Assert client was closed
        mock_service_bus_handler.servicebus_client.close.assert_called_once()
        
        # Assert credential was closed
        mock_service_bus_handler.credential.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_lock_renewal_renews_message_lock(self, mock_service_bus_handler, sample_feedback_message):
        """Test that _renew_message_lock renews message lock periodically."""
        # Set smaller interval for faster test
        mock_service_bus_handler.message_lock_renewal_interval = 0.01
        mock_service_bus_handler.max_message_lock_renewal = 2
        
        # Add message_id to lock_renewal_tasks
        message_id = "msg-123"
        mock_service_bus_handler.lock_renewal_tasks[message_id] = AsyncMock()
        
        # Start lock renewal in background task
        task = asyncio.create_task(
            mock_service_bus_handler._renew_message_lock(sample_feedback_message, message_id)
        )
        
        # Wait a bit for renewals to happen
        await asyncio.sleep(0.03)
        
        # Remove from lock_renewal_tasks to stop the renewal
        del mock_service_bus_handler.lock_renewal_tasks[message_id]
        
        # Wait for task to complete
        await task
        
        # Assert renew_message_lock was called at least once
        mock_service_bus_handler.receiver.renew_message_lock.assert_called_with(sample_feedback_message)
        assert mock_service_bus_handler.receiver.renew_message_lock.call_count >= 1 