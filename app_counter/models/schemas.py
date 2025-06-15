from pydantic import BaseModel
from typing import Optional

class TokenRequest(BaseModel):
    """Request to lock tokens for usage."""
    app_id: str
    token_count: int

class TokenReport(BaseModel):
    """Report actual token usage after API call."""
    app_id: str
    request_id: str
    prompt_tokens: int
    completion_tokens: int
    rate_request_id: Optional[str] = None

class EmbeddingReport(BaseModel):
    """Report actual embedding token usage after API call."""
    app_id: str
    request_id: str
    prompt_tokens: int

class ReleaseRequest(BaseModel):
    """Request to release locked tokens."""
    app_id: str
    request_id: str
    rate_request_id: Optional[str] = None

class TokenResponse(BaseModel):
    """Response for token requests."""
    allowed: bool
    request_id: Optional[str] = None
    rate_request_id: Optional[str] = None
    message: Optional[str] = None

class StatusResponse(BaseModel):
    """Status of the token counter."""
    available_tokens: int
    used_tokens: int
    locked_tokens: int
    available_requests: Optional[int] = None
    used_requests: Optional[int] = None
    locked_requests: Optional[int] = None
    reset_time_seconds: int

class EmbeddingStatusResponse(BaseModel):
    """Status of the embedding token counter."""
    available_tokens: int
    used_tokens: int
    locked_tokens: int
    available_requests: Optional[int] = None
    used_requests: Optional[int] = None
    locked_requests: Optional[int] = None
    reset_time_seconds: int

# Whisper-specific schemas
class WhisperRateRequest(BaseModel):
    """Request to lock a Whisper API rate slot."""
    app_id: str

class WhisperRateReport(BaseModel):
    """Report that a Whisper API request was completed."""
    app_id: str
    request_id: str

class WhisperRateRelease(BaseModel):
    """Request to release a locked Whisper rate slot."""
    app_id: str
    request_id: str

class WhisperRateResponse(BaseModel):
    """Response for Whisper rate requests."""
    allowed: bool
    request_id: Optional[str] = None
    message: Optional[str] = None

class WhisperRateStatusResponse(BaseModel):
    """Status of the Whisper rate counter."""
    available_requests: int
    used_requests: int
    locked_requests: int
    reset_time_seconds: int 