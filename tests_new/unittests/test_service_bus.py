"""
Comprehensive unit tests for common_new.service_bus module.
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from common_new.service_bus import AsyncServiceBusHandler


class TestAsyncServiceBusHandlerInit:
    """Test AsyncServiceBusHandler initialization."""
    
    @pytest.mark.unit
    def test_init_basic(self):
        """Test basic initialization."""
        processor_func = AsyncMock()
        handler = AsyncServiceBusHandler(
            processor_function=processor_func,
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        assert handler.processor_function is processor_func
        assert handler.in_queue_name == "input-queue"
        assert handler.out_queue_name == "output-queue"
        assert handler.fully_qualified_namespace == "test.servicebus.windows.net"
        assert handler.max_retries == 5
        assert handler.retry_delay == 3.0
        assert handler.max_wait_time == 3.0
        assert handler.message_batch_size == 1
        assert not handler.running
        assert handler.total_processed_messages == 0
        assert handler.sleep_seconds == 4
    
    @pytest.mark.unit
    def test_init_with_custom_params(self):
        """Test initialization with custom parameters."""
        processor_func = AsyncMock()
        handler = AsyncServiceBusHandler(
            processor_function=processor_func,
            in_queue_name="custom-input",
            out_queue_name="custom-output",
            fully_qualified_namespace="custom.servicebus.windows.net",
            max_retries=10,
            retry_delay=5.0,
            max_wait_time=10.0,
            message_batch_size=5
        )
        
        assert handler.max_retries == 10
        assert handler.retry_delay == 5.0
        assert handler.max_wait_time == 10.0
        assert handler.message_batch_size == 5


class TestAsyncServiceBusHandlerProcessMessage:
    """Test the process_message method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_process_message_success_with_result(self):
        """Test successful message processing with result."""
        processor_func = AsyncMock(return_value="processed result")
        handler = AsyncServiceBusHandler(
            processor_function=processor_func,
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        mock_message = Mock()
        mock_message.message_id = "test-message-123"
        mock_message.body = b"test message content"
        
        with patch.object(handler, 'send_message', return_value=True) as mock_send:
            await handler.process_message(mock_message)
            
            processor_func.assert_called_once_with("test message content")
            mock_send.assert_called_once_with("processed result")
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_process_message_success_no_result(self):
        """Test successful message processing without result."""
        processor_func = AsyncMock(return_value=None)
        handler = AsyncServiceBusHandler(
            processor_function=processor_func,
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        mock_message = Mock()
        mock_message.message_id = "test-message-123"
        mock_message.body = b"test message content"
        
        with patch.object(handler, 'send_message') as mock_send:
            await handler.process_message(mock_message)
            
            processor_func.assert_called_once_with("test message content")
            mock_send.assert_not_called()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_process_message_string_body(self):
        """Test message processing with string body."""
        processor_func = AsyncMock(return_value=None)
        handler = AsyncServiceBusHandler(
            processor_function=processor_func,
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        mock_message = Mock()
        mock_message.message_id = "test-message-123"
        mock_message.body = "string message content"
        
        await handler.process_message(mock_message)
        
        processor_func.assert_called_once_with("string message content")
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_process_message_generator_body(self):
        """Test message processing with generator body."""
        processor_func = AsyncMock(return_value=None)
        handler = AsyncServiceBusHandler(
            processor_function=processor_func,
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        mock_message = Mock()
        mock_message.message_id = "test-message-123"
        # Mock generator that yields byte chunks
        mock_message.body = iter([b"chunk1", b"chunk2"])
        
        await handler.process_message(mock_message)
        
        processor_func.assert_called_once_with("chunk1chunk2")
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_process_message_decode_error(self):
        """Test message processing with decode error."""
        
        # Create a custom bytes-like class that raises decode error
        class BadBytes(bytes):
            def decode(self, *args, **kwargs):
                raise UnicodeDecodeError("utf-8", b"", 0, 1, "invalid")
        
        processor_func = AsyncMock()
        handler = AsyncServiceBusHandler(
            processor_function=processor_func,
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        # Mock the send_message method to prevent real Azure connections
        with patch.object(handler, 'send_message', new_callable=AsyncMock) as mock_send:
            mock_message = Mock()
            mock_message.message_id = "test-message-123"
            
            # Use our custom bytes class that will raise decode error
            mock_message.body = BadBytes(b"\xff\xfe")  # Invalid UTF-8 sequence
            
            await handler.process_message(mock_message)
            
            processor_func.assert_not_called()
            mock_send.assert_not_called()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_process_message_processor_exception(self):
        """Test message processing when processor function raises exception."""
        processor_func = AsyncMock(side_effect=Exception("Processing failed"))
        handler = AsyncServiceBusHandler(
            processor_function=processor_func,
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        mock_message = Mock()
        mock_message.message_id = "test-message-123"
        mock_message.body = b"test message content"
        
        # Should not raise exception, just log error
        await handler.process_message(mock_message)
        
        processor_func.assert_called_once_with("test message content")
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_process_message_no_message_id(self):
        """Test message processing when message has no ID."""
        processor_func = AsyncMock(return_value=None)
        handler = AsyncServiceBusHandler(
            processor_function=processor_func,
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        mock_message = Mock()
        # No message_id attribute
        del mock_message.message_id
        mock_message.body = b"test message content"
        
        await handler.process_message(mock_message)
        
        processor_func.assert_called_once_with("test message content")


class TestAsyncServiceBusHandlerSendMessage:
    """Test the send_message method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_send_message_string_success(self):
        """Test successful sending of string message."""
        handler = AsyncServiceBusHandler(
            processor_function=AsyncMock(),
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        mock_credential = AsyncMock()
        
        # Use regular Mock for service client to avoid coroutine issues
        mock_service_client = Mock()
        mock_sender = AsyncMock()
        
        # Set up the service client to return our async mock sender
        mock_service_client.get_queue_sender.return_value = mock_sender
        
        # Mock the async context managers
        mock_service_client.__aenter__ = AsyncMock(return_value=mock_service_client)
        mock_service_client.__aexit__ = AsyncMock(return_value=None)
        mock_sender.__aenter__ = AsyncMock(return_value=mock_sender)
        mock_sender.__aexit__ = AsyncMock(return_value=None)
        
        # Mock the async close methods
        mock_service_client.close = AsyncMock()
        mock_credential.close = AsyncMock()
        
        with patch('common_new.service_bus.DefaultAzureCredential', return_value=mock_credential):
            with patch('common_new.service_bus.ServiceBusClient', return_value=mock_service_client):
                result = await handler.send_message("test message")
                
                assert result is True
                mock_service_client.get_queue_sender.assert_called_once_with(queue_name="output-queue")
                mock_sender.send_messages.assert_called_once()
                mock_service_client.close.assert_called_once()
                mock_credential.close.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_send_message_dict_success(self):
        """Test successful sending of dictionary message."""
        handler = AsyncServiceBusHandler(
            processor_function=AsyncMock(),
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        mock_credential = AsyncMock()
        
        # Use regular Mock for service client to avoid coroutine issues
        mock_service_client = Mock()
        mock_sender = AsyncMock()
        
        # Set up the service client to return our async mock sender
        mock_service_client.get_queue_sender.return_value = mock_sender
        
        test_dict = {"key": "value", "number": 42}
        
        # Mock the async context managers
        mock_service_client.__aenter__ = AsyncMock(return_value=mock_service_client)
        mock_service_client.__aexit__ = AsyncMock(return_value=None)
        mock_sender.__aenter__ = AsyncMock(return_value=mock_sender)
        mock_sender.__aexit__ = AsyncMock(return_value=None)
        
        # Mock the async close methods
        mock_service_client.close = AsyncMock()
        mock_credential.close = AsyncMock()
        
        with patch('common_new.service_bus.DefaultAzureCredential', return_value=mock_credential):
            with patch('common_new.service_bus.ServiceBusClient', return_value=mock_service_client):
                with patch('common_new.service_bus.ServiceBusMessage') as mock_message_class:
                    # Create a mock message instance with the JSON content
                    mock_message = Mock()
                    mock_message.body = json.dumps(test_dict)
                    mock_message_class.return_value = mock_message
                    
                    result = await handler.send_message(test_dict)
                    
                    assert result is True
                    mock_sender.send_messages.assert_called_once()
                    # Verify JSON serialization was used by checking the ServiceBusMessage call
                    mock_message_class.assert_called_once_with(json.dumps(test_dict))
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_send_message_failure(self):
        """Test message sending failure."""
        handler = AsyncServiceBusHandler(
            processor_function=AsyncMock(),
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        mock_credential = AsyncMock()
        
        # Use regular Mock for service client to avoid coroutine issues
        mock_service_client = Mock()
        mock_sender = AsyncMock()
        mock_sender.send_messages.side_effect = Exception("Send failed")
        
        # Set up the service client to return our async mock sender
        mock_service_client.get_queue_sender.return_value = mock_sender
        
        # Mock the async context managers
        mock_service_client.__aenter__ = AsyncMock(return_value=mock_service_client)
        mock_service_client.__aexit__ = AsyncMock(return_value=None)
        mock_sender.__aenter__ = AsyncMock(return_value=mock_sender)
        mock_sender.__aexit__ = AsyncMock(return_value=None)
        
        # Mock the async close methods
        mock_service_client.close = AsyncMock()
        mock_credential.close = AsyncMock()
        
        with patch('common_new.service_bus.DefaultAzureCredential', return_value=mock_credential):
            with patch('common_new.service_bus.ServiceBusClient', return_value=mock_service_client):
                result = await handler.send_message("test message")
                
                assert result is False
                mock_service_client.close.assert_called_once()
                mock_credential.close.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_send_message_connection_failure(self):
        """Test message sending when connection fails."""
        handler = AsyncServiceBusHandler(
            processor_function=AsyncMock(),
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        with patch('common_new.service_bus.DefaultAzureCredential', side_effect=Exception("Auth failed")):
            result = await handler.send_message("test message")
            assert result is False


class TestAsyncServiceBusHandlerListen:
    """Test the listen method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_listen_processes_messages(self):
        """Test that listen processes messages from queue."""
        processor_func = AsyncMock(return_value=None)
        handler = AsyncServiceBusHandler(
            processor_function=processor_func,
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        mock_credential = AsyncMock()
        
        # Use regular Mock for service client to avoid coroutine issues
        mock_service_client = Mock()
        mock_receiver = AsyncMock()
        
        # Set up the service client to return our async mock receiver
        mock_service_client.get_queue_receiver.return_value = mock_receiver
        
        # Create mock message
        mock_message = Mock()
        mock_message.message_id = "test-msg-1"
        mock_message.body = b"test content"
        
        call_count = 0
        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [mock_message]
            else:
                # Stop the listen loop after first iteration
                handler.running = False
                return []
        
        mock_receiver.receive_messages.side_effect = side_effect
        mock_receiver.complete_message.return_value = None
        
        # Mock the async context managers
        mock_service_client.__aenter__ = AsyncMock(return_value=mock_service_client)
        mock_service_client.__aexit__ = AsyncMock(return_value=None)
        mock_receiver.__aenter__ = AsyncMock(return_value=mock_receiver)
        mock_receiver.__aexit__ = AsyncMock(return_value=None)
        
        # Mock the async close methods
        mock_service_client.close = AsyncMock()
        mock_credential.close = AsyncMock()
        
        with patch('common_new.service_bus.DefaultAzureCredential', return_value=mock_credential):
            with patch('common_new.service_bus.ServiceBusClient', return_value=mock_service_client):
                with patch('asyncio.sleep') as mock_sleep:  # Mock asyncio.sleep to prevent delays
                    await handler.listen()
                    
                    mock_receiver.complete_message.assert_called_with(mock_message)
                    processor_func.assert_called_with("test content")
                    assert handler.total_processed_messages == 1
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_listen_no_messages(self):
        """Test listen behavior when no messages are available."""
        processor_func = AsyncMock()
        handler = AsyncServiceBusHandler(
            processor_function=processor_func,
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        mock_credential = AsyncMock()
        
        # Use regular Mock for service client to avoid coroutine issues
        mock_service_client = Mock()
        mock_receiver = AsyncMock()
        
        # Set up the service client to return our async mock receiver
        mock_service_client.get_queue_receiver.return_value = mock_receiver
        
        call_count = 0
        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return []  # No messages
            else:
                handler.running = False
                return []
        
        mock_receiver.receive_messages.side_effect = side_effect
        
        # Mock the async context managers
        mock_service_client.__aenter__ = AsyncMock(return_value=mock_service_client)
        mock_service_client.__aexit__ = AsyncMock(return_value=None)
        mock_receiver.__aenter__ = AsyncMock(return_value=mock_receiver)
        mock_receiver.__aexit__ = AsyncMock(return_value=None)
        
        # Mock the async close methods
        mock_service_client.close = AsyncMock()
        mock_credential.close = AsyncMock()
        
        with patch('common_new.service_bus.DefaultAzureCredential', return_value=mock_credential):
            with patch('common_new.service_bus.ServiceBusClient', return_value=mock_service_client):
                with patch('asyncio.sleep') as mock_sleep:  # Mock asyncio.sleep to prevent delays
                    await handler.listen()
                    
                    processor_func.assert_not_called()
                    assert handler.total_processed_messages == 0
                    # Sleep time should increase when no messages
                    assert handler.sleep_seconds > 4
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_listen_connection_error(self):
        """Test listen behavior with connection errors."""
        processor_func = AsyncMock()
        handler = AsyncServiceBusHandler(
            processor_function=processor_func,
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net",
            retry_delay=0.1  # Short delay for testing
        )
        
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Connection failed")
            else:
                handler.running = False  # Stop after retry
                
        with patch('common_new.service_bus.DefaultAzureCredential', side_effect=side_effect):
            with patch('asyncio.sleep') as mock_sleep:
                await handler.listen()
                
                # Should have attempted retry with sleep
                mock_sleep.assert_called()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_listen_message_processing_error(self):
        """Test listen behavior when message processing fails."""
        processor_func = AsyncMock(side_effect=Exception("Processing failed"))
        handler = AsyncServiceBusHandler(
            processor_function=processor_func,
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        mock_credential = AsyncMock()
        
        # Use regular Mock for service client to avoid coroutine issues
        mock_service_client = Mock()
        mock_receiver = AsyncMock()
        
        # Set up the service client to return our async mock receiver
        mock_service_client.get_queue_receiver.return_value = mock_receiver
        
        # Create mock message
        mock_message = Mock()
        mock_message.message_id = "test-msg-1"
        mock_message.body = b"test content"
        
        call_count = 0
        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [mock_message]
            else:
                handler.running = False
                return []
        
        mock_receiver.receive_messages.side_effect = side_effect
        mock_receiver.complete_message.return_value = None
        
        # Mock the async context managers
        mock_service_client.__aenter__ = AsyncMock(return_value=mock_service_client)
        mock_service_client.__aexit__ = AsyncMock(return_value=None)
        mock_receiver.__aenter__ = AsyncMock(return_value=mock_receiver)
        mock_receiver.__aexit__ = AsyncMock(return_value=None)
        
        # Mock the async close methods
        mock_service_client.close = AsyncMock()
        mock_credential.close = AsyncMock()
        
        with patch('common_new.service_bus.DefaultAzureCredential', return_value=mock_credential):
            with patch('common_new.service_bus.ServiceBusClient', return_value=mock_service_client):
                with patch('asyncio.sleep') as mock_sleep:  # Mock asyncio.sleep to prevent delays
                    await handler.listen()
                    
                    # Message should still be completed even if processing fails
                    mock_receiver.complete_message.assert_called_with(mock_message)
                    # Total processed should still increment
                    assert handler.total_processed_messages == 1
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_listen_complete_message_error(self):
        """Test listen behavior when message completion fails."""
        processor_func = AsyncMock(return_value=None)
        handler = AsyncServiceBusHandler(
            processor_function=processor_func,
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        mock_credential = AsyncMock()
        
        # Use regular Mock for service client to avoid coroutine issues
        mock_service_client = Mock()
        mock_receiver = AsyncMock()
        
        # Set up the service client to return our async mock receiver
        mock_service_client.get_queue_receiver.return_value = mock_receiver
        
        # Create mock message
        mock_message = Mock()
        mock_message.message_id = "test-msg-1"
        mock_message.body = b"test content"
        
        mock_receiver.complete_message.side_effect = Exception("Complete failed")
        
        call_count = 0
        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [mock_message]
            else:
                handler.running = False
                return []
        
        mock_receiver.receive_messages.side_effect = side_effect
        
        # Mock the async context managers
        mock_service_client.__aenter__ = AsyncMock(return_value=mock_service_client)
        mock_service_client.__aexit__ = AsyncMock(return_value=None)
        mock_receiver.__aenter__ = AsyncMock(return_value=mock_receiver)
        mock_receiver.__aexit__ = AsyncMock(return_value=None)
        
        # Mock the async close methods
        mock_service_client.close = AsyncMock()
        mock_credential.close = AsyncMock()
        
        with patch('common_new.service_bus.DefaultAzureCredential', return_value=mock_credential):
            with patch('common_new.service_bus.ServiceBusClient', return_value=mock_service_client):
                with patch('asyncio.sleep') as mock_sleep:  # Mock asyncio.sleep to prevent delays
                    await handler.listen()
                    
                    # Should continue processing despite completion failure
                    processor_func.assert_called_with("test content")
                    assert handler.total_processed_messages == 1


class TestAsyncServiceBusHandlerStop:
    """Test the stop method."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_stop_running_handler(self):
        """Test stopping a running handler."""
        handler = AsyncServiceBusHandler(
            processor_function=AsyncMock(),
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        handler.running = True
        
        await handler.stop()
        
        assert not handler.running
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_stop_already_stopped_handler(self):
        """Test stopping a handler that's already stopped."""
        handler = AsyncServiceBusHandler(
            processor_function=AsyncMock(),
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        handler.running = False
        
        await handler.stop()
        
        assert not handler.running


class TestAsyncServiceBusHandlerIntegration:
    """Integration tests for AsyncServiceBusHandler."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_sleep_time_adjustment(self):
        """Test that sleep time adjusts based on message activity."""
        processor_func = AsyncMock(return_value=None)
        handler = AsyncServiceBusHandler(
            processor_function=processor_func,
            in_queue_name="input-queue",
            out_queue_name="output-queue",
            fully_qualified_namespace="test.servicebus.windows.net"
        )
        
        initial_sleep = handler.sleep_seconds
        
        mock_credential = AsyncMock()
        
        # Use regular Mock for service client to avoid coroutine issues
        mock_service_client = Mock()
        mock_receiver = AsyncMock()
        
        # Set up the service client to return our async mock receiver
        mock_service_client.get_queue_receiver.return_value = mock_receiver
        
        # Create mock message
        mock_message = Mock()
        mock_message.message_id = "test-msg-1"
        mock_message.body = b"test content"
        
        call_count = 0
        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [mock_message]  # First call has messages (sleep resets to 1)
            elif call_count == 2:
                return []  # Second call has no messages (sleep goes to 2)
            elif call_count == 3:
                return []  # Third call has no messages (sleep goes to 3)
            elif call_count == 4:
                return []  # Fourth call has no messages (sleep goes to 4)
            elif call_count == 5:
                return []  # Fifth call has no messages (sleep goes to 5, now > initial_sleep)
            else:
                handler.running = False
                return []
        
        mock_receiver.receive_messages.side_effect = side_effect
        mock_receiver.complete_message.return_value = None
        
        # Mock the async context managers
        mock_service_client.__aenter__ = AsyncMock(return_value=mock_service_client)
        mock_service_client.__aexit__ = AsyncMock(return_value=None)
        mock_receiver.__aenter__ = AsyncMock(return_value=mock_receiver)
        mock_receiver.__aexit__ = AsyncMock(return_value=None)
        
        # Mock the async close methods
        mock_service_client.close = AsyncMock()
        mock_credential.close = AsyncMock()
        
        with patch('common_new.service_bus.DefaultAzureCredential', return_value=mock_credential):
            with patch('common_new.service_bus.ServiceBusClient', return_value=mock_service_client):
                with patch('asyncio.sleep') as mock_sleep:
                    await handler.listen()
                    
                    # Sleep time should reset to 1 after processing messages
                    # then increase when no messages are found
                    sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
                    assert 1 in sleep_calls  # Reset after processing
                    assert any(s > initial_sleep for s in sleep_calls)  # Increased when idle 