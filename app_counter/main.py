import os
import asyncio
from fastapi import FastAPI, HTTPException, Request
from contextlib import asynccontextmanager
from common_new.logger import get_logger
from app_counter.services.token_counter import TokenCounter
from app_counter.services.rate_counter import RateCounter
from app_counter.services.embedding_token_counter import EmbeddingTokenCounter
from app_counter.services.embedding_rate_counter import EmbeddingRateCounter
from app_counter.services.whisper_rate_counter import WhisperRateCounter
from app_counter.models.schemas import (
    TokenRequest,
    TokenReport,
    EmbeddingReport,
    ReleaseRequest,
    TokenResponse,
    StatusResponse,
    EmbeddingStatusResponse,
    WhisperRateRequest,
    WhisperRateReport,
    WhisperRateRelease,
    WhisperRateResponse,
    WhisperRateStatusResponse
)

logger = get_logger("counter")

# Get token limit from environment variables or use default
TOKEN_LIMIT_PER_MINUTE = int(os.getenv("APP_TPM_QUOTA", "128000"))
# Get rate limit from environment variables or use default
RATE_LIMIT_PER_MINUTE = int(os.getenv("APP_RPM_QUOTA", "250"))
# Get embedding token limit from environment variables or use default (typically higher than chat tokens)
EMBEDDING_TOKEN_LIMIT_PER_MINUTE = int(os.getenv("APP_EMBEDDING_TPM_QUOTA", "1000000"))
# Get embedding rate limit from environment variables or use default
EMBEDDING_RATE_LIMIT_PER_MINUTE = int(os.getenv("APP_EMBEDDING_RPM_QUOTA", "6000"))
# Get Whisper rate limit from environment variables or use default
WHISPER_RATE_LIMIT_PER_MINUTE = int(os.getenv("APP_WHISPER_RPM_QUOTA", "15"))

# Initialize the token counter and rate counter services
token_counter = TokenCounter(tokens_per_minute=TOKEN_LIMIT_PER_MINUTE)
rate_counter = RateCounter(requests_per_minute=RATE_LIMIT_PER_MINUTE)
embedding_token_counter = EmbeddingTokenCounter(tokens_per_minute=EMBEDDING_TOKEN_LIMIT_PER_MINUTE)
embedding_rate_counter = EmbeddingRateCounter(requests_per_minute=EMBEDDING_RATE_LIMIT_PER_MINUTE)
whisper_rate_counter = WhisperRateCounter(requests_per_minute=WHISPER_RATE_LIMIT_PER_MINUTE)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for the FastAPI app.
    Handles startup and shutdown events.
    """
    # Startup logic
    logger.info(f"Starting Token Counter app with limit of {TOKEN_LIMIT_PER_MINUTE} tokens per minute, {EMBEDDING_TOKEN_LIMIT_PER_MINUTE} embedding tokens per minute, {RATE_LIMIT_PER_MINUTE} requests per minute, {EMBEDDING_RATE_LIMIT_PER_MINUTE} embedding requests per minute, and {WHISPER_RATE_LIMIT_PER_MINUTE} Whisper requests per minute")
    
    # Initialize log monitoring service if configured
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
    account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
    container_name = os.getenv("AZURE_LOGS_CONTAINER_NAME", "fla-logs")
    retention_days = int(os.getenv("AZURE_LOGS_RETENTION_DAYS", "7"))
    scan_interval = int(os.getenv("LOG_SCAN_INTERVAL", "300"))
    app_name = os.getenv("APP_NAME_FOR_LOGGER")  # Get app name from environment variables
    
    # Only initialize if blob storage is configured (either by URL or account name)
    if account_url or account_name:
        from common_new.log_monitor import LogMonitorService
        
        storage_endpoint = account_url or f"https://{account_name}.blob.core.windows.net"
        logger.info(f"Initializing log monitor service to upload to {storage_endpoint}/{container_name}")
        
        log_monitor = LogMonitorService(
            logs_dir=logs_dir,
            account_name=account_name,
            account_url=account_url,
            container_name=container_name,
            app_name=app_name,  # Pass app_name to the LogMonitorService
            retention_days=retention_days,
            scan_interval=scan_interval
        )
        
        monitor_initialized = await log_monitor.initialize()
        if monitor_initialized:
            logger.info("Log monitor service initialized successfully")
            app.state.log_monitor = log_monitor
        else:
            logger.warning("Failed to initialize log monitor service")
    else:
        logger.info("Azure Blob Storage not configured - log uploads disabled")
    
    # Store counters in app state for access from endpoints
    app.state.token_counter = token_counter
    app.state.rate_counter = rate_counter
    app.state.embedding_token_counter = embedding_token_counter
    app.state.embedding_rate_counter = embedding_rate_counter
    app.state.whisper_rate_counter = whisper_rate_counter
    
    yield  # This is where the app runs
    
    # Shutdown logic
    logger.info("Shutting down Token Counter app")
    
    # Shut down the log monitor if it was initialized
    if hasattr(app.state, "log_monitor"):
        logger.info("Shutting down log monitor service")
        await app.state.log_monitor.shutdown()

app = FastAPI(title="OpenAI Token Counter", lifespan=lifespan)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests"""
    method = request.method
    path = request.url.path
    logger.info(f"API REQUEST: {method} {path}")
    response = await call_next(request)
    logger.info(f"API RESPONSE: {method} {path} - Status: {response.status_code}")
    return response

@app.get("/")
def read_root():
    logger.info(f"CONFIG: token_limit={TOKEN_LIMIT_PER_MINUTE}, embedding_token_limit={EMBEDDING_TOKEN_LIMIT_PER_MINUTE}, rate_limit={RATE_LIMIT_PER_MINUTE}, embedding_rate_limit={EMBEDDING_RATE_LIMIT_PER_MINUTE}, whisper_rate_limit={WHISPER_RATE_LIMIT_PER_MINUTE}")
    return {
        "app": "OpenAI Token Counter",
        "status": "running",
        "token_limit_per_minute": TOKEN_LIMIT_PER_MINUTE,
        "embedding_token_limit_per_minute": EMBEDDING_TOKEN_LIMIT_PER_MINUTE,
        "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE,
        "embedding_rate_limit_per_minute": EMBEDDING_RATE_LIMIT_PER_MINUTE,
        "whisper_rate_limit_per_minute": WHISPER_RATE_LIMIT_PER_MINUTE
    }

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

@app.post("/lock", response_model=TokenResponse)
async def lock_tokens(request: TokenRequest):
    """
    Lock tokens for usage and check rate limits.
    Returns whether the request is allowed and a request ID if allowed.
    """
    logger.info(f"API LOCK: app={request.app_id}, tokens={request.token_count}")
    
    # First check the rate limit
    rate_result = await rate_counter.lock_request(request.app_id)
    
    if not rate_result.get("allowed", False):
        logger.warning(f"API LOCK DENIED (RATE): app={request.app_id}, tokens={request.token_count}, reason={rate_result.get('message')}")
        return TokenResponse(
            allowed=False,
            message=f"API Rate limit would be exceeded: {rate_result.get('message', 'Rate limit exceeded')}"
        )
    
    # Then check the token limit
    token_result = await token_counter.lock_tokens(request.app_id, request.token_count)
    
    if not token_result.get("allowed", False):
        # Release the rate lock since we're not proceeding
        await rate_counter.release_request(request.app_id, rate_result["request_id"])
        logger.warning(f"API LOCK DENIED (TOKEN): app={request.app_id}, tokens={request.token_count}, reason={token_result.get('message')}")
        return TokenResponse(
            allowed=False,
            message=f"Token limit would be exceeded: {token_result.get('message', 'Token limit exceeded')}"
        )
    
    # Combine token and rate request IDs for backward compatibility with existing clients
    # Clients can parse this combined ID if they're updated, or use it as is if they're not
    combined_request_id = f"{token_result['request_id']}:{rate_result['request_id']}"
    
    # Both limits passed, return success with combined info
    logger.info(f"API LOCK APPROVED: app={request.app_id}, tokens={request.token_count}, combined_id={combined_request_id}")
    
    return TokenResponse(
        allowed=True,
        request_id=combined_request_id,
        rate_request_id=rate_result["request_id"]
    )

@app.post("/report", status_code=200)
async def report_usage(report: TokenReport):
    """
    Report actual token usage after an API call.
    """
    logger.info(f"API REPORT: app={report.app_id}, request_id={report.request_id}, prompt={report.prompt_tokens}, completion={report.completion_tokens}, rate_id={report.rate_request_id}")
    
    success = await token_counter.report_usage(
        report.app_id,
        report.request_id,
        report.prompt_tokens,
        report.completion_tokens
    )
    
    if not success:
        error_msg = f"Failed to report token usage. Invalid request ID or app ID."
        logger.error(f"API REPORT ERROR: app={report.app_id}, request_id={report.request_id}, reason={error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    
    # If rate request ID is provided, confirm the request
    rate_success = True
    if report.rate_request_id:
        rate_success = await rate_counter.confirm_request(
            report.app_id,
            report.rate_request_id
        )
        if not rate_success:
            logger.warning(f"API REPORT PARTIAL: app={report.app_id}, token_success=True, rate_success=False, rate_id={report.rate_request_id}")
    
    logger.info(f"API REPORT SUCCESS: app={report.app_id}, token_success={success}, rate_success={rate_success}")
    return {"success": True}

@app.post("/release", status_code=200)
async def release_tokens(request: ReleaseRequest):
    """
    Release locked tokens that won't be used.
    """
    logger.info(f"API RELEASE: app={request.app_id}, request_id={request.request_id}, rate_id={request.rate_request_id}")
    
    success = await token_counter.release_tokens(request.app_id, request.request_id)
    
    if not success:
        error_msg = f"Failed to release tokens. Invalid request ID or app ID."
        logger.error(f"API RELEASE ERROR: app={request.app_id}, request_id={request.request_id}, reason={error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    
    # If rate request ID is provided, release the request slot
    rate_success = True
    if request.rate_request_id:
        rate_success = await rate_counter.release_request(
            request.app_id,
            request.rate_request_id
        )
        if not rate_success:
            logger.warning(f"API RELEASE PARTIAL: app={request.app_id}, token_success=True, rate_success=False, rate_id={request.rate_request_id}")
    
    logger.info(f"API RELEASE SUCCESS: app={request.app_id}, token_success={success}, rate_success={rate_success}")
    return {"success": True}

@app.get("/status", response_model=StatusResponse)
async def get_status():
    """
    Get the current status of the token counter and rate counter.
    """
    logger.info("API STATUS: Fetching current status")
    
    token_status = await token_counter.get_status()
    rate_status = await rate_counter.get_status()
    
    # Calculate which limit will reset first
    token_reset = token_status.get("reset_time_seconds", 0)
    rate_reset = rate_status.get("reset_time_seconds", 0)
    
    # Use the minimum reset time as the effective reset time
    effective_reset = min(token_reset, rate_reset)
    
    token_usage = token_status.get("used_tokens", 0) + token_status.get("locked_tokens", 0)
    rate_usage = rate_status.get("used_requests", 0) + rate_status.get("locked_requests", 0)
    
    token_pct = (token_usage / TOKEN_LIMIT_PER_MINUTE) * 100 if TOKEN_LIMIT_PER_MINUTE > 0 else 0
    rate_pct = (rate_usage / RATE_LIMIT_PER_MINUTE) * 100 if RATE_LIMIT_PER_MINUTE > 0 else 0
    
    logger.info(f"API STATUS RESULT: tokens={token_usage}/{TOKEN_LIMIT_PER_MINUTE} ({token_pct:.1f}%), "
                f"requests={rate_usage}/{RATE_LIMIT_PER_MINUTE} ({rate_pct:.1f}%), "
                f"token_reset={token_reset}s, rate_reset={rate_reset}s, effective_reset={effective_reset}s")
    
    return StatusResponse(
        available_tokens=token_status.get("available_tokens", 0),
        used_tokens=token_status.get("used_tokens", 0),
        locked_tokens=token_status.get("locked_tokens", 0),
        available_requests=rate_status.get("available_requests", 0),
        used_requests=rate_status.get("used_requests", 0),
        locked_requests=rate_status.get("locked_requests", 0),
        reset_time_seconds=effective_reset  # Use the minimum of the two reset times
    )

# Embedding endpoints
@app.post("/embedding/lock", response_model=TokenResponse)
async def lock_embedding_tokens(request: TokenRequest):
    """
    Lock embedding tokens for usage and check embedding rate limits.
    Returns whether the request is allowed and a request ID if allowed.
    """
    logger.info(f"API EMBEDDING LOCK: app={request.app_id}, tokens={request.token_count}")
    
    # First check the embedding rate limit
    rate_result = await embedding_rate_counter.lock_request(request.app_id)
    
    if not rate_result.get("allowed", False):
        logger.warning(f"API EMBEDDING LOCK DENIED (RATE): app={request.app_id}, tokens={request.token_count}, reason={rate_result.get('message')}")
        return TokenResponse(
            allowed=False,
            message=f"Embedding rate limit would be exceeded: {rate_result.get('message', 'Embedding rate limit exceeded')}"
        )
    
    # Then check the embedding token limit
    embedding_result = await embedding_token_counter.lock_tokens(request.app_id, request.token_count)
    
    if not embedding_result.get("allowed", False):
        # Release the rate lock since we're not proceeding
        await embedding_rate_counter.release_request(request.app_id, rate_result["request_id"])
        logger.warning(f"API EMBEDDING LOCK DENIED (TOKEN): app={request.app_id}, tokens={request.token_count}, reason={embedding_result.get('message')}")
        return TokenResponse(
            allowed=False,
            message=f"Embedding token limit would be exceeded: {embedding_result.get('message', 'Embedding token limit exceeded')}"
        )
    
    # Combine embedding token and embedding rate request IDs
    combined_request_id = f"{embedding_result['request_id']}:{rate_result['request_id']}"
    
    # Both limits passed, return success with combined info
    logger.info(f"API EMBEDDING LOCK APPROVED: app={request.app_id}, tokens={request.token_count}, combined_id={combined_request_id}")
    
    return TokenResponse(
        allowed=True,
        request_id=combined_request_id,
        rate_request_id=rate_result["request_id"]
    )

@app.post("/embedding/report", status_code=200)
async def report_embedding_usage(report: EmbeddingReport):
    """
    Report actual embedding token usage after an API call.
    """
    logger.info(f"API EMBEDDING REPORT: app={report.app_id}, request_id={report.request_id}, prompt={report.prompt_tokens}")
    
    # Parse combined request ID if it contains both token and rate IDs
    token_request_id = report.request_id
    rate_request_id = None
    
    if ":" in report.request_id:
        token_request_id, rate_request_id = report.request_id.split(":", 1)
    
    success = await embedding_token_counter.report_usage(
        report.app_id,
        token_request_id,
        report.prompt_tokens
    )
    
    if not success:
        error_msg = f"Failed to report embedding token usage. Invalid request ID or app ID."
        logger.error(f"API EMBEDDING REPORT ERROR: app={report.app_id}, request_id={report.request_id}, reason={error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    
    # If rate request ID is provided, confirm the request
    rate_success = True
    if rate_request_id:
        rate_success = await embedding_rate_counter.confirm_request(
            report.app_id,
            rate_request_id
        )
        if not rate_success:
            logger.warning(f"API EMBEDDING REPORT PARTIAL: app={report.app_id}, token_success=True, rate_success=False, rate_id={rate_request_id}")
    
    logger.info(f"API EMBEDDING REPORT SUCCESS: app={report.app_id}, token_success={success}, rate_success={rate_success}")
    return {"success": True}

@app.post("/embedding/release", status_code=200)
async def release_embedding_tokens(request: ReleaseRequest):
    """
    Release locked embedding tokens that won't be used.
    """
    logger.info(f"API EMBEDDING RELEASE: app={request.app_id}, request_id={request.request_id}, rate_id={request.rate_request_id}")
    
    # Parse combined request ID if it contains both token and rate IDs
    token_request_id = request.request_id
    rate_request_id = request.rate_request_id
    
    if ":" in request.request_id:
        token_request_id, parsed_rate_id = request.request_id.split(":", 1)
        # Use parsed rate ID if no explicit rate_request_id was provided
        if not rate_request_id:
            rate_request_id = parsed_rate_id
    
    success = await embedding_token_counter.release_tokens(request.app_id, token_request_id)
    
    if not success:
        error_msg = f"Failed to release embedding tokens. Invalid request ID or app ID."
        logger.error(f"API EMBEDDING RELEASE ERROR: app={request.app_id}, request_id={request.request_id}, reason={error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    
    # If rate request ID is provided, release the request slot
    rate_success = True
    if rate_request_id:
        rate_success = await embedding_rate_counter.release_request(
            request.app_id,
            rate_request_id
        )
        if not rate_success:
            logger.warning(f"API EMBEDDING RELEASE PARTIAL: app={request.app_id}, token_success=True, rate_success=False, rate_id={rate_request_id}")
    
    logger.info(f"API EMBEDDING RELEASE SUCCESS: app={request.app_id}, token_success={success}, rate_success={rate_success}")
    return {"success": True}

@app.get("/embedding/status", response_model=EmbeddingStatusResponse)
async def get_embedding_status():
    """
    Get the current status of the embedding token counter and rate counter.
    """
    logger.info("API EMBEDDING STATUS: Fetching current status")
    
    embedding_status = await embedding_token_counter.get_status()
    embedding_rate_status = await embedding_rate_counter.get_status()
    
    # Calculate which limit will reset first
    token_reset = embedding_status.get("reset_time_seconds", 0)
    rate_reset = embedding_rate_status.get("reset_time_seconds", 0)
    
    # Use the minimum reset time as the effective reset time
    effective_reset = min(token_reset, rate_reset)
    
    embedding_usage = embedding_status.get("used_tokens", 0) + embedding_status.get("locked_tokens", 0)
    embedding_rate_usage = embedding_rate_status.get("used_requests", 0) + embedding_rate_status.get("locked_requests", 0)
    
    embedding_pct = (embedding_usage / EMBEDDING_TOKEN_LIMIT_PER_MINUTE) * 100 if EMBEDDING_TOKEN_LIMIT_PER_MINUTE > 0 else 0
    embedding_rate_pct = (embedding_rate_usage / EMBEDDING_RATE_LIMIT_PER_MINUTE) * 100 if EMBEDDING_RATE_LIMIT_PER_MINUTE > 0 else 0
    
    logger.info(f"API EMBEDDING STATUS RESULT: tokens={embedding_usage}/{EMBEDDING_TOKEN_LIMIT_PER_MINUTE} ({embedding_pct:.1f}%), "
                f"requests={embedding_rate_usage}/{EMBEDDING_RATE_LIMIT_PER_MINUTE} ({embedding_rate_pct:.1f}%), "
                f"token_reset={token_reset}s, rate_reset={rate_reset}s, effective_reset={effective_reset}s")
    
    return EmbeddingStatusResponse(
        available_tokens=embedding_status.get("available_tokens", 0),
        used_tokens=embedding_status.get("used_tokens", 0),
        locked_tokens=embedding_status.get("locked_tokens", 0),
        available_requests=embedding_rate_status.get("available_requests", 0),
        used_requests=embedding_rate_status.get("used_requests", 0),
        locked_requests=embedding_rate_status.get("locked_requests", 0),
        reset_time_seconds=effective_reset  # Use the minimum of the two reset times
    )

# Whisper endpoints
@app.post("/whisper/lock", response_model=WhisperRateResponse)
async def lock_whisper_rate(request: WhisperRateRequest):
    """
    Lock a Whisper API rate slot.
    Returns whether the request is allowed and a request ID if allowed.
    """
    logger.info(f"API WHISPER LOCK: app={request.app_id}")
    
    # Check the Whisper rate limit
    result = await whisper_rate_counter.lock_request(request.app_id)
    
    if not result.get("allowed", False):
        logger.warning(f"API WHISPER LOCK DENIED: app={request.app_id}, reason={result.get('message')}")
        return WhisperRateResponse(
            allowed=False,
            message=result.get('message', 'Whisper rate limit exceeded')
        )
    
    logger.info(f"API WHISPER LOCK APPROVED: app={request.app_id}, request_id={result['request_id']}")
    
    return WhisperRateResponse(
        allowed=True,
        request_id=result["request_id"]
    )

@app.post("/whisper/report", status_code=200)
async def report_whisper_usage(report: WhisperRateReport):
    """
    Report that a Whisper API request was completed.
    """
    logger.info(f"API WHISPER REPORT: app={report.app_id}, request_id={report.request_id}")
    
    success = await whisper_rate_counter.confirm_request(
        report.app_id,
        report.request_id
    )
    
    if not success:
        error_msg = f"Failed to report Whisper usage. Invalid request ID or app ID."
        logger.error(f"API WHISPER REPORT ERROR: app={report.app_id}, request_id={report.request_id}, reason={error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    
    logger.info(f"API WHISPER REPORT SUCCESS: app={report.app_id}")
    return {"success": True}

@app.post("/whisper/release", status_code=200)
async def release_whisper_rate(request: WhisperRateRelease):
    """
    Release a locked Whisper rate slot that won't be used.
    """
    logger.info(f"API WHISPER RELEASE: app={request.app_id}, request_id={request.request_id}")
    
    success = await whisper_rate_counter.release_request(request.app_id, request.request_id)
    
    if not success:
        error_msg = f"Failed to release Whisper rate slot. Invalid request ID or app ID."
        logger.error(f"API WHISPER RELEASE ERROR: app={request.app_id}, request_id={request.request_id}, reason={error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    
    logger.info(f"API WHISPER RELEASE SUCCESS: app={request.app_id}")
    return {"success": True}

@app.get("/whisper/status", response_model=WhisperRateStatusResponse)
async def get_whisper_status():
    """
    Get the current status of the Whisper rate counter.
    """
    logger.info("API WHISPER STATUS: Fetching current status")
    
    whisper_status = await whisper_rate_counter.get_status()
    
    whisper_usage = whisper_status.get("used_requests", 0) + whisper_status.get("locked_requests", 0)
    whisper_pct = (whisper_usage / WHISPER_RATE_LIMIT_PER_MINUTE) * 100 if WHISPER_RATE_LIMIT_PER_MINUTE > 0 else 0
    
    logger.info(f"API WHISPER STATUS RESULT: requests={whisper_usage}/{WHISPER_RATE_LIMIT_PER_MINUTE} ({whisper_pct:.1f}%), "
                f"reset_in={whisper_status.get('reset_time_seconds', 0)}s")
    
    return WhisperRateStatusResponse(
        available_requests=whisper_status.get("available_requests", 0),
        used_requests=whisper_status.get("used_requests", 0),
        locked_requests=whisper_status.get("locked_requests", 0),
        reset_time_seconds=whisper_status.get("reset_time_seconds", 0)
    ) 