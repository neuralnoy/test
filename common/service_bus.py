# service_bus.py
import asyncio
import time
from typing import Callable, Any
from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage
from azure.servicebus.exceptions import ServiceBusError, ServiceBusConnectionError
from azure.identity.aio import DefaultAzureCredential

from common.logger import get_logger

logger = get_logger("common")

class AsyncServiceBusHandler:
    """
    Async handler for Azure Service Bus operations with robust error handling,
    exponential backoff for empty queues, and improved connection stability.
    """
    def __init__(
        self,
        processor_function: Callable,
        in_queue_name: str,
        out_queue_name: str,
        fully_qualified_namespace: str,
        max_retries: int = 3,
        retry_delay: float = 5.0,  # Increased default retry delay
        min_wait_time: float = 1.0,
        max_wait_time: float = 60.0, # Increased max backoff wait
        backoff_factor: float = 1.5,
        receive_max_wait_time: float = 30.0 # Longer receive wait time
    ):
        self.fully_qualified_namespace = fully_qualified_namespace
        self.in_queue_name = in_queue_name
        self.out_queue_name = out_queue_name
        self.processor_function = processor_function
        self.max_retries = max_retries
        self.retry_delay = retry_delay # Use this for connection retries
        self.servicebus_client = None
        self.credential = None
        self.receiver = None
        self.sender = None
        self.running = False
        self.connection_healthy = False # Flag to indicate if we believe connection is OK

        # Exponential backoff parameters for empty queue polling
        self.min_wait_time = min_wait_time
        self.max_wait_time = max_wait_time # Max wait *between* receive attempts when queue empty
        self.backoff_factor = backoff_factor
        self.current_wait_time = min_wait_time
        self.consecutive_empty_polls = 0
        
        # Receiver configuration
        self.receive_max_wait_time = receive_max_wait_time # Max time for one receive_messages call

    async def _check_connection_health(self) -> bool:
        """Simplified check: Assumes healthy unless an error forced reconnection."""
        # Primarily checks if resources are initialized. Actual health is determined by operation success/failure.
        if not self.servicebus_client or not self.receiver or not self.sender:
            logger.warning("Connection check failed: Resources not initialized.")
            self.connection_healthy = False
            return False
            
        # If an error handler set this to False, respect it.
        if not self.connection_healthy:
             logger.warning("Connection check failed: Marked unhealthy by previous error.")
             return False

        # Assume healthy otherwise. Let operations prove otherwise.
        logger.debug("Connection check: Assuming healthy.")
        return True

    async def _ensure_connection(self) -> bool:
        """Ensure connection is active. Re-initializes if marked unhealthy or not initialized."""
        if await self._check_connection_health():
            return True
            
        logger.info("Attempting to reinitialize Service Bus client due to unhealthy or uninitialized state.")
        for attempt in range(self.max_retries):
            try:
                await self._cleanup_resources() # Clean up before attempting init
                await self.initialize()
                logger.info(f"Successfully reinitialized connection on attempt {attempt + 1}")
                self.connection_healthy = True # Mark as healthy after successful init
                return True
            except Exception as e:
                logger.error(f"Failed to reinitialize connection on attempt {attempt + 1}/{self.max_retries}: {str(e)}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1)) # Exponential backoff for re-init
                else:
                    logger.critical("Failed to reinitialize connection after multiple retries. Stopping listener.")
                    self.running = False # Stop running if connection cannot be established
                    return False
        return False # Should not be reached if self.running is set False, but included for completeness

    async def _cleanup_resources(self) -> None:
        """Clean up all Service Bus resources."""
        logger.debug("Cleaning up Service Bus resources...")
        try:
            if self.receiver:
                logger.debug("Closing receiver...")
                await self.receiver.close()
                self.receiver = None
                logger.debug("Receiver closed.")
            if self.sender:
                logger.debug("Closing sender...")
                await self.sender.close()
                self.sender = None
                logger.debug("Sender closed.")
            if self.servicebus_client:
                logger.debug("Closing servicebus client...")
                await self.servicebus_client.close()
                self.servicebus_client = None
                logger.debug("Servicebus client closed.")
            if self.credential:
                 logger.debug("Closing credential...")
                 await self.credential.close()
                 self.credential = None
                 logger.debug("Credential closed.")
        except Exception as e:
            logger.error(f"Error during resource cleanup: {str(e)}")
        finally:
            self.connection_healthy = False # Always mark unhealthy after cleanup
            logger.debug("Finished cleaning up resources.")

    async def initialize(self) -> None:
        """Initialize the Service Bus client, sender and receiver."""
        # Does not clean up here - _ensure_connection handles cleanup before calling initialize
        try:
            self.credential = DefaultAzureCredential()
            self.servicebus_client = ServiceBusClient(
                fully_qualified_namespace=self.fully_qualified_namespace,
                credential=self.credential,
                retry_total=self.max_retries, # Configure SDK retries
                retry_backoff_factor=self.retry_delay / 2, # Relate SDK backoff to our delay
                retry_mode='exponential'
            )
            logger.info(f"Initialized Service Bus client using DefaultAzureCredential for {self.fully_qualified_namespace}")

            # Initialize receiver and sender
            self.receiver = self.servicebus_client.get_queue_receiver(
                queue_name=self.in_queue_name,
                # Consider adding prefetch_count if needed for performance
                # prefetch_count = 10
            )
            logger.info(f"Initialized receiver for queue: {self.in_queue_name}")
            
            self.sender = self.servicebus_client.get_queue_sender(
                queue_name=self.out_queue_name
            )
            logger.info(f"Initialized sender for queue: {self.out_queue_name}")

            self.running = True
            self.connection_healthy = True # Mark healthy after successful initialization
            logger.info(f"Initialized Service Bus handler for queues: {self.in_queue_name} -> {self.out_queue_name}")
        
        except Exception as e:
            self.connection_healthy = False # Mark unhealthy on init failure
            logger.error(f"Failed to initialize Service Bus: {str(e)}")
            # Propagate the error to let _ensure_connection handle retries/stopping
            raise

    async def process_message(self, message) -> None:
        """Process a single message with immediate completion."""
        # Reset backoff when processing messages
        self.consecutive_empty_polls = 0
        self.current_wait_time = self.min_wait_time
        
        message_id = str(message.message_id)
        logger.info(f"Processing message {message_id}")
        
        try:
            # Complete the message immediately
            # Note: If processing fails often, consider moving completion after successful processing
            # or implementing a dead-letter strategy.
            await self.receiver.complete_message(message)
            logger.info(f"Marked message {message_id} as complete immediately")
        except ServiceBusError as complete_err:
             # Check if it's a lock expiry error (checking string is fragile but often necessary)
             if "lock expired" in str(complete_err).lower():
                 logger.warning(f"Message lock expired for message {message_id} before completion. Message might be processed again.")
                 # Cannot complete anymore, just log and continue processing if possible
             else:
                 logger.error(f"Failed to complete message {message_id}: {complete_err}")
                 # Depending on the error, might need specific handling. For now, log and proceed.
        except Exception as e:
             logger.error(f"Unexpected error completing message {message_id}: {e}")

        try:
            # Convert message body to string, handling generator case
            message_body = message.body
            
            # Handle generator or bytes-like message body
            if hasattr(message_body, '__iter__') and not isinstance(message_body, (bytes, str)):
                try:
                    message_body_bytes = b''.join(chunk for chunk in message_body)
                    message_body = message_body_bytes.decode('utf-8')
                except Exception as e:
                    logger.error(f"Failed to process generator message body: {str(e)}")
                    message_body = str(message_body) # Fallback
            elif isinstance(message_body, bytes):
                message_body = message_body.decode('utf-8')
            elif not isinstance(message_body, str):
                message_body = str(message_body)
            
            # Process the message using the provided function
            result = await self.processor_function(message_body)
            
            # Send the result to the out queue if there is one
            if result:
                await self.send_message(result)
                logger.info(f"Sent processing result for message {message_id}")
            else:
                logger.warning(f"No result returned from processor for message {message_id}")
            
        except Exception as e:
            logger.error(f"Error processing message {message_id} payload: {str(e)}")
            # Error message should ideally be handled and potentially sent by processor_function
            # If processor_function raises, we log it here.

    async def send_message(self, message_body: Any) -> None:
        """Send a message to the out queue with retry logic handled by the SDK."""
        # Simplified: Rely on SDK's built-in retry for sending
        try:
            if not self.sender:
                logger.warning("Sender not initialized. Attempting to reinitialize...")
                if not await self._ensure_connection():
                    logger.error("Failed to reinitialize sender. Cannot send message.")
                    return
                if not self.sender:
                    logger.error("Sender still not initialized after reconnection attempt.")
                    return

            if isinstance(message_body, str):
                message = ServiceBusMessage(message_body)
            else:
                import json
                message = ServiceBusMessage(json.dumps(message_body))
            
            await self.sender.send_messages(message)
            logger.debug("Message sent successfully to out_queue.")

        except ServiceBusConnectionError as conn_err:
             logger.error(f"Connection error sending message: {conn_err}. Marking connection as unhealthy.")
             self.connection_healthy = False # Trigger re-connection in the main loop
             raise # Re-raise to potentially stop processing if needed, or let loop handle reconnect
        except ServiceBusError as sbe:
            # Log other Service Bus errors during send
            logger.error(f"ServiceBus error sending message: {sbe}")
            # Depending on the error, may need specific handling or just rely on SDK retry.
            # If error persists, connection might be unhealthy.
            # Consider adding logic here to mark unhealthy on persistent send errors.
            raise # Re-raise
        except Exception as e:
            logger.error(f"Unexpected error sending message: {e}")
            raise # Re-raise

    async def listen(self) -> None:
        """
        Start listening for messages on the in_queue and process them.
        Relies on SDK for retries and handles connection errors robustly.
        """
        logger.info(f"Attempting to initialize listener for queue: {self.in_queue_name}")
        if not await self._ensure_connection():
             logger.critical("Initial connection failed. Listener cannot start.")
             return # Stop if initial connection fails

        logger.info(f"Starting listener loop for queue: {self.in_queue_name}")
        
        while self.running:
            try:
                # 1. Ensure Connection is Active (or re-establish)
                if not await self._ensure_connection():
                    # _ensure_connection already logged critical error and set self.running=False if failed permanently
                    if self.running:
                         logger.warning("Connection lost and failed to re-establish immediately. Waiting before retry...")
                         await asyncio.sleep(self.retry_delay)
                    continue # Try ensuring connection again in the next loop iteration

                # 2. Receive Messages
                logger.debug(f"Attempting to receive messages (max wait: {self.receive_max_wait_time}s)")
                if not self.receiver:
                     logger.error("Receiver is None, cannot receive. Connection issue likely.")
                     self.connection_healthy = False # Mark unhealthy to trigger re-init
                     await asyncio.sleep(self.retry_delay)
                     continue

                messages = await self.receiver.receive_messages(
                    max_message_count=10,
                    max_wait_time=self.receive_max_wait_time
                )

                if messages:
                    logger.info(f"Received {len(messages)} messages.")
                    # Reset backoff state since we received messages
                    self.consecutive_empty_polls = 0
                    self.current_wait_time = self.min_wait_time
                    
                    # Process messages concurrently
                    await asyncio.gather(*[self.process_message(message) for message in messages])
                    # Add a small sleep after processing a batch to yield control
                    await asyncio.sleep(0.01) 

                else:
                    # No messages received - Apply backoff
                    self.consecutive_empty_polls += 1
                    logger.debug(f"No messages received. Consecutive empty polls: {self.consecutive_empty_polls}")
                    
                    # Calculate next wait time
                    wait_time = min(self.current_wait_time * (self.backoff_factor ** self.consecutive_empty_polls), self.max_wait_time)
                    # Add jitter
                    wait_time = wait_time * (1 + (0.2 * (time.time() % 1) - 0.1)) # +/- 10% jitter
                    wait_time = max(self.min_wait_time, wait_time) # Ensure minimum wait
                    
                    logger.debug(f"Waiting for {wait_time:.2f}s before next receive attempt.")
                    await asyncio.sleep(wait_time)
                    self.current_wait_time = wait_time # Update for potential next empty poll

            except ServiceBusConnectionError as conn_err:
                logger.error(f"Connection Error during receive: {conn_err}. Marking connection unhealthy.")
                self.connection_healthy = False
                # No sleep here, _ensure_connection at the start of the loop will handle delays/retries

            except ServiceBusError as sbe:
                 error_str = str(sbe).lower()
                 if "handler has already shutdown" in error_str:
                      logger.warning(f"Receiver Error: {sbe}. Handler shutdown detected. Marking unhealthy.")
                      self.connection_healthy = False
                 # Check for lock expiry within the broader ServiceBusError catch
                 elif "lock expired" in error_str:
                      logger.warning(f"Message lock expired during receive/processing: {sbe}")
                      # Lock expired is usually handled per message, but if it bubbles up, log it.
                      # Don't necessarily mark connection as unhealthy for this.
                 else:
                      # Other ServiceBus errors might be transient or indicate deeper issues
                      logger.error(f"ServiceBus Error during receive: {sbe}")
                      # Consider marking unhealthy for persistent or specific other errors
                      # For now, rely on SDK retries and the connection check loop
                      await asyncio.sleep(self.retry_delay / 2) # Short wait before next attempt for non-connection SB errors

            except Exception as e:
                logger.error(f"Unexpected error in listener loop: {str(e)}")
                # Check if it's the specific shutdown error
                if "handler has already shutdown" in str(e).lower():
                     logger.warning("Unexpected error indicates handler shutdown. Marking unhealthy.")
                     self.connection_healthy = False
                else:
                     # For other unexpected errors, maybe wait briefly before retrying
                     await asyncio.sleep(self.retry_delay)
                 # Let the _ensure_connection handle the recovery logic in the next iteration

        # End of while self.running loop
        logger.info("Listener loop exiting.")
        await self._cleanup_resources()

    async def stop(self) -> None:
        """Stop listening and clean up resources."""
        if self.running:
            self.running = False
            logger.info("Stopping Service Bus handler...")
            # Cleanup is handled by the finally block in listen() when the loop exits
        else:
             logger.info("Handler already stopped.")
