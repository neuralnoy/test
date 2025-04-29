# Common Library for AI Microservices

## Overview
The Common Library provides shared utilities, services, and functionality that are used across multiple microservices in the system. It creates a consistent foundation for interacting with Azure services, handling errors, managing logging, and implementing retry logic.

## Key Components

### Azure OpenAI Service
A comprehensive client for interacting with Azure OpenAI models.

#### Features
- **Authentication**: Uses Azure Identity for secure authentication
- **Token Management**: Integrates with Token Counter service to prevent rate limit issues
- **Prompt Management**: Utilities for formatting and sending prompts
- **Token Estimation**: Accurate token counting using tiktoken
- **Context Management**: Handles conversation context for chat completions
- **Error Handling**: Comprehensive error handling with retry logic

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

#### Features
- **Async Processing**: Non-blocking message processing using asyncio
- **Connection Management**: Handles connection initialization, health checks, and cleanup
- **Message Handling**: Processes messages from input queues and sends to output queues
- **Error Resilience**: Implements retries, backoff, and error handling
- **Authentication**: Uses DefaultAzureCredential for secure service bus access

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

### Logger
A standardized logging utility for consistent log formatting across services.

#### Features
- **Standardized Format**: Consistent log format with contextual information
- **Color Coding**: Makes logs easy to read in console output
- **Multiple Sources**: Handles logging from different components
- **Environment Awareness**: Adapts based on environment (dev/production)

#### Usage
```python
from common.logger import get_logger

logger = get_logger("my_component")
logger.info("Operation successful")
logger.error("Error occurred: %s", error_message)
```

## Design Principles

### Asynchronous by Default
All services and utilities are designed to work with asyncio for efficient resource utilization and scalability.

### Robust Error Handling
Comprehensive error handling at all levels with meaningful error messages and appropriate error propagation.

### Centralized Authentication
Uses Azure Identity with DefaultAzureCredential for consistent authentication across services.

### Reusable Components
Components are designed to be reusable across different microservices.

### Configuration via Environment
Configuration is handled via environment variables for secure and flexible deployment.

## Integration with Apps

The common library is the foundation for the following applications:
- **app_counter**: Uses common logger and provides token management services
- **app_feedbackform**: Uses Azure OpenAI Service, Service Bus Handler, and retry logic

## Configuration
The common library uses the following environment variables:

- `AZURE_OPENAI_API_VERSION`: API version for Azure OpenAI
- `AZURE_OPENAI_ENDPOINT`: Endpoint URL for Azure OpenAI
- `AZURE_OPENAI_DEPLOYMENT_NAME`: Default deployment name for OpenAI models
- `LOG_LEVEL`: Logging level (default: INFO)

## Security
- Uses Azure Identity for secure access to Azure resources
- No hardcoded credentials or secrets
- Supports Managed Identity in production environments
- Falls back to other credential types (environment, CLI) for development 