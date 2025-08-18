import json
from typing import Dict, Any, Optional
from common_new.logger import get_logger
from app_reasoner.models.schemas import InputReasoner, OutputReasoner, ReasonerProcessingResponse
from app_reasoner.services.prompts.call_processor import process_call_structured

logger = get_logger("services")


async def process_data(message_body: str) -> Optional[Dict[str, Any]]:
    """
    Process reasoner data from the in_queue and return processed data for the out_queue.
    
    Args:
        message_body: JSON string containing the reasoner data
    
    Returns:
        Processed data as a dictionary with SUCCESS or FAIL message, or None if processing failed
    """
    try:
        logger.info("Processing reasoner data")
        
        # Parse the message body
        data_dict = json.loads(message_body)
        
        # Validate data using existing Pydantic model
        call_data = InputReasoner(**data_dict)
                
        # Process the message data using Azure OpenAI
        success, result = await process_call_structured(call_data)
        
        if success:
            # Create internal result with PII/CID detection information for logging
            internal_result = ReasonerProcessingResponse(
                ai_generated=result.ai_generated,
                ai_hashtags=result.ai_hashtags,
                ai_hashtags_native=result.ai_hashtags_native,
                authentication=result.authentication,
                call_flags=result.call_flags,
                call_reason=result.call_reason,
                call_triggers=result.call_triggers,
                call_triggers_native=result.call_triggers_native,
                caller_authentication=result.caller_authentication,
                category=result.category,
                client_lifecycle_event=result.client_lifecycle_event,
                entry_point=result.entry_point,
                further_sentiment=result.further_sentiment,
                hashtags=result.hashtags,
                live_help=result.live_help,
                product=result.product,
                product_cluster=result.product_cluster,
                resolution=result.resolution,
                resolution_flag=result.resolution_flag,
                self_service=result.self_service,
                sentiment=result.sentiment,
                speaker=result.speaker,
                subtopics=result.subtopics,
                summary=result.summary,
                summary_native=result.summary_native,
                contains_pii_or_cid=result.contains_pii_or_cid
            )
            
            # Log the PII/CID detection information
            logger.info(f"Reasoner form {call_data.id} contains PII or CID: {internal_result.contains_pii_or_cid}")
                        
            # Create output data structure using existing Pydantic model with SUCCESS message
            # This is what will be sent to the queue (without the contains_pii_or_cid field)
            output_data = OutputReasoner(
                id=call_data.id,
                taskId=call_data.taskId,
                ai_generated=result.ai_generated,
                ai_hashtags=result.ai_hashtags,
                ai_hashtags_native=result.ai_hashtags_native,
                authentication=result.authentication,
                call_flags=result.call_flags,
                call_reason=result.call_reason,
                call_triggers=result.call_triggers,
                call_triggers_native=result.call_triggers_native,
                caller_authentication=result.caller_authentication,
                category=result.category,
                client_lifecycle_event=result.client_lifecycle_event,
                entry_point=result.entry_point,
                further_sentiment=result.further_sentiment,
                hashtags=result.hashtags,
                live_help=result.live_help,
                product=result.product,
                product_cluster=result.product_cluster,
                resolution=result.resolution,
                resolution_flag=result.resolution_flag,
                self_service=result.self_service,
                sentiment=result.sentiment,
                speaker=result.speaker,
                subtopics=result.subtopics,
                summary=result.summary,
                summary_native=result.summary_native,
                message="SUCCESS"
            )
            
            logger.info(f"Successfully processed reasoner {call_data.id}")
            return output_data.model_dump()
        else:
            # Processing failed after retries, return error response
            # For failed processing, we still want to log if we have PII/CID information
            contains_pii_or_cid = result.get("contains_pii_or_cid", "Unknown")
            logger.info(f"Failed reasoner {call_data.id} contains PII or CID: {contains_pii_or_cid}")
            
            output_data = OutputReasoner(
                id=call_data.id,
                taskId=call_data.taskId,
                ai_generated=result.ai_generated,
                ai_hashtags=result.ai_hashtags,
                ai_hashtags_native=result.ai_hashtags_native,
                authentication=result.authentication,
                call_flags=result.call_flags,
                call_reason=result.call_reason,
                call_triggers=result.call_triggers,
                call_triggers_native=result.call_triggers_native,
                caller_authentication=result.caller_authentication,
                category=result.category,
                client_lifecycle_event=result.client_lifecycle_event,
                entry_point=result.entry_point,
                further_sentiment=result.further_sentiment,
                hashtags=result.hashtags,
                live_help=result.live_help,
                product=result.product,
                product_cluster=result.product_cluster,
                resolution=result.resolution,
                resolution_flag=result.resolution_flag,
                self_service=result.self_service,
                sentiment=result.sentiment,
                speaker=result.speaker,
                subtopics=result.subtopics,
                summary=result.summary,
                summary_native=result.summary_native,
                message="Failed after several valid retries"
            )
            
            logger.error(f"Failed to process reasoner {call_data.id}")
            return output_data.model_dump()
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in message: {str(e)}")
        # Return failure response
        try:
            # Try to extract an ID and taskId if possible
            data = json.loads(message_body) if isinstance(message_body, str) else {}
            call_id = data.get("id", "unknown")
            task_id = data.get("taskId", "unknown")
            
            output_data = OutputReasoner(
                id=call_id,
                taskId=task_id,
                ai_generated=False,
                ai_hashtags=["#error"],
                ai_hashtags_native=["#error"],
                authentication="No",
                call_flags="EXTERN",
                call_reason="Unknown",
                call_triggers="Unknown",
                call_triggers_native="Unknown",
                caller_authentication="NO_AUTHENTICATION",
                category="Unknown",
                client_lifecycle_event="NOT_MENTIONED",
                entry_point="Not mentioned",
                further_sentiment={
                    "sentiment_advice": "Neutral",
                    "sentiment_feedback": "Neutral",
                    "sentiment_service": "Neutral"
                },
                hashtags=["#error"],
                live_help="No",
                product=["#error"],
                product_cluster="Unknown",
                resolution={
                    "CALLBACK": "No",
                    "CALL_TRANSFER": "No",
                    "CONTACT_BRANCH": "No"
                },
                resolution_flag="Unknown",
                self_service={
                    "self_service_guidance": "No",
                    "self_service_mention": "No",
                    "self_service_usage": "No"
                },
                sentiment="Neutral",
                speaker={
                    "Speaker 1": "Client",
                    "Speaker 2": "Agent"
                },
                subtopics="Unknown",
                summary="Unknown",
                summary_native="Unknown",
                message=f"Failed: JSON parsing error: {str(e)}"
            )
            return output_data.model_dump()
        except:
            # If we can't even create a proper error response, return None
            return None
            
    except Exception as e:
        logger.error(f"Error processing reasoner: {str(e)}")
        # Return failure response with error details
        try:
            # Try to get the ID and taskId from the exception context if possible
            form_id = getattr(call_data, 'id', "unknown") if 'call_data' in locals() else "unknown"
            task_id = getattr(call_data, 'taskId', "unknown") if 'call_data' in locals() else "unknown"
            
            output_data = OutputReasoner(
                id=form_id,
                taskId=task_id,
                ai_generated=False,
                ai_hashtags=["#error"],
                ai_hashtags_native=["#error"],
                authentication="No",
                call_flags="EXTERN",
                call_reason="Unknown",
                call_triggers="Unknown",
                call_triggers_native="Unknown",
                caller_authentication="NO_AUTHENTICATION",
                category="Unknown",
                client_lifecycle_event="NOT_MENTIONED",
                entry_point="Not mentioned",
                further_sentiment={
                    "sentiment_advice": "Neutral",
                    "sentiment_feedback": "Neutral",
                    "sentiment_service": "Neutral"
                },
                hashtags=["#error"],
                live_help="No",
                product=["#error"],
                product_cluster="Unknown",
                resolution={
                    "CALLBACK": "No",
                    "CALL_TRANSFER": "No",
                    "CONTACT_BRANCH": "No"
                },
                resolution_flag="Unknown",
                self_service={
                    "self_service_guidance": "No",
                    "self_service_mention": "No",
                    "self_service_usage": "No"
                },
                sentiment="Neutral",
                speaker={
                    "Speaker 1": "Client",
                    "Speaker 2": "Agent"
                },
                subtopics="Unknown",
                summary="Unknown",
                summary_native="Unknown",
                message=f"Failed: JSON Processing error: {str(e)}"
            )
            return output_data.model_dump()
        except:
            # If we can't even create a proper error response, return None
            return None
