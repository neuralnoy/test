# OpenAI Token Counter Service

## Overview
The Token Counter Service is a comprehensive microservice that provides token usage tracking and rate limiting for Azure OpenAI API calls across both completion and embedding services. It manages global token and request budgets across multiple applications to prevent Azure OpenAI API rate limits from being exceeded, ensuring smooth operation of AI-powered applications.

## Key Features
- **Dual Service Support**: Separate tracking for completion and embedding services
- **Token Usage Tracking**: Maintains real-time count of tokens used by all applications
- **Request Rate Limiting**: Tracks and limits API requests per minute across services
- **Token Reservation System**: Allows applications to "lock" tokens before making API calls
- **Rate Limit Enforcement**: Prevents applications from exceeding configured token and request rate limits
- **Reporting Mechanism**: Records actual token usage after API calls are completed
- **Token Release**: Allows releasing unused tokens back to the pool
- **Status Monitoring**: Provides real-time status of token availability and request limits

## Architecture

### Core Components

#### Completion Services
1. **TokenCounter**: Tracks completion token usage (prompt + completion tokens)
   - Manages minute-based token budget with automatic resets
   - Implements locking mechanism to prevent race conditions
   - Default: 128,000 tokens per minute

2. **RateCounter**: Tracks completion request rate limiting
   - Manages API request quotas per minute
   - Prevents request rate limit violations
   - Default: 250 requests per minute

#### Embedding Services
3. **EmbeddingTokenCounter**: Tracks embedding token usage (prompt tokens only)
   - Optimized for high-volume embedding operations
   - Typically has higher token limits than completion services
   - Default: 1,000,000 tokens per minute

4. **EmbeddingRateCounter**: Tracks embedding request rate limiting
   - Manages embedding API request quotas
   - Independent rate limiting from completion services
   - Default: 6000 requests per minute

#### Client Integration
5. **TokenClient**: A client library for applications to interact with the token counter
   - Provides methods for both completion and embedding services
   - Handles communication with the counter service via HTTP
   - Manages error handling and combined request ID parsing

6. **FastAPI Endpoints**: 
   - **Completion**: `/lock`, `/report`, `/release`, `/status`
   - **Embedding**: `/embedding/lock`, `/embedding/report`, `/embedding/release`, `/embedding/status`

## Technical Details

### Token and Rate Locking Process
1. Applications estimate token usage and request both token and rate locks
2. The service checks both token availability and request rate limits
3. If both limits allow, it issues a combined request ID (`token_id:rate_id`)
4. Applications use this ID to track and report actual usage to both counters

### Reset Windows
- All services have configurable limits per minute
- Token and request counts automatically reset every 60 seconds
- Status endpoints show time remaining until the next reset
- Effective reset time is the minimum of token and rate reset times

### Concurrency Management
- Uses `asyncio.Lock()` for each counter to prevent race conditions
- All operations on token and request counts are thread-safe
- Supports concurrent requests from multiple applications across all services

### Request Tracking
- Each reservation is tracked with unique UUIDs
- Combined request IDs allow tracking both token and rate usage
- Request data includes app ID, resource counts, and timestamps

## Configuration

### Environment Variables
```bash
# Service Limits
APP_TPM_QUOTA=128000        # Completion tokens per minute
APP_RPM_QUOTA=250           # Completion requests per minute
APP_EMBEDDING_TPM_QUOTA=1000000  # Embedding tokens per minute
APP_EMBEDDING_RPM_QUOTA=6000      # Embedding requests per minute
APP_WHISPER_RPM_QUOTA=15    # Whisper requests per minute

# Authentication Configuration
AZURE_TENANT_ID=your-tenant-id                    # Azure AD tenant ID
APP_COUNTER_API_CLIENT_ID=your-api-client-id      # Counter API's client ID
APP_COUNTER_API_SCOPE=api://your-api-client-id/.default  # Scope for accessing the counter API

# UAMI Authentication (recommended)
APP_AUDIENCES=uami-1-client-id,uami-2-client-id   # Comma-separated UAMI client IDs allowed to access the API

# Legacy Service Principal (deprecated - remove after UAMI migration)
# APP_COUNTER_API_CLIENT_SECRET=your-client-secret   # Service principal secret (remove after UAMI migration)
```

### Default Values
- **Completion Tokens**: 128,000 per minute
- **Completion Requests**: 250 per minute
- **Embedding Tokens**: 1,000,000 per minute (higher for bulk operations)
- **Embedding Requests**: 6000 per minute
- **Whisper Requests**: 15 per minute

## Authentication

### User-Assigned Managed Identity (UAMI) Authentication

The service now uses **ManagedIdentityCredential** for authentication, providing deterministic, fast, and secure authentication for Azure-hosted applications:

#### Benefits of ManagedIdentityCredential + UAMI
- ✅ No client secret management required
- ✅ Automatic credential rotation
- ✅ Enhanced security posture
- ✅ Simplified deployment and operations
- ✅ **Deterministic authentication**: Direct path to Managed Identity (no credential chain)
- ✅ **Faster performance**: ~50% faster than DefaultAzureCredential
- ✅ **Production-optimized**: Cannot fall back to development credentials

#### Configuration
1. **Deploy applications with UAMI**: Assign User-Assigned Managed Identity to your Azure resources (App Service, Container Instances, AKS, etc.)
2. **Configure UAMI client ID**: Set `APP_COUNTER_API_CLIENT_ID` to your UAMI's client ID
3. **Update audiences**: Add all UAMI client IDs to `APP_AUDIENCES` environment variable
4. **Grant permissions**: Ensure UAMI has access to the counter service scope

#### Migration from Service Principal
- **Remove**: `APP_COUNTER_API_CLIENT_SECRET` environment variable
- **Keep**: `APP_COUNTER_API_CLIENT_ID` (now used for UAMI specification)
- **Update**: `APP_AUDIENCES` to include UAMI client IDs
- **Deploy**: Applications with UAMI assigned to Azure resources

### Authentication Flow
1. **Client**: Uses ManagedIdentityCredential to obtain token for `APP_COUNTER_API_SCOPE`
2. **Token**: Contains audience claim matching UAMI client ID  
3. **Server**: Validates token against configured `effective_audiences` list
4. **Success**: Request is authenticated and processed

### Development vs Production
- **Production**: Uses ManagedIdentityCredential with UAMI (fast, secure, deterministic)
- **Development**: For local development, consider using Azure CLI authentication or Service Principal
  - Alternative: Use DefaultAzureCredential in development environments only
  - Recommendation: Test with actual UAMI in staging environments

## API Endpoints

### General Endpoints

#### GET /
Returns basic information about the app and all configured limits.

#### GET /health
Health check endpoint.

### Completion Service Endpoints

#### POST /lock
Locks tokens and request slots for completion usage.
- Request body: `{"app_id": "app_name", "token_count": 1000}`
- Response: `{"allowed": true, "request_id": "token_uuid:rate_uuid", "rate_request_id": "rate_uuid"}`

#### POST /report
Reports actual completion token usage after an API call.
- Request body: `{"app_id": "app_name", "request_id": "combined_id", "prompt_tokens": 150, "completion_tokens": 50, "rate_request_id": "rate_uuid"}`
- Response: `{"success": true}`

#### POST /release
Releases locked completion tokens and request slots.
- Request body: `{"app_id": "app_name", "request_id": "combined_id", "rate_request_id": "rate_uuid"}`
- Response: `{"success": true}`

#### GET /status
Gets current status of completion token and request counters.
- Response: `{"available_tokens": 95000, "used_tokens": 5000, "locked_tokens": 0, "available_requests": 200, "used_requests": 50, "locked_requests": 0, "reset_time_seconds": 45}`

### Embedding Service Endpoints

#### POST /embedding/lock
Locks tokens and request slots for embedding usage.
- Request body: `{"app_id": "app_name", "token_count": 5000}`
- Response: `{"allowed": true, "request_id": "token_uuid:rate_uuid", "rate_request_id": "rate_uuid"}`

#### POST /embedding/report
Reports actual embedding token usage after an API call.
- Request body: `{"app_id": "app_name", "request_id": "combined_id", "prompt_tokens": 5000}`
- Response: `{"success": true}`

#### POST /embedding/release
Releases locked embedding tokens and request slots.
- Request body: `{"app_id": "app_name", "request_id": "combined_id"}`
- Response: `{"success": true}`

#### GET /embedding/status
Gets current status of embedding token and request counters.
- Response: `{"available_tokens": 950000, "used_tokens": 50000, "locked_tokens": 0, "available_requests": 450, "used_requests": 50, "locked_requests": 0, "reset_time_seconds": 30}`

## Usage in Applications

### Integration with Azure OpenAI Services

#### Completion Service Integration
The token counter works with the `AzureOpenAIService`:
1. Initializes a `TokenClient` 
2. Estimates token usage and locks both tokens and request slots
3. Reports actual usage to both token and rate counters
4. Releases locks in case of errors

#### Embedding Service Integration
The token counter works with the `AzureEmbeddingService`:
1. Uses the same `TokenClient` with embedding-specific methods
2. Calls `lock_embedding_tokens()`, `report_embedding_usage()`, `release_embedding_tokens()`
3. Handles combined request IDs automatically
4. Provides separate token tracking for embedding operations

### Token Estimation
- Uses `tiktoken` library for accurate token counting
- **Completion**: Accounts for prompt + estimated completion tokens
- **Embedding**: Only counts prompt tokens (no completion tokens)
- Provides model-specific encoding (including text-embedding-3-large)

## Service Separation Benefits

### Independent Scaling
- **Different Usage Patterns**: Embeddings often involve bulk operations with high token counts
- **Different Pricing**: Embedding tokens are typically much cheaper than completion tokens
- **Independent Limits**: Can tune each service based on actual usage patterns
- **Clear Cost Tracking**: Separate accounting for different service types

### Rate Limit Management
- **Completion Services**: Balanced token and request limits for interactive use
- **Embedding Services**: Higher token limits with moderate request limits for batch operations
- **Independent Resets**: Each service resets independently based on usage patterns

## Retry Logic
The system includes retry logic for handling rate limit errors:
- Applications can retry after rate limit denials
- The `with_token_limit_retry` utility provides automatic waiting
- Works with both completion and embedding services
- Handles combined request ID parsing automatically

## Running the Service
```bash
uvicorn app_counter.main:app --host 0.0.0.0 --port 8000 --workers 1
```

The service runs on port 8000 by default and manages all four counter types simultaneously, providing comprehensive rate limiting for both completion and embedding Azure OpenAI services. 