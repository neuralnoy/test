# data_processor.py
import json
import asyncio
from typing import Dict, Any, Optional
from common_new.logger import get_logger
from app_feedbackform.models.schemas import InputFeedbackForm, OutputFeedbackForm, InternalFeedbackResult
from app_feedbackform.services.prompts.feedback_processor import process_feedback

logger = get_logger("feedback_form_processor")

async def process_data(message_body: str) -> Optional[Dict[str, Any]]:
    """
    Process feedback form data from the in_queue and return processed data for the out_queue.
    
    Args:
        message_body: JSON string containing the feedback form data
    
    Returns:
        Processed data as a dictionary with SUCCESS or FAIL message, or None if processing failed
    """
    try:
        logger.info("Processing feedback form data")
        
        # Parse the message body
        data_dict = json.loads(message_body)
        
        # Validate data using existing Pydantic model
        form_data = InputFeedbackForm(**data_dict)
        
        # Process the feedback text using Azure OpenAI
        success, result = await process_feedback(form_data.text)
        
        if success:
            # Create internal result with PII/CID detection information for logging
            internal_result = InternalFeedbackResult(
                id=form_data.id,
                taskId=form_data.taskId,
                ai_hashtag=result["ai_hashtag"],
                hashtag=result["hashtag"],
                summary=result["summary"],
                message="SUCCESS",
                contains_pii_or_cid=result["contains_pii_or_cid"]
            )
            
            # Log the PII/CID detection information
            logger.info(f"Feedback form {form_data.id} contains PII or CID: {internal_result.contains_pii_or_cid}")
            
            # Create output data structure using existing Pydantic model with SUCCESS message
            # This is what will be sent to the queue (without the contains_pii_or_cid field)
            output_data = OutputFeedbackForm(
                id=form_data.id,
                taskId=form_data.taskId,
                ai_hashtag=result["ai_hashtag"],
                hashtag=result["hashtag"],
                summary=result["summary"],
                message="SUCCESS"
            )
            
            logger.info(f"Successfully processed feedback form {form_data.id}")
            return output_data.model_dump()
        else:
            # Processing failed after retries, return error response
            # For failed processing, we still want to log if we have PII/CID information
            contains_pii_or_cid = result.get("contains_pii_or_cid", "Unknown")
            logger.info(f"Failed feedback form {form_data.id} contains PII or CID: {contains_pii_or_cid}")
            
            output_data = OutputFeedbackForm(
                id=form_data.id,
                taskId=form_data.taskId,
                ai_hashtag=result["ai_hashtag"],
                hashtag=result["hashtag"],
                summary=result["summary"],
                message="failed"
            )
            
            logger.error(f"Failed to process feedback form {form_data.id}")
            return output_data.model_dump()
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in message: {str(e)}")
        # Return failure response
        try:
            # Try to extract an ID and taskId if possible
            data = json.loads(message_body) if isinstance(message_body, str) else {}
            form_id = data.get("id", "unknown")
            task_id = data.get("taskId", "unknown")
            
            output_data = OutputFeedbackForm(
                id=form_id,
                taskId=task_id,
                ai_hashtag="#error",
                hashtag="#error",
                summary=f"JSON parsing error: {str(e)}",
                message="failed"
            )
            return output_data.model_dump()
        except:
            # If we can't even create a proper error response, return None
            return None
            
    except Exception as e:
        logger.error(f"Error processing feedback form: {str(e)}")
        # Return failure response with error details
        try:
            # Try to get the ID and taskId from the exception context if possible
            form_id = getattr(form_data, 'id', "unknown") if 'form_data' in locals() else "unknown"
            task_id = getattr(form_data, 'taskId', "unknown") if 'form_data' in locals() else "unknown"
            
            output_data = OutputFeedbackForm(
                id=form_id,
                taskId=task_id,
                ai_hashtag="#error",
                hashtag="#error",
                summary=f"Processing error: {str(e)}",
                message="failed"
            )
            return output_data.model_dump()
        except:
            # If we can't even create a proper error response, return None
            return None

# USAGE EXAMPLE: To use the new structured validation with Instructor/Pydantic:
#
# from app_feedbackform.services.prompts.feedback_processor import process_feedback_structured
# 
# # Replace the line:
# # success, result = await process_feedback(form_data.text)
# 
# # With:
# # success, structured_result = await process_feedback_structured(form_data.text)
# 
# # The structured_result will be a validated FeedbackProcessingResponse Pydantic model
# # with automatic validation, better error handling, and type safety.
# # You can access fields directly: structured_result.summary, structured_result.hashtag, etc.
# # The response is guaranteed to match the expected schema or raise a ValidationError.
