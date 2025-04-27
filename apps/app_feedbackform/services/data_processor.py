# data_processor.py
import json
import asyncio
from typing import Dict, Any, Optional
from common.logger import get_logger
from apps.app_feedbackform.models.schemas import InputFeedbackForm, OutputFeedbackForm
from apps.app_feedbackform.services.prompts import process_feedback

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
            # Create output data structure using existing Pydantic model with SUCCESS message
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
