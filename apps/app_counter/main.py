import os
import asyncio
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from common.logger import get_logger
from apps.app_counter.services.token_counter import TokenCounter
from apps.app_counter.services.rate_counter import RateCounter
from apps.app_counter.models.schemas import (
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
    
    yield  # This is where the app runs
    
    # Shutdown logic
    logger.info("Shutting down Token Counter app")

app = FastAPI(title="OpenAI Token Counter", lifespan=lifespan)

@app.get("/")
def read_root():
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
    logger.info(f"Received token lock request from {request.app_id} for {request.token_count} tokens")
    
    # First check the rate limit
    rate_result = await rate_counter.lock_request(request.app_id)
    
    if not rate_result.get("allowed", False):
        return TokenResponse(
            allowed=False,
            message=rate_result.get("message", "Rate limit exceeded")
        )
    
    # Then check the token limit
    token_result = await token_counter.lock_tokens(request.app_id, request.token_count)
    
    if not token_result.get("allowed", False):
        # Release the rate lock since we're not proceeding
        await rate_counter.release_request(request.app_id, rate_result["request_id"])
        return TokenResponse(
            allowed=False,
            message=token_result.get("message", "Token limit exceeded")
        )
    
    # Combine token and rate request IDs for backward compatibility with existing clients
    # Clients can parse this combined ID if they're updated, or use it as is if they're not
    combined_request_id = f"{token_result['request_id']}:{rate_result['request_id']}"
    
    # Both limits passed, return success with combined info
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
    logger.info(f"Received usage report from {report.app_id}: prompt={report.prompt_tokens}, completion={report.completion_tokens}")
    
    success = await token_counter.report_usage(
        report.app_id,
        report.request_id,
        report.prompt_tokens,
        report.completion_tokens
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to report token usage. Invalid request ID or app ID.")
    
    # If rate request ID is provided, confirm the request
    if report.rate_request_id:
        rate_success = await rate_counter.confirm_request(
            report.app_id,
            report.rate_request_id
        )
        if not rate_success:
            logger.warning(f"Failed to confirm rate request for {report.app_id}")
    
    return {"success": True}

@app.post("/release", status_code=200)
async def release_tokens(request: ReleaseRequest):
    """
    Release locked tokens that won't be used.
    """
    logger.info(f"Received token release request from {request.app_id} for request ID {request.request_id}")
    
    success = await token_counter.release_tokens(request.app_id, request.request_id)
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to release tokens. Invalid request ID or app ID.")
    
    # If rate request ID is provided, release the request slot
    if request.rate_request_id:
        rate_success = await rate_counter.release_request(
            request.app_id,
            request.rate_request_id
        )
        if not rate_success:
            logger.warning(f"Failed to release rate request for {request.app_id}")
    
    return {"success": True}

@app.get("/status", response_model=StatusResponse)
async def get_status():
    """
    Get the current status of the token counter and rate counter.
    """
    token_status = await token_counter.get_status()
    rate_status = await rate_counter.get_status()
    
    return StatusResponse(
        available_tokens=token_status["available_tokens"],
        used_tokens=token_status["used_tokens"],
        locked_tokens=token_status["locked_tokens"],
        available_requests=rate_status["available_requests"],
        used_requests=rate_status["used_requests"],
        locked_requests=rate_status["locked_requests"],
        reset_time_seconds=token_status["reset_time_seconds"]
    ) 