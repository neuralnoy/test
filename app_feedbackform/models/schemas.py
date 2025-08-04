from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional


class InputFeedbackForm(BaseModel):
    """Input data, which we receive from the queue"""
    id: str
    taskId: Optional[str] = None
    language: str
    text: str


class OutputFeedbackForm(BaseModel):
    """Output data, which we send to the queue"""
    id: str
    taskId: Optional[str] = None
    hashtag: str
    category: str
    summary: str
    ai_hashtag: str
    message: str


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
    
    category: str = Field(
        description="Mapped category according to predefined hashtag",
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
