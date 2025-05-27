from pydantic import BaseModel, Field, field_validator
from typing import Literal

class InputFeedbackForm(BaseModel):
    id: str
    taskId: str
    language: str
    text: str

class OutputFeedbackForm(BaseModel):
    id: str
    taskId: str
    ai_hashtag: str
    hashtag: str
    summary: str
    message: str

class InternalFeedbackResult(BaseModel):
    id: str
    taskId: str
    ai_hashtag: str
    hashtag: str
    summary: str
    message: str
    contains_pii_or_cid: str

class FeedbackProcessingResponse(BaseModel):
    """Pydantic model for validating OpenAI feedback processing responses."""
    
    summary: str = Field(
        description="Concise summary of the feedback with all PII removed",
        min_length=5,
        max_length=500
    )
    
    hashtag: str = Field(
        description="Predefined hashtag from the provided list",
        pattern=r"^#\w+$"
    )
    
    ai_hashtag: str = Field(
        description="AI-generated hashtag relevant to the feedback",
        pattern=r"^#\w+$"
    )
    
    contains_pii_or_cid: Literal["Yes", "No"] = Field(
        description="Whether the original feedback contains PII or CID"
    )
    
    @field_validator('hashtag')
    def validate_hashtag_starts_with_hash(cls, v):
        """Ensure hashtag starts with #."""
        if not v.startswith('#'):
            raise ValueError("Hashtag must start with #")
        return v
    
    @field_validator('ai_hashtag')
    def validate_ai_hashtag_starts_with_hash(cls, v):
        """Ensure AI hashtag starts with #."""
        if not v.startswith('#'):
            raise ValueError("AI hashtag must start with #")
        return v
