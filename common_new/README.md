# Common Library for AI Microservices

## Overview
The Common Library provides shared utilities, services, and functionality that are used across multiple microservices in the system. It creates a consistent foundation for interacting with Azure services, handling errors, managing logging, and implementing retry logic.

## Key Components

### Azure OpenAI Service
A comprehensive client for interacting with Azure-hosted OpenAI models.

#### Technical Details
- **Class**: `AzureOpenAIService`
- **File**: `azure_openai_service.py`
- **Authentication**: Uses Azure Identity with `DefaultAzureCredential` for secure authentication
- **Token Management**: Integrates with `TokenClient` for preventing rate limit issues through token tracking and allocation
- **API Version Management**: Configurable API version for Azure OpenAI
- **Model Deployment Flexibility**: Works with deployments and base models

#### Methods
- `__init__(model, app_id, token_counter_url, token_counter_resource_uri)`: Initializes the service with specified parameters
- `chat_completion(messages, model, temperature, max_tokens, top_p, frequency_penalty, presence_penalty, stop)`: Sends requests to Azure OpenAI chat models with token tracking
- `format_prompt(system_prompt, user_prompt, variables, examples)`: Formats prompts with variable substitution and examples
- `send_prompt(system_prompt, user_prompt, variables, examples, model, temperature, max_tokens)`: High-level method combining format and chat completion with retry logic

#### Token Handling
- Uses `tiktoken` for accurate token counting
- Implements methods for estimating token usage before API calls
- Properly manages token allocation with the token counter service
- Reports actual token usage after API calls

#### Usage
```python
from common.azure_openai_service import AzureOpenAIService

# Initialize service
ai_service = AzureOpenAIService(app_id="my_app")

# Send a prompt
response = await ai_service.send_prompt(
    system_prompt="You are a helpful assistant.",
    user_prompt="Tell me about {topic}.",
    variables={"topic": "AI"}
)
```

### Service Bus Handler
An asynchronous handler for Azure Service Bus operations.

#### Technical Details
- **Class**: `AsyncServiceBusHandler`
- **File**: `service_bus.py`
- **Design**: Fully asynchronous implementation using `asyncio`
- **Connection Management**: Creates fresh connections for each cycle to improve reliability
- **Error Handling**: Comprehensive error handling with retry logic

#### Methods
- `__init__(processor_function, in_queue_name, out_queue_name, fully_qualified_namespace, max_retries, retry_delay, max_wait_time, message_batch_size)`: Initializes the handler with configurable parameters
- `process_message(message)`: Processes a single message with robust error handling
- `send_message(message_body)`: Sends a message to the output queue using a fresh connection
- `listen()`: Starts listening for messages with adaptive sleep timing based on queue activity
- `stop()`: Stops listening and cleans up resources

#### Features
- **Async Processing**: Non-blocking message processing using asyncio
- **Connection Management**: Handles connection initialization, health checks, and cleanup
- **Message Handling**: Processes messages from input queues and sends to output queues
- **Error Resilience**: Implements retries, backoff, and error handling
- **Adaptive Sleep**: Dynamically adjusts sleep time based on queue activity
- **Clean Resource Management**: Proper cleanup of connections and resources

#### Usage
```python
from common.service_bus import AsyncServiceBusHandler

# Initialize handler
handler = AsyncServiceBusHandler(
    processor_function=process_data,
    in_queue_name="input-queue",
    out_queue_name="output-queue",
    fully_qualified_namespace="namespace.servicebus.windows.net"
)

# Start listening for messages
await handler.listen()
```

### Retry Helpers
Smart retry utilities for handling rate limits and transient errors.

#### Technical Details
- **File**: `retry_helpers.py`
- **Functions**:
  - `with_token_limit_retry(func, token_client, max_retries, *args, **kwargs)`: Wrapper function for handling token rate limits
  - `with_token_limit_retry_decorator(token_client, max_retries)`: Decorator version for use with async functions

#### Features
- **Token Limit Retries**: Specialized retries for OpenAI token rate limits
- **Intelligent Waiting**: Waits for the rate limit window based on token counter status
- **Decorator Support**: Can be used as a decorator for clean code
- **Error Propagation**: Proper error propagation for non-retryable errors

#### Usage
```python
from common.retry_helpers import with_token_limit_retry

# Use as a wrapper
result = await with_token_limit_retry(my_async_function, token_client, *args, **kwargs)

# Or as a decorator
@with_token_limit_retry_decorator(token_client)
async def my_function():
    # Function that might hit rate limits
```

### Token Client
Client for interacting with the token counter service.

#### Technical Details
- **Class**: `TokenClient`
- **File**: `token_client.py`
- **Authentication**: Optional Azure AD authentication for secure token service communication
- **API**: Methods for locking, reporting, and releasing tokens

#### Methods
- `__init__(app_id, base_url, resource_uri, use_auth)`: Initializes the client with options for authentication
- `lock_tokens(token_count)`: Requests token allocation from the token service
- `report_usage(request_id, prompt_tokens, completion_tokens)`: Reports actual token usage after completion
- `release_tokens(request_id)`: Releases locked tokens if not used
- `get_status()`: Retrieves current token counter status with reset timing information

#### Features
- Support for both token and rate limit tracking
- Handles compound request IDs (token_id:rate_id format)
- Detailed logging for debugging token issues
- Proper error handling for service communication failures

#### Usage
```python
from common.token_client import TokenClient

# Initialize client
client = TokenClient(app_id="my_app", base_url="http://token-counter:8000")

# Lock tokens for usage
allowed, request_id, error = await client.lock_tokens(1000)

# Report actual usage
await client.report_usage(request_id, prompt_tokens=500, completion_tokens=200)
```

### Logger
A standardized logging utility for consistent log formatting across services.

#### Technical Details
- **File**: `logger.py`
- **Functions**:
  - `get_app_name()`: Retrieves the application name from environment
  - `get_logger(name, log_level)`: Configures and returns a logger instance

#### Features
- **Standardized Format**: Consistent log format with contextual information
- **Color Coding**: Makes logs easy to read in console output
- **Multiple Sources**: Handles logging from different components
- **Environment Awareness**: Adapts based on environment (dev/production)
- **Log Rotation**: Automatic log file rotation with daily rotations
- **Custom Naming**: Custom naming for rotated logs

#### Usage
```python
from common.logger import get_logger

logger = get_logger("my_component")
logger.info("Operation successful")
logger.error("Error occurred: %s", error_message)
```

### Blob Storage Uploader
Asynchronous client for uploading files to Azure Blob Storage.

#### Technical Details
- **Class**: `AsyncBlobStorageUploader`
- **File**: `blob_storage.py`
- **Design**: Background upload worker with queue for non-blocking operation
- **Authentication**: Uses Azure Identity with `DefaultAzureCredential`

#### Methods
- `__init__(account_url, container_name, max_retries, retry_delay)`: Initializes the uploader
- `initialize()`: Sets up connections and starts background worker
- `upload_file(file_path, blob_name, app_name)`: Queues a file for background upload
- `shutdown()`: Gracefully shuts down the uploader waiting for pending uploads

#### Features
- Background processing of uploads to avoid blocking
- Automatic container creation if needed
- Proper resource management with async context managers
- **Retry Logic**: Implements configurable exponential backoff for failed uploads (default: 16 retries)
- **Two-stage Delay**: Uses a fixed 1-second initial delay followed by increasing exponential backoff
- **Resource Management**: Creates fresh connections for each upload attempt and properly closes them
- **Worker Recovery**: Upload worker continues processing queue even if individual uploads fail

#### Usage
```python
from common.blob_storage import AsyncBlobStorageUploader

# Initialize uploader
uploader = AsyncBlobStorageUploader(
    account_url="https://myaccount.blob.core.windows.net",
    container_name="my-container",
    max_retries=16,
    retry_delay=2.0
)
await uploader.initialize()

# Upload a file
await uploader.upload_file("/path/to/file.txt", blob_name="uploaded-file.txt")
```

### Log Monitor Service
Service for monitoring and uploading rotated log files to blob storage.

#### Technical Details
- **Class**: `LogMonitorService`
- **File**: `log_monitor.py`
- **Design**: Periodic scanning for rotated log files with asynchronous upload

#### Methods
- `__init__(logs_dir, account_name, account_url, container_name, app_name, retention_days, scan_interval)`: Initializes the monitor with configurable parameters
- `initialize()`: Sets up the blob storage uploader and starts monitoring
- `shutdown()`: Gracefully shuts down the monitor with final scan

#### Features
- Periodic scanning for new rotated log files
- Skips files still being written to
- Tracks already processed files to avoid duplicates
- Sorts files by modification time for ordered processing
- Works with TimedRotatingFileHandler from Python logging
- **Resilient Operation**: Continues operating even if individual file uploads fail
- **Failed Upload Tracking**: Maintains a set of failed uploads to retry in subsequent scan cycles
- **Final Scan**: Performs one last scan for new log files during shutdown process
- **Error Isolation**: Errors in one file upload don't affect processing of other files

#### Usage
```python
from common.log_monitor import LogMonitorService

# Initialize monitor
monitor = LogMonitorService(
    logs_dir="/app/logs",
    account_name="mystorageaccount",
    container_name="logs",
    app_name="my-application"
)

# Start monitoring
await monitor.initialize()
```

## Design Principles

### Asynchronous by Default
All services and utilities are designed to work with asyncio for efficient resource utilization and scalability.

### Defensive Programming
- Comprehensive error handling at all levels with meaningful error messages
- Proper resource cleanup in finally blocks
- Graceful degradation when services are unavailable

### Retry and Backoff Strategies
- Smart retry logic for rate-limited operations
- Exponential backoff for transient errors
- Status-aware waiting for rate limits

### Resource Management
- Proper cleanup of connections and clients
- Reuse of connections where appropriate
- Fresh connections for critical operations

### Logging and Monitoring
- Consistent logging format across components
- File rotation with upload to blob storage
- Detailed context information in logs

## Integration with Apps

The common library is the foundation for the following applications:
- **app_counter**: Uses common logger and provides token management services
- **app_feedbackform**: Uses Azure OpenAI Service, Service Bus Handler, and retry logic
- **app_reasoner**: Uses Azure OpenAI Service, Service Bus Handler, and retry logic