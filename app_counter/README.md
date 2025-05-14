# OpenAI Token Counter Service

## Overview
The Token Counter Service is a specialized microservice that provides token usage tracking and rate limiting for Azure OpenAI API calls. It manages a global token budget across multiple applications to prevent Azure OpenAI API rate limits from being exceeded, ensuring smooth operation of AI-powered applications.

## Key Features
- **Token Usage Tracking**: Maintains real-time count of tokens used by all applications
- **Token Reservation System**: Allows applications to "lock" tokens before making API calls
- **Rate Limit Enforcement**: Prevents applications from exceeding the configured token rate limit
- **Reporting Mechanism**: Records actual token usage after API calls are completed
- **Token Release**: Allows releasing unused tokens back to the pool
- **Status Monitoring**: Provides real-time status of token availability

## Architecture

### Core Components
1. **TokenCounter**: The main in-memory service that tracks token usage
   - Manages a minute-based token budget with automatic resets
   - Implements a locking mechanism to prevent race conditions
   - Tracks token usage per request using unique request IDs

2. **TokenClient**: A client library for applications to interact with the token counter
   - Provides methods to lock, report, and release tokens
   - Handles communication with the counter service via HTTP
   - Manages error handling for failed requests

3. **FastAPI Endpoints**: 
   - `/lock`: Reserves tokens before making API calls
   - `/report`: Reports actual token usage after calls complete
   - `/release`: Releases tokens that won't be used
   - `/status`: Gets current token availability and reset time

## Technical Details

### Token Locking Process
1. Applications estimate token usage for their OpenAI API calls
2. They request to lock that number of tokens via the `/lock` endpoint
3. If tokens are available, the counter issues a unique request ID
4. Applications use this ID to track and report actual usage

### Token Window Reset
- The service has a configurable token limit per minute (default: 100,000)
- Token counts automatically reset every 60 seconds
- The status endpoint shows time remaining until the next reset

### Concurrency Management
- Uses `asyncio.Lock()` to prevent race conditions in token accounting
- All operations on token counts are thread-safe
- Supports concurrent requests from multiple applications

### Request Tracking
- Each token reservation is tracked with a unique UUID
- Request data stored includes:
  - App ID requesting the tokens
  - Number of tokens locked
  - Timestamp of the request

## Usage in Applications

### Integration with Azure OpenAI Service
The token counter is designed to work with the `AzureOpenAIService` in the common library:

1. The OpenAI service initializes a `TokenClient`
2. Before making API calls, it estimates token usage and locks tokens
3. After getting responses, it reports actual usage
4. In case of errors, it releases any locked tokens

### Token Estimation
- Uses `tiktoken` library to accurately estimate token counts
- Accounts for both prompt and estimated completion tokens
- Provides model-specific token counting

## Configuration
- `OPENAI_TOKEN_LIMIT_PER_MINUTE`: Environment variable to set the token rate limit (default: 100,000)

## API Endpoints

### GET /
Returns basic information about the app.

### GET /health
Health check endpoint.

### POST /lock
Locks tokens for usage.
- Request body: `{"app_id": "app_name", "token_count": 1000}`
- Response: `{"allowed": true, "request_id": "uuid"}`

### POST /report
Reports actual token usage after an API call.
- Request body: `{"app_id": "app_name", "request_id": "uuid", "prompt_tokens": 150, "completion_tokens": 50}`
- Response: `{"success": true}`

### POST /release
Releases locked tokens that won't be used.
- Request body: `{"app_id": "app_name", "request_id": "uuid"}`
- Response: `{"success": true}`

### GET /status
Gets the current status of the token counter.
- Response: `{"available_tokens": 95000, "used_tokens": 5000, "locked_tokens": 0, "reset_time_seconds": 45}`

## Retry Logic
The system includes advanced retry logic for handling rate limit errors:
- If a request is denied due to rate limits, applications can retry after the reset window
- The `with_token_limit_retry` utility provides automatic waiting based on the reset time
- This ensures applications can continue functioning during high-demand periods

## Running the Service
```bash
uvicorn apps.app_counter.main:app --host 0.0.0.0 --port 8001 --workers 4
```

The default port is 8001, which other applications expect when connecting to the token counter service. 