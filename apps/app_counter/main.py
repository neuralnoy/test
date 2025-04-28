import os
import asyncio
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from common.logger import get_logger
from apps.app_counter.services.token_counter import TokenCounter
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

# Initialize the token counter service
token_counter = TokenCounter(tokens_per_minute=TOKEN_LIMIT_PER_MINUTE)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for the FastAPI app.
    Handles startup and shutdown events.
    """
    # Startup logic
    logger.info(f"Starting Token Counter app with limit of {TOKEN_LIMIT_PER_MINUTE} tokens per minute")
    
    yield  # This is where the app runs
    
    # Shutdown logic
    logger.info("Shutting down Token Counter app")

app = FastAPI(title="OpenAI Token Counter", lifespan=lifespan)

@app.get("/")
def read_root():
    return {
        "app": "OpenAI Token Counter",
        "status": "running",
        "token_limit_per_minute": TOKEN_LIMIT_PER_MINUTE
    }

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

@app.post("/lock", response_model=TokenResponse)
async def lock_tokens(request: TokenRequest):
    """
    Lock tokens for usage.
    Returns whether the request is allowed and a request ID if allowed.
    """
    logger.info(f"Received token lock request from {request.app_id} for {request.token_count} tokens")
    
    result = await token_counter.lock_tokens(request.app_id, request.token_count)
    
    return TokenResponse(
        allowed=result.get("allowed", False),
        request_id=result.get("request_id"),
        message=result.get("message")
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
    
    return {"success": True}

@app.get("/status", response_model=StatusResponse)
async def get_status():
    """
    Get the current status of the token counter.
    """
    status = await token_counter.get_status()
    
    return StatusResponse(
        available_tokens=status["available_tokens"],
        used_tokens=status["used_tokens"],
        locked_tokens=status["locked_tokens"],
        reset_time_seconds=status["reset_time_seconds"]
    ) 