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

### Azure Embedding Service
A specialized client for generating text embeddings using Azure-hosted OpenAI embedding models.

#### Technical Details
- **Class**: `AzureEmbeddingService`
- **File**: `azure_embedding_service.py`
- **Authentication**: Uses Azure Identity with `DefaultAzureCredential` for secure authentication (identical to main OpenAI service)
- **Token Management**: Integrates with `TokenClient` for embedding-specific token tracking and rate limiting
- **Separate Configuration**: Independent endpoint, API version, and model configuration from completion services
- **Service Separation**: Dedicated service for embedding operations with separate quotas and limits

#### Methods
- `__init__(model, app_id, token_counter_url)`: Initializes the embedding service with specified parameters
- `create_embedding(text, model)`: Creates embeddings for single or multiple texts with token tracking
- `create_embedding_batch(texts, model, batch_size)`: Processes large batches of texts with chunking support
- `_estimate_tokens(texts, model)`: Estimates token usage using tiktoken for accurate pre-allocation
- `_get_encoding_for_model(model)`: Gets appropriate tokenizer for embedding models (cl100k_base)

#### Token Handling
- Uses `tiktoken` with cl100k_base encoding for embedding model token counting
- Implements separate embedding token limits independent of completion tokens
- Reports actual embedding token usage from Azure OpenAI API responses
- Supports batch processing with proper token allocation per batch

#### Environment Variables
```bash
# Required
APP_EMBEDDING_API_BASE=https://your-embedding-endpoint.openai.azure.com/
COUNTER_APP_BASE_URL=http://token-counter:8000

# Optional (with defaults)
APP_EMBEDDING_API_VERSION=2024-02-01
APP_EMBEDDING_ENGINE=text-embedding-3-large
APP_EMBEDDING_TPM_QUOTA=1000000
APP_EMBEDDING_RPM_QUOTA=500
```

#### Usage
```python
from common.azure_embedding_service import AzureEmbeddingService

# Initialize embedding service
embedding_service = AzureEmbeddingService(app_id="my_app")

# Create single embedding
embedding = await embedding_service.create_embedding("Hello world")

# Create multiple embeddings
texts = ["Text 1", "Text 2", "Text 3"]
embeddings = await embedding_service.create_embedding(texts)

# Process large batch with chunking
large_texts = ["Text {}".format(i) for i in range(1000)]
embeddings = await embedding_service.create_embedding_batch(large_texts, batch_size=100)
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
Client for interacting with the token counter service supporting both completion and embedding operations.

#### Technical Details
- **Class**: `TokenClient`
- **File**: `token_client.py`
- **Authentication**: Optional Azure AD authentication for secure token service communication
- **Dual Service Support**: Methods for both completion and embedding token management
- **Combined Request IDs**: Handles compound request IDs (token_id:rate_id format) for rate limiting

#### Completion Service Methods
- `__init__(app_id, base_url, resource_uri, use_auth)`: Initializes the client with options for authentication
- `lock_tokens(token_count)`: Requests token allocation from the completion token service
- `report_usage(request_id, prompt_tokens, completion_tokens)`: Reports actual token usage after completion
- `release_tokens(request_id)`: Releases locked completion tokens if not used
- `get_status()`: Retrieves current completion token counter status with reset timing information

#### Embedding Service Methods
- `lock_embedding_tokens(token_count)`: Requests token allocation from the embedding token service
- `report_embedding_usage(request_id, prompt_tokens)`: Reports actual embedding token usage (prompt tokens only)
- `release_embedding_tokens(request_id)`: Releases locked embedding tokens if not used
- `get_embedding_status()`: Retrieves current embedding token counter status with reset timing information

#### Features
- **Dual Token Tracking**: Separate tracking for completion and embedding tokens with independent quotas
- **Rate Limit Integration**: Support for both token and rate limit tracking with combined request IDs
- **Service Separation**: Independent token pools for completion vs embedding operations
- **Detailed Logging**: Comprehensive logging for debugging token issues across both services
- **Error Handling**: Proper error handling for service communication failures
- **Status Monitoring**: Real-time status information for both completion and embedding counters

#### Usage
```python
from common.token_client import TokenClient

# Initialize client
client = TokenClient(app_id="my_app", base_url="http://token-counter:8000")

# Completion service operations
allowed, request_id, error = await client.lock_tokens(1000)
await client.report_usage(request_id, prompt_tokens=500, completion_tokens=200)
status = await client.get_status()

# Embedding service operations
allowed, request_id, error = await client.lock_embedding_tokens(5000)
await client.report_embedding_usage(request_id, prompt_tokens=5000)
embedding_status = await client.get_embedding_status()
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
- **app_counter**: Uses common logger and provides token management services for both completion and embedding operations
- **app_feedbackform**: Uses Azure OpenAI Service, Azure Embedding Service, Service Bus Handler, and retry logic
- **app_reasoner**: Uses Azure OpenAI Service, Azure Embedding Service, Service Bus Handler, and retry logic

### Service Integration Patterns

#### Completion + Embedding Services
Applications requiring both text generation and embeddings can use both services independently:
```python
# Initialize both services with same app_id for unified tracking
openai_service = AzureOpenAIService(app_id="my_app")
embedding_service = AzureEmbeddingService(app_id="my_app")

# Use appropriate service for each operation
response = await openai_service.structured_prompt(...)
embeddings = await embedding_service.create_embedding([...])
```

#### Token Counter Integration
The token counter service provides separate quotas and tracking for:
- **Completion Operations**: Token and request rate limiting for chat/completion APIs
- **Embedding Operations**: Independent token and request rate limiting for embedding APIs
- **Unified Monitoring**: Single counter app manages all token tracking with separate pools

#### Environment Configuration
Each application can configure completion and embedding services independently:
```bash
# Completion Service
APP_OPENAI_API_BASE=https://completion-endpoint.openai.azure.com/
APP_OPENAI_ENGINE=gpt-4
APP_TPM_QUOTA=128000
APP_RPM_QUOTA=250

# Embedding Service  
APP_EMBEDDING_API_BASE=https://embedding-endpoint.openai.azure.com/
APP_EMBEDDING_ENGINE=text-embedding-3-large
APP_EMBEDDING_TPM_QUOTA=1000000
APP_EMBEDDING_RPM_QUOTA=500

# Shared Counter Service
COUNTER_APP_BASE_URL=http://token-counter:8000
```

### Azure AI Search Service
A comprehensive service for Azure AI Search operations including document indexing and vector search.

#### Technical Details
- **Class**: `AzureSearchService`
- **File**: `azure_search_service.py`
- **Authentication**: Uses Azure Identity with `DefaultAzureCredential` for secure authentication
- **Index Management**: Supports multiple search indexes with configurable index names
- **Search Types**: Supports both traditional text search and vector search capabilities

#### Methods
- `__init__(index_name, app_id)`: Initializes the service with specified index and application ID
- `upload_documents(documents)`: Upload or update documents in the search index
- `search_documents(search_text, top, select, filter_expression, order_by)`: Perform text-based search
- `vector_search(vector, vector_field, top, select, filter_expression)`: Perform vector similarity search
- `get_document(document_key, selected_fields)`: Retrieve a single document by key
- `delete_documents(documents)`: Delete documents from the index
- `get_document_count()`: Get total number of documents in the index
- `close()`: Clean up search client connections

#### Features
- **Multi-Index Support**: Can work with different indexes for different applications
- **Vector Search**: Native support for vector similarity search using embeddings
- **Text Search**: Traditional full-text search with Azure's cognitive search capabilities
- **Document Management**: Complete CRUD operations for search documents
- **Error Handling**: Comprehensive error handling with proper exception propagation
- **Resource Management**: Proper cleanup of search client connections

#### Environment Variables
```bash
# Required
APP_SEARCH_ENDPOINT=https://your-search-service.search.windows.net
```

#### Usage
```python
from common_new.azure_search_service import AzureSearchService

# Initialize search service
search_service = AzureSearchService(
    index_name="my-documents",
    app_id="my_app"
)

# Upload documents
documents = [
    {"id": "1", "title": "AI Overview", "content": "AI is transforming..."},
    {"id": "2", "title": "ML Basics", "content": "Machine learning..."}
]
await search_service.upload_documents(documents)

# Text search
results = await search_service.search_documents("machine learning", top=5)

# Vector search (requires vector field in documents)
vector_results = await search_service.vector_search(
    vector=[0.1, 0.2, 0.3, ...],  # Your query vector
    vector_field="content_vector",
    top=10
)

# Get specific document
document = await search_service.get_document("1")

# Clean up
search_service.close()
```

#### Integration with Embedding Service
The Azure Search Service works seamlessly with the existing `AzureEmbeddingService` for vector search scenarios:

```python
from common_new.azure_search_service import AzureSearchService
from common_new.azure_embedding_service import AzureEmbeddingService

# Initialize both services
search_service = AzureSearchService(index_name="vectors", app_id="my_app")
embedding_service = AzureEmbeddingService(app_id="my_app")

# Generate embedding for query
query_text = "artificial intelligence applications"
query_embedding = await embedding_service.create_embedding(query_text)

# Perform vector search
results = await search_service.vector_search(
    vector=query_embedding[0],
    vector_field="content_vector",
    top=5
)
```

# Async Service Bus Handler for AI-powered Microservices

A robust, asynchronous framework for building AI-powered microservices that process data from dedicated input queues and send processed results to output queues. This framework includes comprehensive token rate limit management for Azure OpenAI integrations and specialized audio processing capabilities.

## System Architecture

The system consists of the following main components:

1. **Feedback Form Processing Service** - Processes customer feedback using AI
2. **Whisper Audio Processing Service** - Transcribes and processes audio files using Azure OpenAI Whisper
3. **Token Counter Service** - Manages token rate limits for Azure OpenAI API calls
4. **Common Library** - Shared components used across all services

### High-Level Flow

```
Data (Feedback, Audio, etc.) -> Service Bus Queue -> Processor -> AI Analysis -> Processed Results
                                                       ↑                ↑
                                                       |                |
                                                       └─── Rate Limiting ───┘
```

## Features

- **Asynchronous Processing**: Non-blocking message handling with asyncio
- **Intelligent Rate Limiting**: 
  - Token-based rate limiting for text models (GPT-4, GPT-3.5)
  - Request-based rate limiting for audio models (Whisper)
- **Robust Error Handling**: Comprehensive error handling with retries and exponential backoff
- **Message Queue Integration**: Seamless integration with Azure Service Bus
- **AI-Powered Processing**: Leverages Azure OpenAI for intelligent data processing
- **Audio Processing**: Complete audio transcription pipeline with Whisper
- **Horizontal Scaling**: Supports multiple worker processes for high throughput
- **Health Monitoring**: Endpoints for health checks and status reporting
- **Secure Authentication**: Azure Identity integration for secure access to Azure services
- **Blob Storage Integration**: Support for Azure Blob Storage operations

## Audio Processing with Whisper

### Whisper Service Features

- **Smart Rate Limiting**: Configurable requests-per-minute limiting
- **Concurrent Processing**: Process multiple audio chunks in parallel
- **File Validation**: Automatic validation of audio format and size
- **Retry Logic**: Built-in retry mechanisms for transient failures
- **Multiple Formats**: Support for JSON, text, SRT, VTT output formats
- **Language Support**: Full language detection and specification

### Environment Variables for Whisper

```bash
# Whisper-specific configuration
WHISPER_REQUESTS_PER_MINUTE=15  # Default: 50 requests per minute
APP_OPENAI_API_VERSION=2024-02-01
APP_OPENAI_API_BASE=https://your-openai-resource.openai.azure.com/
APP_OPENAI_ENGINE=whisper-1  # Your Whisper deployment name
```

### Usage Example

```python
from common_new.azure_openai_service import AzureOpenAIServiceWhisper

# Initialize Whisper service
whisper_service = AzureOpenAIServiceWhisper(app_id="app_whisper")

# Single file transcription
result = await whisper_service.transcribe_audio(
    audio_file_path="/path/to/audio.wav",
    language="en",
    response_format="verbose_json",
    timestamp_granularities=["word", "segment"]
)

# Transcription with retry logic
result = await whisper_service.transcribe_audio_with_retry(
    audio_file_path="/path/to/audio.wav",
    max_retries=3,
    retry_delay=2.0
)

# Concurrent chunk processing
chunk_paths = ["/path/to/chunk1.wav", "/path/to/chunk2.wav"]
results = await whisper_service.transcribe_audio_chunks(chunk_paths)

# Check rate limiting stats
stats = whisper_service.get_rate_limit_stats()
print(f"Current usage: {stats['utilization_percentage']:.1f}%")

# Dynamically adjust rate limit
await whisper_service.set_rate_limit(100)  # Increase to 100 RPM
```

### Rate Limiting Details

The Whisper service uses a smart rate limiter that:

1. **Tracks Requests**: Maintains a sliding window of requests over the last minute
2. **Prevents Overuse**: Automatically waits when rate limit would be exceeded
3. **Provides Statistics**: Real-time usage statistics and utilization percentages
4. **Configurable**: Rate limits can be set via environment variables or dynamically
5. **Thread-Safe**: Safe for concurrent use across multiple async tasks

### Audio File Requirements

- **Supported Formats**: MP3, MP4, MPEG, MPGA, M4A, WAV, WEBM
- **Maximum Size**: 25MB per file
- **Automatic Validation**: Files are validated before processing

## Project Structure

```
├── app_counter/                 # Token counter service
│   ├── models/                  # Data models
│   │   ├── __init__.py
│   │   └── schemas.py          # Pydantic models for requests/responses
│   ├── services/               # Business logic
│   │   ├── __init__.py
│   │   └── counter_service.py  # Token counting logic
│   ├── main.py                 # FastAPI application
│   └── README.md               # Service-specific documentation
├── app_whisper/                # Whisper audio processing service
│   ├── models/                 # Data models
│   ├── services/               # Business logic
│   │   ├── businesslogic/      # Core processing logic
│   │   └── data_processor.py   # Message queue data processing
│   ├── main.py                 # FastAPI application
│   └── README.md               # Service-specific documentation
├── app_feedbackform/           # Feedback processing service
├── common_new/                 # Shared library
│   ├── azure_openai_service.py # Azure OpenAI integration with Whisper support
│   ├── blob_storage.py         # Azure Blob Storage client (upload/download)
│   ├── service_bus.py          # Azure Service Bus handler
│   ├── token_client.py         # Token counter client
│   ├── logger.py               # Centralized logging
│   └── retry_helpers.py        # Retry logic utilities
├── requirements.txt            # Python dependencies (includes audio processing)
└── README.md                   # This file
```

## Rate Limiting Architecture

### Text Models (GPT-4, GPT-3.5)
- **Method**: Token-based rate limiting
- **Tracking**: Input tokens + estimated output tokens
- **Service**: Centralized Token Counter service
- **Benefits**: Prevents costly overuse, accurate cost prediction

### Audio Models (Whisper)
- **Method**: Request-based rate limiting  
- **Tracking**: Requests per minute with sliding window
- **Service**: Local rate limiter per service instance
- **Benefits**: Prevents API rate limit errors, configurable per deployment

## Performance and Scaling

For optimal performance and throughput:

- Run with multiple worker processes (4 workers recommended for most deployments)
- Scale horizontally by adding more instances for higher throughput
- Configure rate limits based on your Azure OpenAI quotas
- Use concurrent processing for audio chunks when possible
- Monitor rate limit utilization to optimize throughput

## Getting Started

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set Environment Variables**:
   ```bash
   # Azure OpenAI Configuration
   export APP_OPENAI_API_VERSION=2024-02-01
   export APP_OPENAI_API_BASE=https://your-resource.openai.azure.com/
   export APP_OPENAI_ENGINE=your-deployment-name
   
   # Whisper Rate Limiting
   export WHISPER_REQUESTS_PER_MINUTE=50
   
   # Service Bus Configuration
   export SERVICE_BUS_NAMESPACE=your-namespace.servicebus.windows.net
   ```

3. **Run a Service**:
   ```bash
   cd app_whisper
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

## Dependencies

The framework includes audio processing capabilities with these key dependencies:

- **Core**: FastAPI, Pydantic, Azure SDK
- **AI**: OpenAI Python client, Instructor
- **Audio**: librosa, soundfile, ffmpeg-python, resemblyzer
- **Infrastructure**: Azure Service Bus, Azure Blob Storage, Azure Identity