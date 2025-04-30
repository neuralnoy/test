import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from common.service_bus import AsyncServiceBusHandler

class TestAsyncServiceBusHandler:
    """Test suite for the AsyncServiceBusHandler class"""

    @pytest.fixture
    def processor_function(self):
        """Create a mock processor function for testing"""
        async def mock_processor(message_body):
            return {"result": "processed", "body": message_body}
        
        return AsyncMock(side_effect=mock_processor)

    @pytest.fixture
    def service_bus_handler(self, processor_function):
        """Create a service bus handler for testing"""
        with patch('common.service_bus.ServiceBusClient') as mock_sb_client, \
             patch('common.service_bus.DefaultAzureCredential') as mock_credential:
            
            # Mock the receiver and sender
            mock_receiver = AsyncMock()
            mock_sender = AsyncMock()
            
            # Set up the mock client to return our mocks
            mock_sb_client.return_value.get_queue_receiver = MagicMock(return_value=mock_receiver)
            mock_sb_client.return_value.get_queue_sender = MagicMock(return_value=mock_sender)
            
            # Create the handler
            handler = AsyncServiceBusHandler(
                processor_function=processor_function,
                in_queue_name="test-in-queue",
                out_queue_name="test-out-queue",
                fully_qualified_namespace="test.servicebus.windows.net"
            )
            
            # Make the mocks accessible for tests
            handler._receiver = mock_receiver
            handler._sender = mock_sender
            
            yield handler

    @pytest.mark.asyncio
    async def test_initialize(self, service_bus_handler):
        """Test initialization of service bus handler"""
        # The service_bus_handler fixture already initializes the handler
        # Just verify that it has the correct properties
        assert service_bus_handler.in_queue_name == "test-in-queue"
        assert service_bus_handler.out_queue_name == "test-out-queue"
        assert service_bus_handler.fully_qualified_namespace == "test.servicebus.windows.net"
        assert service_bus_handler._receiver is not None
        assert service_bus_handler._sender is not None

    @pytest.mark.asyncio
    async def test_process_message_success(self, service_bus_handler, processor_function):
        """Test successful processing of a message"""
        # Create a mock message
        mock_message = MagicMock()
        mock_message.body = b'{"test": "data"}'
        
        # Process the message
        await service_bus_handler._process_message(mock_message)
        
        # Verify processor was called with correct data
        processor_function.assert_called_once_with('{"test": "data"}')
        
        # Verify message was completed
        mock_message.complete.assert_called_once()
        
        # Verify result was sent to output queue
        service_bus_handler._sender.send_messages.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_message_processor_returns_none(self, service_bus_handler, processor_function):
        """Test when processor function returns None"""
        # Override the processor function to return None
        processor_function.side_effect = AsyncMock(return_value=None)
        
        # Create a mock message
        mock_message = MagicMock()
        mock_message.body = b'{"test": "data"}'
        
        # Process the message
        await service_bus_handler._process_message(mock_message)
        
        # Verify processor was called
        processor_function.assert_called_once()
        
        # Verify message was completed
        mock_message.complete.assert_called_once()
        
        # Verify no result was sent (send_messages not called)
        service_bus_handler._sender.send_messages.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_processor_exception(self, service_bus_handler, processor_function):
        """Test when processor function raises an exception"""
        # Override the processor function to raise an exception
        processor_function.side_effect = Exception("Processing error")
        
        # Create a mock message
        mock_message = MagicMock()
        mock_message.body = b'{"test": "data"}'
        mock_message.message_id = "test-message-id"
        
        # Process the message
        await service_bus_handler._process_message(mock_message)
        
        # Verify processor was called
        processor_function.assert_called_once()
        
        # Verify message was abandoned (not completed)
        mock_message.abandon.assert_called_once()
        
        # Verify no result was sent
        service_bus_handler._sender.send_messages.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_invalid_body(self, service_bus_handler):
        """Test processing a message with an invalid body"""
        # Create a mock message with an invalid body (not bytes)
        mock_message = MagicMock()
        mock_message.body = None  # Invalid body
        mock_message.message_id = "test-message-id"
        
        # Process the message
        await service_bus_handler._process_message(mock_message)
        
        # Verify message was abandoned
        mock_message.abandon.assert_called_once()
        
        # Verify no result was sent
        service_bus_handler._sender.send_messages.assert_not_called()

    @pytest.mark.asyncio
    async def test_listen_stop(self, service_bus_handler):
        """Test starting and stopping the listener"""
        # Override _process_message to track calls and simulate waiting
        service_bus_handler._process_message = AsyncMock()
        
        # Create mock messages
        mock_message1 = MagicMock()
        mock_message2 = MagicMock()
        
        # Set up receiver to return messages then raise StopAsyncIteration
        service_bus_handler._receiver.receive_messages.side_effect = [
            [mock_message1], 
            [mock_message2], 
            asyncio.CancelledError
        ]
        
        # Start listening in a task so we can stop it
        listen_task = asyncio.create_task(service_bus_handler.listen())
        
        # Wait a bit to let it process some messages
        await asyncio.sleep(0.1)
        
        # Stop the listener
        await service_bus_handler.stop()
        
        # Wait for the task to complete
        try:
            await listen_task
        except asyncio.CancelledError:
            pass
        
        # Verify receiver was called multiple times
        assert service_bus_handler._receiver.receive_messages.call_count >= 1
        
        # Verify messages were processed
        service_bus_handler._process_message.assert_called()

    @pytest.mark.asyncio
    async def test_listen_receiver_exception(self, service_bus_handler):
        """Test handling of receiver exceptions"""
        # Set up receiver to raise an exception
        service_bus_handler._receiver.receive_messages.side_effect = Exception("Receiver error")
        
        # Override _process_message to track calls
        service_bus_handler._process_message = AsyncMock()
        
        # Start listening in a task so we can stop it
        listen_task = asyncio.create_task(service_bus_handler.listen())
        
        # Wait a bit to let it try processing
        await asyncio.sleep(0.1)
        
        # Stop the listener
        await service_bus_handler.stop()
        
        # Wait for the task to complete
        try:
            await listen_task
        except asyncio.CancelledError:
            pass
        
        # Verify receiver was called
        service_bus_handler._receiver.receive_messages.assert_called()
        
        # Verify no messages were processed (exception was caught)
        service_bus_handler._process_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_message_success(self, service_bus_handler):
        """Test successfully sending a message"""
        # Send a message
        result = await service_bus_handler._send_message({"test": "output"})
        
        # Verify sender was called
        service_bus_handler._sender.send_messages.assert_called_once()
        
        # Verify result is True
        assert result is True

    @pytest.mark.asyncio
    async def test_send_message_exception(self, service_bus_handler):
        """Test handling sender exceptions"""
        # Set up sender to raise an exception
        service_bus_handler._sender.send_messages.side_effect = Exception("Sender error")
        
        # Send a message
        result = await service_bus_handler._send_message({"test": "output"})
        
        # Verify sender was called
        service_bus_handler._sender.send_messages.assert_called_once()
        
        # Verify result is False (exception was caught)
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, service_bus_handler):
        """Test stopping the handler when it's not running"""
        # Handler isn't running yet
        assert not service_bus_handler.running
        
        # Stop it anyway
        await service_bus_handler.stop()
        
        # Should not throw an exception
        assert not service_bus_handler.running

    @pytest.mark.asyncio
    async def test_close_contexts(self, service_bus_handler):
        """Test closing the receiver and sender contexts"""
        # Call the close method
        await service_bus_handler._close()
        
        # Verify receiver and sender were closed
        service_bus_handler._receiver.close.assert_called_once()
        service_bus_handler._sender.close.assert_called_once() 