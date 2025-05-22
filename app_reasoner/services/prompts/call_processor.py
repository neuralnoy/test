"""
Call processor service that uses Azure OpenAI to process call transcripts.
"""
import json
from typing import Dict, Any, Tuple
from common.azure_openai_service import AzureOpenAIService
from common.logger import get_logger
from app_reasoner.services.prompts.reason_mapping import get_reason_mapping
from app_reasoner.services.prompts.prompts import get_system_prompt, get_user_prompt

logger = get_logger("call_processor")

# Initialize the Azure OpenAI service
ai_service = AzureOpenAIService(app_id="app_reasoner")

# System prompt for call processing
SYSTEM_PROMPT = get_system_prompt()

# User prompt template
USER_PROMPT = get_user_prompt()

def _format_reason_options() -> str:
    """
    Format the reason mapping into a string for the prompt.
    
    Returns:
        str: Formatted reason options
    """
    reason_map = get_reason_mapping()
    options = []
    
    for tag, details in reason_map.items():
        option = f"#{tag}: {details['description']}"
        if details.get('examples'):
            examples = ", ".join([f'"{ex}"' for ex in details['examples']])
            option += f" (examples: {examples})"
        options.append(option)
    
    return "\n".join(options)

async def process_call(text: str, max_retries: int = 3) -> Tuple[bool, Dict[str, Any]]:
    """
    Process call transcript using OpenAI to summarize, categorize, and sanitize.
    
    Args:
        text: The call transcript to process
        max_retries: Maximum number of retries on failure
        
    Returns:
        Tuple[bool, Dict[str, Any]]: (success flag, processed data)
    """
    # Format reason options for the prompt
    reason_options = _format_reason_options()
    
    # Attempt processing with retries
    for attempt in range(max_retries):
        try:
            logger.info(f"Processing call transcript (attempt {attempt + 1}/{max_retries})")
            
            # Send the prompt to the AI service
            # The send_prompt method now handles token rate limit retries internally
            response = await ai_service.send_prompt(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=USER_PROMPT,
                variables={"text": text, "reason_options": reason_options},
                temperature=0.3  # Lower temperature for more deterministic results
            )
            
            # Parse the JSON response
            result = json.loads(response)
            
            # Validate required fields
            required_fields = ["summary", "reason", "ai_reason", "contains_pii_or_cid"]
            if all(field in result for field in required_fields):
                # Log whether PII or CID was detected
                logger.info(f"PII or CID detected: {result['contains_pii_or_cid']}")
                logger.info("Successfully processed call transcript")
                return True, result
            else:
                missing_fields = [field for field in required_fields if field not in result]
                logger.warning(f"Response missing required fields: {missing_fields}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {str(e)}")
        except Exception as e:
            logger.error(f"Error processing call transcript: {str(e)}")
        
        # If not the final attempt, log and retry
        if attempt < max_retries - 1:
            logger.info(f"Retrying call transcript processing (attempt {attempt + 2}/{max_retries})")
    
    # If all retries failed, return failure with error message
    error_result = {
        "summary": "Failed to process call transcript after multiple attempts",
        "reason": "#error",
        "ai_reason": "#processing_failed",
        "contains_pii_or_cid": "Unknown",
        "error": "Processing failed after maximum retry attempts"
    }
    
    return False, error_result 