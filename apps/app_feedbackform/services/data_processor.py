import json
import asyncio
from typing import Dict, Any, Optional
from common.logger import get_logger

logger = get_logger("feedback_form_processor")

async def process_data(message_body: str) -> Optional[Dict[str, Any]]:
    """
    Process feedback form data from the in_queue and return processed data for the out_queue.
    
    Args:
        message_body: JSON string containing the feedback form data
    
    Returns:
        Processed data as a dictionary, or None if processing failed
    """
    try:
        logger.info("Processing feedback form data")
        
        # Parse the message body
        data = json.loads(message_body)
        
        # Extract required fields
        form_id = data.get("id")
        task_id = data.get("taskId")
        language = data.get("language")
        text = data.get("text")
        
        if not all([form_id, task_id, language, text]):
            logger.error(f"Missing required fields in message: {message_body}")
            return None
        
        # Simulate processing time (replace with actual processing logic)
        await asyncio.sleep(0.5)
        
        # Generate AI hashtag and summary (replace with actual logic)
        ai_hashtag = f"#{text.split()[0].lower() if text else 'unknown'}"
        hashtag = f"#{language.lower() if language else 'en'}"
        summary = text[:100] + "..." if len(text) > 100 else text
        
        # Create output data structure
        output_data = {
            "id": form_id,
            "ai_hashtag": ai_hashtag,
            "hashtag": hashtag,
            "summary": summary
        }
        
        logger.info(f"Successfully processed feedback form {form_id}")
        return output_data
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in message: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error processing feedback form: {str(e)}")
        return None
