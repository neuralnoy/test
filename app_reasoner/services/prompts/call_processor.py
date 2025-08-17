"""
Call processor service that uses Azure OpenAI to process call transcripts.
"""
from typing import Tuple
from pydantic import ValidationError
from common_new.azure_openai_service import AzureOpenAIService
from common_new.logger import get_logger
from app_reasoner.models.schemas import ReasonerProcessingResponse
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

async def process_call_structured(text: str, max_retries: int = 3) -> Tuple[bool, ReasonerProcessingResponse]:
    """
    Process call transcript using Instructor for structured, validated outputs.
    
    Args:
        text: The call transcript to process
        max_retries: Maximum number of retries on failure
        
    Returns:
        Tuple[bool, ReasonerProcessingResponse]: (success flag, validated response)
    """

    reason_options = _format_reason_options()

    for attempt in range(max_retries):
        try:
            logger.info("Processing call transcript with structured validation")
            
            # Use the enhanced service for structured completion
            response = await ai_service.structured_prompt(
                response_model=ReasonerProcessingResponse,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=USER_PROMPT,
                variables={"text": text, "reason_options": reason_options},
                temperature=0.0,
                max_retries=max_retries
            )
            
            logger.info(f"PII or CID detected: {response.contains_pii_or_cid}")
            logger.info("Successfully processed call transcript with validation")
            
            return True, response
            
        except ValidationError as e:
            logger.error(f"Validation error in AI response: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error processing call transcript: {str(e)}")
        
        # If not the final attempt, log and retry
        if attempt < max_retries - 1:
            logger.info(f"Retrying call transcript processing (attempt {attempt + 2}/{max_retries})")
    # If all retries failed, return failure with error message
    error_result = {
        "ai_generated": False,
        "ai_hashtags": [],
        "ai_hashtags_native": [],
        "authentication": "Unknown",
        "call_flags": "EXTERN",
        "call_reason": "Unknown",
        "call_triggers": "Unknown",
        "call_triggers_native": "Unknown",
        "caller_authentication": "Unknown",
        "category": "Unknown",
        "client_lifecycle_event": "Unknown",
        "entry_point": "Unknown",
        "hashtags": [],
        "live_help": "No",
        "product": [],
        "product_cluster": "Unknown",
        "resolution": {
            "CALLBACK": "Unknown",
            "CALL_TRANSFER": "Unknown",
            "CONTACT_BRANCH": "Unknown"
        },
        "resolution_flag": "Unknown",
        "self_service": "Unknown",
        "sentiment": "Unknown",
        "speaker": {
            "Speaker 1": "Unknown",
            "Speaker 2": "Unknown"
        },
        "subtopics": "Unknown",
        "summary": "Unknown",
        "summary_native": "Unknown"
    }
    
    return False, error_result 
