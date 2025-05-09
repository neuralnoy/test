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