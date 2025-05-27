from pydantic import BaseModel, Field, validator
from typing import Literal

class InputReasoner(BaseModel):
    id: str
    taskId: str
    language: str
    text: str

class OutputReasoner(BaseModel):
    id: str
    taskId: str
    ai_reason: str
    reason: str
    summary: str
    message: str

class InternalReasonerResult(BaseModel):
    id: str
    taskId: str
    ai_reason: str
    reason: str
    summary: str
    message: str
    contains_pii_or_cid: str

class CallProcessingResponse(BaseModel):
    """Pydantic model for validating OpenAI call transcript processing responses."""
    
    summary: str = Field(
        description="Concise summary of the call transcript with all PII removed",
        min_length=5,
        max_length=500
    )
    
    reason: str = Field(
        description="Predefined reason from the provided list",
        pattern=r"^#\w+$"
    )
    
    ai_reason: str = Field(
        description="AI-generated reason relevant to the call transcript",
        pattern=r"^#\w+$"
    )
    
    contains_pii_or_cid: Literal["Yes", "No"] = Field(
        description="Whether the original call transcript contains PII or CID"
    )
    
    @validator('reason')
    def validate_reason_starts_with_hash(cls, v):
        """Ensure reason starts with #."""
        if not v.startswith('#'):
            raise ValueError("Reason must start with #")
        return v
    
    @validator('ai_reason')
    def validate_ai_reason_starts_with_hash(cls, v):
        """Ensure AI reason starts with #."""
        if not v.startswith('#'):
            raise ValueError("AI reason must start with #")
        return v 