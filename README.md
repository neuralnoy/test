# Async Service Bus Handler for AI-powered Microservices

A robust, asynchronous framework for building AI-powered microservices that process data from dedicated input queues and send processed results to output queues. This framework includes comprehensive token rate limit management for Azure OpenAI integrations.

## System Architecture

The system consists of the following main components:

1. **Feedback Form Processing Service** - Processes customer feedback using AI
2. **Token Counter Service** - Manages token rate limits for Azure OpenAI API calls
3. **Common Library** - Shared components used across all services

### High-Level Flow

```
Data (Feedback, Call, etc.) -> Service Bus Queue -> Feedback Processor -> AI Analysis -> Processed Results
                                                       ↑                       ↑
                                                       |                       |
                                                       └─── Token Counter Service ───┘
```

## Features

- **Asynchronous Processing**: Non-blocking message handling with asyncio
- **Intelligent OpenAI Rate Limiting**: Prevents exceeding API rate limits with a dedicated Token Counter service
- **Robust Error Handling**: Comprehensive error handling with retries and exponential backoff
- **Message Queue Integration**: Seamless integration with Azure Service Bus
- **AI-Powered Processing**: Leverages Azure OpenAI for intelligent data processing
- **Horizontal Scaling**: Supports multiple worker processes for high throughput
- **Health Monitoring**: Endpoints for health checks and status reporting
- **Secure Authentication**: Azure Identity integration for secure access to Azure services
- **Blob Storage Integration**: Support for Azure Blob Storage operations

## Project Structure

```
├── app_counter/                 # Token counter service
│   ├── models/                  # Data models
│   │   ├── __init__.py
│   │   └── schemas.py           # Pydantic schemas for token counter
│   ├── services/                # Service implementations
│   │   ├── __init__.py
│   │   ├── rate_counter.py      # Rate limit tracking implementation
│   │   └── token_counter.py     # Token counting implementation
│   ├── __init__.py
│   ├── main.py                  # FastAPI application
│   └── README.md                # Service documentation
├── app_feedbackform/            # Feedback processing service
│   ├── models/                  # Data models
│   │   ├── __init__.py
│   │   └── schemas.py           # Pydantic schemas for feedback data
│   ├── services/                # Service implementations
│   │   ├── prompts/             # OpenAI prompts and processors
│   │   │   ├── __init__.py
│   │   │   ├── feedback_processor.py  # Processes feedback with AI
│   │   │   ├── hashtag_mapping.py     # Maps feedback to hashtags 
│   │   │   └── prompts.py             # Prompt templates
│   │   ├── __init__.py
│   │   └── data_processor.py    # Main data processing logic
│   ├── __init__.py
│   ├── main.py                  # FastAPI application
│   └── README.md                # Service documentation
├── common_new/                  # Updated shared utilities and services
│   ├── __init__.py
│   ├── azure_openai_service.py  # Azure OpenAI client
│   ├── blob_storage.py          # Azure Blob Storage client
│   ├── log_monitor.py           # Monitoring service for logs
│   ├── logger.py                # Logging utilities
│   ├── retry_helpers.py         # Retry logic for rate limits
│   ├── service_bus.py           # Service Bus handler
│   ├── token_client.py          # Client for token counter service
│   └── README.md                # Common library documentation
├── tests_new/                   # Comprehensive test suite
│   ├── integrationtests/        # Integration tests
│   ├── unittests/               # Unit tests
│   │   ├── __init__.py
│   │   ├── test_azure_openai_service.py    # Azure OpenAI service tests
│   │   ├── test_blob_storage.py            # Blob storage tests
│   │   ├── test_log_monitor.py             # Log monitor tests
│   │   ├── test_logger.py                  # Logger tests
│   │   ├── test_retry_helpers.py           # Retry helpers tests
│   │   ├── test_service_bus.py             # Service bus tests
│   │   └── test_token_client.py            # Token client tests
│   └── README.md                # Testing documentation
├── tests/                       # Legacy test suite
│   ├── integrationtests/        # Integration tests
│   ├── unittests/               # Unit tests
│   └── README.md                # Testing documentation
├── .gitignore                   # Git ignore file
├── deployment_guide.md          # Azure deployment guide
├── manage.py                    # Management script
├── pytest.ini                   # PyTest configuration
├── requirements.txt             # Main Python dependencies
├── test_logger.py               # Logger testing script
└── test_requirements.txt        # Test dependencies
```

## Getting Started

### Prerequisites

- Python 3.8+
- Azure Service Bus namespace
- Azure OpenAI endpoint
- Azure Blob Storage account (optional)

### System Dependencies

The audio processing pipeline (`app_whisper`) relies on **FFmpeg**. You must install it on your system for the service to function correctly.

- **On macOS (using Homebrew):**
  ```bash
  brew install ffmpeg
  ```

- **On Debian/Ubuntu:**
  ```bash
  sudo apt-get update && sudo apt-get install ffmpeg
  ```

- **On Windows:**
  1. Download the latest build from the [official FFmpeg website](https://ffmpeg.org/download.html).
  2. Unzip the file to a location on your computer (e.g., `C:\ffmpeg`).
  3. Add the `bin` directory from the unzipped folder (e.g., `C:\ffmpeg\bin`) to your system's `PATH` environment variable.

> **Note:** If you cannot add FFmpeg to your system's PATH, you can set the `FFMPEG_PATH` environment variable to the full path of the `ffmpeg` executable (e.g., `C:\ffmpeg\bin\ffmpeg.exe`).

### Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set up environment variables:

```bash
# Service Bus Namespace
export SERVICE_BUS_NAMESPACE="your-servicebus-namespace.servicebus.windows.net"

# Queue names for the feedback form app
export FEEDBACK_FORM_IN_QUEUE="feedback-form-in"
export FEEDBACK_FORM_OUT_QUEUE="feedback-form-out"

# Azure OpenAI configuration
export AZURE_OPENAI_API_VERSION="2023-05-15"
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4"

# FFmpeg Path (if not in system PATH)
export FFMPEG_PATH="/path/to/your/ffmpeg"

# Token limit (optional, default is 100,000)
export OPENAI_TOKEN_LIMIT_PER_MINUTE="100000"

# Azure Blob Storage (optional)
export AZURE_STORAGE_ACCOUNT="your-storage-account"
export AZURE_STORAGE_CONTAINER="your-container"
```

## Running the Services

### Token Counter Service

```bash
uvicorn app_counter.main:app --host 0.0.0.0 --port 8001 --workers 4
```

### Feedback Form Service

```bash
uvicorn app_feedbackform.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Testing

This project includes both unit tests and integration tests:

```bash
# Install test dependencies
pip install -r test_requirements.txt

# Run all tests
pytest

# Run tests with coverage
pytest --cov=.

# Run only unit tests
pytest tests/unittests/

# Run only integration tests
pytest tests/integrationtests/
```

## Authentication

The services use Azure Identity's DefaultAzureCredential for authentication, which supports:
- Environment variables
- Managed Identity
- Azure CLI credentials
- Visual Studio Code credentials
- Interactive browser authentication

For detailed deployment and authentication setup, see the [Deployment Guide](./deployment_guide.md).

## Detailed Documentation

Each component has its own detailed README file:

- [Feedback Form Processing Service](./app_feedbackform/README.md)
- [Token Counter Service](./app_counter/README.md)
- [Common Library](./common_new/README.md)
- [Tests](./tests_new/README.md)

## Key Technical Implementation Details

### Token Rate Limiting

The system implements a sophisticated token rate limiting system to prevent exceeding Azure OpenAI API limits:

1. Applications estimate token usage before making API calls
2. The Token Counter service keeps track of global token usage
3. If a rate limit would be exceeded, the request is denied
4. The calling application intelligently waits until the rate limit window resets
5. This enables high concurrency without exceeding API limits

### Asynchronous Service Bus Processing

Messages are processed asynchronously with robust error handling:

1. The Service Bus handler listens to an input queue
2. Messages are processed concurrently with asyncio
3. Results are sent to an output queue
4. Comprehensive error handling ensures no messages are lost

### Blob Storage Integration

The system supports Azure Blob Storage for:

1. Storing large inputs and outputs
2. Backing up processed data
3. Sharing data between services
4. Long-term archiving of results

### Retry Logic with Intelligent Backoff

The system includes smart retry logic:

1. Transient errors are retried with exponential backoff
2. Rate limit errors are retried after the rate limit window resets
3. Permanent errors are reported with detailed error messages

## Performance and Scaling

For optimal performance and throughput:

- Run with multiple worker processes (4 workers recommended for most deployments)
- Scale horizontally by adding more instances for higher throughput
- Token Counter service should be scaled to handle the combined load of all services 