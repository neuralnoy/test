import os
import asyncio
from fastapi import FastAPI, HTTPException, Request
from contextlib import asynccontextmanager
from common.logger import get_logger
from app_counter.services.token_counter import TokenCounter
from app_counter.services.rate_counter import RateCounter
from app_counter.models.schemas import (
    TokenRequest,
    TokenReport,
    ReleaseRequest,
    TokenResponse,
    StatusResponse
)

logger = get_logger("token_counter_app")

# Get token limit from environment variables or use default
TOKEN_LIMIT_PER_MINUTE = int(os.getenv("OPENAI_TOKEN_LIMIT_PER_MINUTE", "100000"))
# Get rate limit from environment variables or use default
RATE_LIMIT_PER_MINUTE = int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "100"))

# Initialize the token counter and rate counter services
token_counter = TokenCounter(tokens_per_minute=TOKEN_LIMIT_PER_MINUTE)
rate_counter = RateCounter(requests_per_minute=RATE_LIMIT_PER_MINUTE)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for the FastAPI app.
    Handles startup and shutdown events.
    """
    # Startup logic
    logger.info(f"Starting Token Counter app with limit of {TOKEN_LIMIT_PER_MINUTE} tokens per minute and {RATE_LIMIT_PER_MINUTE} requests per minute")
    
    # Initialize log monitoring service if configured
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
    account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
    container_name = os.getenv("AZURE_LOGS_CONTAINER_NAME", "application-logs")
    retention_days = int(os.getenv("AZURE_LOGS_RETENTION_DAYS", "30"))
    scan_interval = int(os.getenv("LOG_SCAN_INTERVAL", "60"))
    
    # Only initialize if blob storage is configured (either by URL or account name)
    if account_url or account_name:
        from common.log_monitor import LogMonitorService
        
        storage_endpoint = account_url or f"https://{account_name}.blob.core.windows.net"
        logger.info(f"Initializing log monitor service to upload to {storage_endpoint}/{container_name}")
        
        log_monitor = LogMonitorService(
            logs_dir=logs_dir,
            account_name=account_name,
            account_url=account_url,
            container_name=container_name,
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
    logger.info(f"CONFIG: token_limit={TOKEN_LIMIT_PER_MINUTE}, rate_limit={RATE_LIMIT_PER_MINUTE}")
    return {
        "app": "OpenAI Token Counter",
        "status": "running",
        "token_limit_per_minute": TOKEN_LIMIT_PER_MINUTE,
        "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE
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