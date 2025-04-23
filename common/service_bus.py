import asyncio
from typing import Callable, Any
from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage
from azure.core.exceptions import ServiceBusError
from azure.identity.aio import DefaultAzureCredential

from common.logger import get_logger

logger = get_logger("service_bus")

class AsyncServiceBusHandler:
    """
    Async handler for Azure Service Bus operations with robust error handling.
    """
    def __init__(
        self,
        processor_function: Callable,
        in_queue_name: str,
        out_queue_name: str,
        fully_qualified_namespace: str,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        max_message_lock_renewal: int = 5,
        message_lock_renewal_interval: float = 30.0
    ):
        self.fully_qualified_namespace = fully_qualified_namespace
        self.in_queue_name = in_queue_name
        self.out_queue_name = out_queue_name
        self.processor_function = processor_function
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.max_message_lock_renewal = max_message_lock_renewal
        self.message_lock_renewal_interval = message_lock_renewal_interval
        self.servicebus_client = None
        self.credential = None
        self.receiver = None
        self.sender = None
        self.running = False
        self.lock_renewal_tasks = {}

    async def initialize(self) -> None:
        """Initialize the Service Bus client, sender and receiver."""
        try:
            self.credential = DefaultAzureCredential()
            self.servicebus_client = ServiceBusClient(
                fully_qualified_namespace=self.fully_qualified_namespace,
                credential=self.credential
            )
            logger.info(f"Initialized Service Bus client using DefaultAzureCredential for {self.fully_qualified_namespace}")
            
            self.receiver = self.servicebus_client.get_queue_receiver(
                queue_name=self.in_queue_name
            )
            self.sender = self.servicebus_client.get_queue_sender(
                queue_name=self.out_queue_name
            )
            self.running = True
            logger.info(f"Initialized Service Bus handler for queues: {self.in_queue_name} -> {self.out_queue_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Service Bus: {str(e)}")
            raise

    async def _renew_message_lock(self, message, message_id) -> None:
        """Renew message lock periodically to prevent message unlock during processing."""
        renewal_count = 0
        while message_id in self.lock_renewal_tasks and renewal_count < self.max_message_lock_renewal:
            try:
                await asyncio.sleep(self.message_lock_renewal_interval)
                await self.receiver.renew_message_lock(message)
                renewal_count += 1
                logger.debug(f"Renewed lock for message {message_id}, renewal count: {renewal_count}")
            except Exception as e:
                logger.error(f"Failed to renew message lock for {message_id}: {str(e)}")
                break

    async def _start_lock_renewal(self, message) -> str:
        """Start the lock renewal task for a message."""
        message_id = str(message.message_id)
        self.lock_renewal_tasks[message_id] = asyncio.create_task(
            self._renew_message_lock(message, message_id)
        )
        return message_id

    async def _stop_lock_renewal(self, message_id: str) -> None:
        """Stop the lock renewal task for a message."""
        if message_id in self.lock_renewal_tasks:
            task = self.lock_renewal_tasks.pop(message_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.debug(f"Stopped lock renewal for message {message_id}")

    async def process_message(self, message) -> None:
        """Process a single message with error handling and lock renewal."""
        message_id = await self._start_lock_renewal(message)
        logger.info(f"Processing message {message_id}")
        
        try:
            # Convert message body to JSON or appropriate format
            message_body = message.body.decode('utf-8')
            
            # Process the message using the provided function
            result = await self.processor_function(message_body)
            
            # Send the result to the out queue
            if result:
                await self.send_message(result)
                logger.info(f"Successfully processed and sent message {message_id}")
            
            # Complete the message
            await self.receiver.complete_message(message)
            logger.info(f"Completed message {message_id}")
            
        except Exception as e:
            logger.error(f"Error processing message {message_id}: {str(e)}")
            # Abandon the message to make it available again after the lock duration
            try:
                await self.receiver.abandon_message(message)
                logger.info(f"Abandoned message {message_id} due to processing error")
            except Exception as abandon_error:
                logger.error(f"Error abandoning message {message_id}: {str(abandon_error)}")
        finally:
            # Stop the lock renewal task
            await self._stop_lock_renewal(message_id)

    async def send_message(self, message_body: Any) -> None:
        """Send a message to the out queue with retry logic."""
        retry_count = 0
        while retry_count < self.max_retries:
            try:
                if isinstance(message_body, str):
                    message = ServiceBusMessage(message_body)
                else:
                    # Convert to string if it's not already one
                    import json
                    message = ServiceBusMessage(json.dumps(message_body))
                
                await self.sender.send_messages(message)
                return
            except Exception as e:
                retry_count += 1
                logger.error(f"Error sending message, attempt {retry_count}/{self.max_retries}: {str(e)}")
                if retry_count < self.max_retries:
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(f"Failed to send message after {self.max_retries} attempts")
                    raise

    async def listen(self) -> None:
        """
        Start listening for messages on the in_queue and process them.
        This method runs indefinitely until stop() is called.
        """
        if not self.running:
            await self.initialize()
        
        logger.info(f"Starting to listen on queue: {self.in_queue_name}")
        
        try:
            while self.running:
                try:
                    # Receive messages in batches with a timeout
                    async with self.receiver:
                        messages = await self.receiver.receive_messages(max_message_count=10, max_wait_time=5)
                        
                        if messages:
                            logger.info(f"Received {len(messages)} messages")
                            # Process messages concurrently
                            await asyncio.gather(*[self.process_message(message) for message in messages])
                        
                except ServiceBusError as sbe:
                    logger.error(f"ServiceBus error while receiving messages: {str(sbe)}")
                    await asyncio.sleep(self.retry_delay)
                except Exception as e:
                    logger.error(f"Unexpected error while receiving messages: {str(e)}")
                    await asyncio.sleep(self.retry_delay)
        
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop listening and clean up resources."""
        self.running = False
        logger.info("Stopping Service Bus handler")
        
        # Cancel all lock renewal tasks
        for message_id in list(self.lock_renewal_tasks.keys()):
            await self._stop_lock_renewal(message_id)
        
        # Close the client connections
        if self.servicebus_client:
            await self.servicebus_client.close()
            if self.credential:
                await self.credential.close()
            logger.info("Closed ServiceBus client")
