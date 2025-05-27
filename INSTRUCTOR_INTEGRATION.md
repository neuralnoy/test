# Instructor Integration Guide

## Overview

This codebase now includes **Instructor** integration for structured OpenAI outputs with automatic Pydantic validation. Instructor provides type-safe, validated responses from OpenAI models, eliminating the need for manual JSON parsing and validation.

## What is Instructor?

[Instructor](https://github.com/jxnl/instructor) is a Python library that:
- **Automatically converts** Pydantic models to JSON schemas for OpenAI function calling
- **Validates and parses** AI responses into strongly-typed Python objects
- **Handles retries** automatically when validation fails
- **Provides better error handling** for malformed responses

## Integration Architecture

### Enhanced Azure OpenAI Service

The `AzureOpenAIService` in `common_new/azure_openai_service.py` now includes:

```python
# New methods for structured outputs
async def structured_completion(response_model, messages, ...)  # Direct structured completion
async def structured_prompt(response_model, system_prompt, user_prompt, ...)  # Structured prompt with formatting
```

### Pydantic Response Models

Each application now has validated response models in `models/schemas.py`:

#### Feedback Form (`app_feedbackform/models/schemas.py`)
```python
class FeedbackProcessingResponse(BaseModel):
    summary: str = Field(min_length=5, max_length=500)
    hashtag: str = Field(pattern=r"^#\w+$")
    ai_hashtag: str = Field(pattern=r"^#\w+$")
    contains_pii_or_cid: Literal["Yes", "No"]
```

#### Reasoner (`app_reasoner/models/schemas.py`)
```python
class CallProcessingResponse(BaseModel):
    summary: str = Field(min_length=5, max_length=500)
    reason: str = Field(pattern=r"^#\w+$")
    ai_reason: str = Field(pattern=r"^#\w+$")
    contains_pii_or_cid: Literal["Yes", "No"]
```

## Usage Examples

### 1. Using Structured Completion Directly

```python
from common_new.azure_openai_service import AzureOpenAIService
from app_feedbackform.models.schemas import FeedbackProcessingResponse

ai_service = AzureOpenAIService(app_id="my_app")

# Structured completion with automatic validation
response = await ai_service.structured_completion(
    response_model=FeedbackProcessingResponse,
    messages=[
        {"role": "system", "content": "Your system prompt..."},
        {"role": "user", "content": "Process this feedback: ..."}
    ],
    temperature=0.0,
    max_retries=3
)

# Response is guaranteed to be a valid FeedbackProcessingResponse
print(response.summary)  # Type-safe access
print(response.hashtag) # No manual JSON parsing needed
```

### 2. Using Structured Prompts (Recommended)

```python
# Higher-level interface with prompt formatting
response = await ai_service.structured_prompt(
    response_model=FeedbackProcessingResponse,
    system_prompt="You are a feedback processor...",
    user_prompt="Process this feedback: {text}",
    variables={"text": user_feedback},
    temperature=0.0,
    max_retries=3
)
```

### 3. Enhanced Processing Functions

Each application now has enhanced processing functions:

#### Feedback Form
```python
from app_feedbackform.services.prompts import process_feedback_structured

# Instead of JSON parsing:
# success, result_dict = await process_feedback(text)

# Use structured validation:
success, validated_response = await process_feedback_structured(text)
# validated_response is a FeedbackProcessingResponse Pydantic model
```

#### Reasoner
```python
from app_reasoner.services.prompts import process_call_structured

# Instead of JSON parsing:
# success, result_dict = await process_call(text)

# Use structured validation:
success, validated_response = await process_call_structured(text)
# validated_response is a CallProcessingResponse Pydantic model
```

## Migration Strategy

You can migrate gradually without breaking existing functionality:

### Phase 1: Side-by-Side (Current State)
- Both old (`process_feedback`) and new (`process_feedback_structured`) functions are available
- Existing code continues to work unchanged
- New code can use structured validation

### Phase 2: Gradual Migration
Replace calls progressively:

```python
# Old approach (still works)
success, result = await process_feedback(text)
if success:
    summary = result["summary"]
    hashtag = result["hashtag"]

# New approach (recommended)
success, response = await process_feedback_structured(text)
if success:
    summary = response.summary  # Type-safe
    hashtag = response.hashtag  # IDE autocomplete
```

### Phase 3: Full Migration
- Update data processors to use structured functions
- Remove old JSON-based processing functions
- Benefit from full type safety and validation

## Benefits

### 1. **Type Safety**
```python
# Old: No type hints, prone to key errors
result["summary"]  # Could be KeyError
result["sumary"]   # Typo won't be caught

# New: Full type safety
response.summary   # IDE autocomplete, type checking
response.sumary    # Compile-time error
```

### 2. **Automatic Validation**
```python
# Old: Manual validation required
if "summary" not in result or len(result["summary"]) < 5:
    raise ValueError("Invalid summary")

# New: Automatic validation
# If summary is missing or too short, ValidationError is raised automatically
```

### 3. **Better Error Handling**
```python
# Old: Cryptic JSON errors
try:
    result = json.loads(response)
except json.JSONDecodeError as e:
    # Unclear what went wrong

# New: Clear validation errors
try:
    response = await structured_completion(...)
except ValidationError as e:
    # Specific field validation errors
    print(e.errors())  # Detailed error information
```

### 4. **Retry Logic**
Instructor automatically retries when validation fails, asking the AI to correct the response format.

## Testing

Run the integration test:

```bash
python test_instructor_integration.py
```

This will verify:
- Azure OpenAI service initialization with Instructor
- Structured completion functionality
- Pydantic model validation
- Both feedback and call processing workflows

## Configuration

No additional configuration required beyond existing Azure OpenAI setup. Instructor works with your existing:
- Environment variables (`APP_OPENAI_API_VERSION`, `APP_OPENAI_API_BASE`)
- Authentication (Azure Identity)
- Token management (Token Counter service)

## Advanced Features

### Custom Validators
Add domain-specific validation to your Pydantic models:

```python
from pydantic import validator

class FeedbackProcessingResponse(BaseModel):
    # ... existing fields ...
    
    @validator('hashtag')
    def validate_hashtag_in_predefined_list(cls, v):
        valid_hashtags = ["#service", "#quality", "#billing"]
        if v not in valid_hashtags:
            raise ValueError(f"Hashtag must be one of: {valid_hashtags}")
        return v
    
    @validator('summary')
    def validate_no_pii_in_summary(cls, v):
        import re
        if re.search(r'\b\d{3,}\b', v):  # Simple number pattern
            raise ValueError("Summary may contain account numbers")
        return v
```

### Response Model Evolution
Easily extend response models as requirements change:

```python
class FeedbackProcessingResponse(BaseModel):
    # Existing fields
    summary: str
    hashtag: str
    ai_hashtag: str
    contains_pii_or_cid: Literal["Yes", "No"]
    
    # New fields (optional for backward compatibility)
    confidence_score: Optional[float] = Field(ge=0.0, le=1.0)
    detected_language: Optional[str] = None
    processing_time: Optional[datetime] = None
```

## Troubleshooting

### Common Issues

1. **ValidationError: Field required**
   - The AI didn't provide all required fields
   - Instructor will automatically retry with clearer instructions

2. **ValidationError: String should match pattern**
   - Field doesn't match regex pattern (e.g., hashtag without #)
   - Review your prompt to ensure clear format instructions

3. **Timeout errors**
   - Increase `max_retries` parameter
   - Check Azure OpenAI service availability

### Debug Mode
Enable detailed logging:

```python
import logging
logging.getLogger("instructor").setLevel(logging.DEBUG)
```

## Best Practices

1. **Use appropriate temperature**: Lower (0.0-0.3) for structured outputs
2. **Provide clear prompts**: Specify exact format requirements
3. **Set reasonable retry limits**: Usually 2-3 retries are sufficient
4. **Design defensive models**: Use Optional fields for non-critical data
5. **Add meaningful field descriptions**: Helps both AI and developers

## Dependencies

The integration adds these dependencies to `requirements.txt`:
- `instructor>=1.0.0` - Main library
- Existing `pydantic>=2.0.0` - Already in project
- Existing `openai>=1.6.0` - Already in project

All dependencies are compatible with your existing stack. 