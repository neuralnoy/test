import json
from common_new.logger import get_logger
from app_whisper.models.schemas import InputWhisper, OutputWhisper
from app_whisper.services.businesslogic.pipeline import run_pipeline

logger = get_logger("whisper")

async def process_data(message_body: str) -> OutputWhisper:
    """
    Process whisper data from the in_queue and return processed data for the out_queue.
    
    Args:
        message_body: JSON string containing the whisper data
    
    Returns:
        Processed data as a dictionary with SUCCESS or FAIL message, or None if processing failed
    """
    try:    
        logger.info("Processing whisper data")
        
        # Parse the message body
        data_dict = json.loads(message_body)
        
        # Validate data using existing Pydantic model
        whisper_data = InputWhisper(**data_dict)
        
        # Process the whisper data using Azure OpenAI
        success, result = await run_pipeline(whisper_data.filename)
        
        if success:            
            # This is what will be sent to the queue
            # The 'diarization' flag from the pipeline result directly indicates success.
            output_data = OutputWhisper(
                id=whisper_data.id,
                filename=whisper_data.filename,
                transcription=result.text,
                diarization=result.diarization,
                message="SUCCESS"
            )
            
            logger.info(f"Successfully processed whisper {whisper_data.id}")
            return output_data.model_dump()
        else:
            # Processing failed after retries, return error response
            # For failed processing, diarization is False and use result.text
            output_data = OutputWhisper(
                id=whisper_data.id,
                filename=whisper_data.filename,
                transcription=result.text,
                diarization=False,
                message="failed"
            )
            
            logger.error(f"Failed to process whisper {whisper_data.id}")
            return output_data.model_dump()
            
    except Exception as e:
        logger.error(f"Error processing whisper: {str(e)}")
        # Return failure response with error details
        whisper_id = getattr(whisper_data, 'id', "unknown") if 'whisper_data' in locals() else "unknown"
        filename = getattr(whisper_data, 'filename', "unknown") if 'whisper_data' in locals() else "unknown"
            
        output_data = OutputWhisper(
                id=whisper_id,
                filename=filename,
                transcription="",
                diarization=False,
                message="failed"
            )
        return output_data.model_dump()
