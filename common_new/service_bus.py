# service_bus.py
import asyncio
import json
import time
from typing import Callable, Any, Optional
from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage
from azure.servicebus.exceptions import ServiceBusError, ServiceBusConnectionError
from azure.identity.aio import DefaultAzureCredential

from common.logger import get_logger

logger = get_logger("common")

class AsyncServiceBusHandler:
    """
    Async handler for Azure Service Bus operations with simplified robust error handling
    using fresh connections for each operation and adaptive sleep timing.
    """
    def __init__(
        self,
        processor_function: Callable,
        in_queue_name: str,
        out_queue_name: str,
        fully_qualified_namespace: str,
        max_retries: int = 5,
        retry_delay: float = 3.0,
        max_wait_time: float = 3.0,
        message_batch_size: int = 1
    ):
        self.fully_qualified_namespace = fully_qualified_namespace
        self.in_queue_name = in_queue_name
        self.out_queue_name = out_queue_name
        self.processor_function = processor_function
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.max_wait_time = max_wait_time
        self.message_batch_size = message_batch_size
        self.running = False
        
        # Service Bus resources - initialized for each operation
        self.total_processed_messages = 0
        self.sleep_seconds = 4

    async def process_message(self, message) -> None:
        """Process a single message with robust error handling."""
        message_id = str(message.message_id) if hasattr(message, "message_id") else "unknown"
        logger.info(f"Processing message {message_id}")
        
        try:
            # Extract message body first
            message_body = None
            try:
                body = message.body
                if isinstance(body, bytes):
                    message_body = body.decode('utf-8')
                elif isinstance(body, str):
                    message_body = body
                elif hasattr(body, '__iter__') and not isinstance(body, (bytes, str)):
                    # Handle generator case
                    message_body_bytes = b''.join(chunk for chunk in body)
                    message_body = message_body_bytes.decode('utf-8')
                else:
                    message_body = str(body)
            except Exception as decode_err:
                logger.error(f"Failed to decode message {message_id}: {str(decode_err)}")
                return
            
            # Process message
            logger.debug(f"Calling processor function for message {message_id}")
            result = await self.processor_function(message_body)
            
            # Send result if present
            if result:
                await self.send_message(result)
                logger.info(f"Sent processing result for message {message_id}")
                
        except Exception as e:
            logger.error(f"Error processing message {message_id}: {str(e)}")
        
    async def send_message(self, message_body: Any) -> bool:
        """Send a message to the out queue using a fresh connection."""
        logger.info("Sending message to out_queue")
        try:
            # Follow the pattern from service_bus_mock.py
            logger.debug("Creating fresh credential for sending message")
            credential = DefaultAzureCredential()
            
            logger.debug(f"Creating fresh service bus client for {self.fully_qualified_namespace}")
            servicebus_client = ServiceBusClient(
                fully_qualified_namespace=self.fully_qualified_namespace,
                credential=credential,
                retry_total=self.max_retries,
                retry_backoff_factor=self.retry_delay / 2,
                retry_mode='exponential',
                logging_enable=True
            )
            
            try:
                async with servicebus_client:
                    logger.debug(f"Creating sender for queue: {self.out_queue_name}")
                    sender = servicebus_client.get_queue_sender(
                        queue_name=self.out_queue_name
                    )
                    
                    # Use context manager for automatic cleanup
                    async with sender:
                        # Convert message to appropriate format
                        if isinstance(message_body, str):
                            message = ServiceBusMessage(message_body)
                        else:
                            message = ServiceBusMessage(json.dumps(message_body))
                        
                        # Send message
                        await sender.send_messages(message)
                        logger.debug("Message sent successfully to out_queue")
                        return True
            finally:
                # Extra cleanup in case context manager fails to handle it
                if servicebus_client:
                    await servicebus_client.close()
                if credential:
                    await credential.close()
                    
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return False

    async def listen(self) -> None:
        """
        Start listening for messages using fresh connections for each cycle
        and adaptive sleep timing based on message processing activity.
        """
        self.running = True
        logger.info(f"Starting Service Bus listener for {self.in_queue_name}")
        
        while self.running:
            processed_messages = 0
            try:
                # Create fresh connections for each cycle
                logger.info("Creating credential for Service Bus")
                credential = DefaultAzureCredential()
                
                logger.info(f"Creating Service Bus client for {self.fully_qualified_namespace}")
                servicebus_client = ServiceBusClient(
                    fully_qualified_namespace=self.fully_qualified_namespace,
                    credential=credential,
                    retry_total=self.max_retries,
                    retry_backoff_factor=self.retry_delay / 2,
                    retry_mode='exponential',
                    logging_enable=True
                )
                
                try:
                    async with servicebus_client:
                        logger.info(f"Connecting to input queue: {self.in_queue_name}")
                        receiver = servicebus_client.get_queue_receiver(
                            queue_name=self.in_queue_name
                        )
                        
                        async with receiver:
                            # Receive messages with short timeout
                            logger.info(f"Attempting to receive up to {self.message_batch_size} messages")
                            received_msgs = await receiver.receive_messages(
                                max_wait_time=self.max_wait_time,
                                max_message_count=self.message_batch_size
                            )
                            
                            if not received_msgs:
                                logger.info("No messages to process")
                            else:
                                logger.info(f"Received {len(received_msgs)} messages")
                                
                                # Process each message, individually handle errors
                                for msg in received_msgs:
                                    try:
                                        # First complete the message to prevent reprocessing
                                        try:
                                            await receiver.complete_message(msg)
                                            logger.debug(f"Marked message as complete")
                                        except Exception as complete_err:
                                            logger.warning(f"Failed to complete message: {str(complete_err)}")
                                        
                                        # Then process the message
                                        await self.process_message(msg)
                                        processed_messages += 1
                                    except Exception as e:
                                        logger.error(f"Error in message processing loop: {str(e)}")
                                        # Continue with next message
                finally:
                    # Ensure resources are cleaned up even if context managers fail
                    if servicebus_client:
                        await servicebus_client.close()
                    if credential:
                        await credential.close()
                
                # Update total messages processed
                self.total_processed_messages += processed_messages
                
                # Adjust sleep time based on message activity
                if processed_messages > 0:
                    self.sleep_seconds = 1  # Reset to minimum if messages were found
                else:
                    # Gradually increase sleep time when queue is empty
                    if self.sleep_seconds < 10:
                        self.sleep_seconds += 1
                
                logger.info(f"{processed_messages} messages processed in this batch -> sleep for {self.sleep_seconds} seconds")
                logger.info(f"{self.total_processed_messages} messages processed since the start of the service")
                
                # Wait before next cycle if still running
                if self.running:
                    await asyncio.sleep(self.sleep_seconds)
                    
            except Exception as e:
                logger.error(f"Critical error in main listen loop: {str(e)}")
                # Wait before retry
                if self.running:
                    await asyncio.sleep(self.retry_delay)
        
        logger.info("Listener stopped")

    async def stop(self) -> None:
        """Stop listening and clean up resources."""
        if self.running:
            logger.info("Stopping Service Bus handler...")
            self.running = False
            logger.info("Service Bus handler stopped")
        else:
            logger.info("Handler already stopped")
