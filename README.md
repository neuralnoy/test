# Async Service Bus Handler for AI-powered Microservices

A robust, asynchronous framework for building AI-powered microservices that process data from dedicated input queues and send processed results to output queues. This framework includes comprehensive token rate limit management for Azure OpenAI integrations.

## System Architecture

The system consists of the following main components:

1. **Feedback Form Processing Service** - Processes customer feedback using AI
2. **Token Counter Service** - Manages token rate limits for Azure OpenAI API calls
3. **Common Library** - Shared components used across all services

### High-Level Flow

```
Customer Feedback -> Service Bus Queue -> Feedback Processor -> AI Analysis -> Processed Results
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

## Project Structure

```
├── apps/
│   ├── app_feedbackform/        # Feedback processing service
│   │   ├── models/              # Data models
│   │   ├── services/            # Service implementations
│   │   │   └── prompts/         # OpenAI prompts and processors
│   │   ├── main.py              # FastAPI application
│   │   └── README.md            # Service documentation
│   └── app_counter/             # Token counter service
│       ├── models/              # Data models
│       ├── services/            # Service implementations
│       ├── main.py              # FastAPI application
│       └── README.md            # Service documentation
├── common/                      # Shared utilities and services
│   ├── azure_openai_service.py  # Azure OpenAI client
│   ├── service_bus.py           # Service Bus handler
│   ├── logger.py                # Logging utilities
│   ├── retry_helpers.py         # Retry logic for rate limits
│   └── README.md                # Common library documentation
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

## Getting Started

### Prerequisites

- Python 3.8+
- Azure Service Bus namespace
- Azure OpenAI endpoint

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

# Token limit (optional, default is 100,000)
export OPENAI_TOKEN_LIMIT_PER_MINUTE="100000"
```

## Running the Services

### Token Counter Service

```bash
uvicorn apps.app_counter.main:app --host 0.0.0.0 --port 8001 --workers 4
```

### Feedback Form Service

```bash
uvicorn apps.app_feedbackform.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Authentication

The services use Azure Identity's DefaultAzureCredential for authentication, which supports:
- Environment variables
- Managed Identity
- Azure CLI credentials
- Visual Studio Code credentials
- Interactive browser authentication

## Detailed Documentation

Each component has its own detailed README file:

- [Feedback Form Processing Service](./apps/app_feedbackform/README.md)
- [Token Counter Service](./apps/app_counter/README.md)
- [Common Library](./common/README.md)

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