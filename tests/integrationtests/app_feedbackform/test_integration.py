import os
import json
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from azure.servicebus import ServiceBusMessage

from common.service_bus import AsyncServiceBusHandler
from apps.app_feedbackform.services.data_processor import process_data


@pytest.mark.integration
class TestFeedbackFormServiceBusIntegration:
    """
    Integration tests for the Feedback Form service with Service Bus.
    
    These tests require mocking the Azure Service Bus client but test
    the integration between the service bus handler and data processor.
    """
    
    @pytest.fixture
    async def integrated_handler(self, mock_service_bus_client, mock_service_bus_receiver, 
                                mock_service_bus_sender, mock_azure_credential):
        """
        Create a service bus handler that uses the actual data processor.
        """
        # Set up the mock return values
        mock_service_bus_client.get_queue_receiver.return_value = mock_service_bus_receiver
        mock_service_bus_client.get_queue_sender.return_value = mock_service_bus_sender
        
        with patch('azure.servicebus.aio.ServiceBusClient', return_value=mock_service_bus_client), \
             patch('azure.identity.aio.DefaultAzureCredential', return_value=mock_azure_credential):
            
            # Create handler with the actual process_data function
            handler = AsyncServiceBusHandler(
                processor_function=process_data,
                in_queue_name="test-feedback-in",
                out_queue_name="test-feedback-out",
                fully_qualified_namespace="test.servicebus.windows.net"
            )
            
            # Initialize without actually connecting to service bus
            await handler.initialize()
            
            yield handler
            
            # Cleanup
            await handler.stop()
    
    @pytest.mark.asyncio
    async def test_end_to_end_message_processing(self, integrated_handler, sample_feedback_data, sample_feedback_message):
        """
        Test end-to-end message processing from receiving to sending.
        Uses the actual data processor with mocked service bus.
        """
        # Configure receiver to return our test message
        integrated_handler.receiver.receive_messages.side_effect = [
            [sample_feedback_message],  # First call returns one message
            []  # Second call returns no messages to exit the loop
        ]
        
        # Set running to True initially, then stop after processing
        integrated_handler.running = True
        
        # Configure a way to stop the handler after processing one message
        original_complete_message = integrated_handler.receiver.complete_message
        
        async def stop_after_complete(*args, **kwargs):
            # Call original method first
            await original_complete_message(*args, **kwargs)
            # Then stop the handler
            integrated_handler.running = False
        
        integrated_handler.receiver.complete_message = AsyncMock(side_effect=stop_after_complete)
        
        # Start listening - this should process the message and stop
        await integrated_handler.listen()
        
        # Assert message was completed, not abandoned
        integrated_handler.receiver.complete_message.assert_called_once_with(sample_feedback_message)
        integrated_handler.receiver.abandon_message.assert_not_called()
        
        # Assert send_messages was called with a ServiceBusMessage
        integrated_handler.sender.send_messages.assert_called_once()
        
        # Get the sent message
        sent_message = integrated_handler.sender.send_messages.call_args[0][0]
        assert isinstance(sent_message, ServiceBusMessage)
        
        # Decode and parse the message body
        sent_body = json.loads(sent_message.body.decode('utf-8'))
        
        # Verify message content matches expected output of data processor
        assert sent_body["id"] == sample_feedback_data["id"]
        assert "ai_hashtag" in sent_body
        assert "hashtag" in sent_body
        assert "summary" in sent_body
    
    @pytest.mark.asyncio
    async def test_invalid_message_handling(self, integrated_handler):
        """
        Test handling of invalid messages in the end-to-end flow.
        """
        # Create an invalid message
        invalid_message = MagicMock()
        invalid_message.body = b'{invalid-json}'
        invalid_message.message_id = "invalid-msg-123"
        
        # Configure receiver to return our invalid message
        integrated_handler.receiver.receive_messages.side_effect = [
            [invalid_message],  # First call returns invalid message
            []  # Second call returns no messages to exit the loop
        ]
        
        # Set running to True initially, then stop after processing
        integrated_handler.running = True
        
        # Configure a way to stop the handler after abandoning the message
        original_abandon_message = integrated_handler.receiver.abandon_message
        
        async def stop_after_abandon(*args, **kwargs):
            # Call original method first
            await original_abandon_message(*args, **kwargs)
            # Then stop the handler
            integrated_handler.running = False
        
        integrated_handler.receiver.abandon_message = AsyncMock(side_effect=stop_after_abandon)
        
        # Start listening - this should process the message and stop
        await integrated_handler.listen()
        
        # Assert message was abandoned, not completed
        integrated_handler.receiver.abandon_message.assert_called_once_with(invalid_message)
        integrated_handler.receiver.complete_message.assert_not_called()
        
        # Assert send_messages was not called
        integrated_handler.sender.send_messages.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_missing_fields_handling(self, integrated_handler):
        """
        Test handling of messages with missing required fields.
        """
        # Create a message with missing fields
        incomplete_data = {
            "id": "test-id-123",
            # Missing taskId and other required fields
        }
        incomplete_message = MagicMock()
        incomplete_message.body = json.dumps(incomplete_data).encode('utf-8')
        incomplete_message.message_id = "incomplete-msg-123"
        
        # Configure receiver to return our incomplete message
        integrated_handler.receiver.receive_messages.side_effect = [
            [incomplete_message],  # First call returns incomplete message
            []  # Second call returns no messages to exit the loop
        ]
        
        # Set running to True initially, then stop after processing
        integrated_handler.running = True
        
        # Configure a way to stop the handler after abandoning the message
        original_abandon_message = integrated_handler.receiver.abandon_message
        
        async def stop_after_abandon(*args, **kwargs):
            # Call original method first
            await original_abandon_message(*args, **kwargs)
            # Then stop the handler
            integrated_handler.running = False
        
        integrated_handler.receiver.abandon_message = AsyncMock(side_effect=stop_after_abandon)
        
        # Start listening - this should process the message and stop
        await integrated_handler.listen()
        
        # Assert message was abandoned, not completed
        integrated_handler.receiver.abandon_message.assert_called_once_with(incomplete_message)
        integrated_handler.receiver.complete_message.assert_not_called()
        
        # Assert send_messages was not called
        integrated_handler.sender.send_messages.assert_not_called() 