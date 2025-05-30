"""
Feedback processor service that uses Azure OpenAI to process feedback text.
"""
from typing import Tuple
from pydantic import ValidationError
from common_new.azure_openai_service import AzureOpenAIService
from common_new.logger import get_logger
from app_feedbackform.models.schemas import FeedbackProcessingResponse
from app_feedbackform.services.prompts.hashtag_mapping import get_hashtag_mapping
from app_feedbackform.services.prompts.prompts import get_system_prompt, get_user_prompt

logger = get_logger("prompts")

# Initialize the Azure OpenAI service
ai_service = AzureOpenAIService(app_id="app_feedbackform")

# System prompt for feedback processing
SYSTEM_PROMPT = get_system_prompt()

# User prompt template
USER_PROMPT = get_user_prompt()

def _format_hashtag_options() -> str:
    """
    Format the hashtag mapping into a string for the prompt.
    
    Returns:
        str: Formatted hashtag options
    """
    hashtag_map = get_hashtag_mapping()
    options = []
    
    for tag, details in hashtag_map.items():
        option = f"#{tag}: {details['description']}"
        if details.get('examples'):
            examples = ", ".join([f'"{ex}"' for ex in details['examples']])
            option += f" (examples: {examples})"
        options.append(option)
    
    return "\n".join(options)

async def process_feedback_structured(text: str, max_retries: int = 3) -> Tuple[bool, FeedbackProcessingResponse]:
    """
    Process feedback using Instructor for structured, validated outputs.
    
    Args:
        text: The feedback text to process
        max_retries: Maximum number of retries on failure
        
    Returns:
        Tuple[bool, FeedbackProcessingResponse]: (success flag, validated response)
    """
    hashtag_options = _format_hashtag_options()

    for attempt in range(max_retries):
        try:
            logger.info("Processing feedback with structured validation")
            
            # Use the enhanced service for structured completion
            response = await ai_service.structured_prompt(
                response_model=FeedbackProcessingResponse,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=USER_PROMPT,
                variables={"text": text, "hashtag_options": hashtag_options},
                temperature=0.0
            )
            
            logger.info(f"PII or CID detected: {response.contains_pii_or_cid}")
            logger.info("Successfully processed feedback with validation")
            
            return True, response
            
        except ValidationError as e:
            logger.error(f"Validation error in AI response: {str(e)}")
            # Create a fallback response
            fallback_response = FeedbackProcessingResponse(
                summary="Failed to process feedback due to validation errors",
                hashtag="#error",
                ai_hashtag="#validation_failed",
                category="failed",
                contains_pii_or_cid="No"
            )
            return False, fallback_response
            
        except Exception as e:
            logger.error(f"Error processing feedback: {str(e)}")
            # Create a fallback response
            fallback_response = FeedbackProcessingResponse(
                summary="Failed to process feedback because of validation errors",
                hashtag="#error", 
                ai_hashtag="#processing_failed",
                category="failed",
                contains_pii_or_cid="No"
            )
            return False, fallback_response
        
        if attempt < max_retries - 1:
            logger.info(f"Retrying feedback processing (attempt {attempt + 2}/{max_retries})")
    
    # If all retries failed, return failure with error message
    error_result = FeedbackProcessingResponse(
        summary="Failed to process feedback after multiple attempts",
        hashtag="#error",
        ai_hashtag="#processing_failed",
        category="failed",
        contains_pii_or_cid="Unknown",
        error="Processing failed after maximum retry attempts"
    )

    
    return False, error_result