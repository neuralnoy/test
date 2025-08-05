"""
Hashtag mapping for the feedback form application.
Loads hashtag data from dispocodes.json and converts to mapping format.
"""
from app_feedbackform.services.prompts.dispocode_reader import get_dispocode_reader
from common_new.logger import get_logger

logger = get_logger("prompts")

def get_hashtag_mapping():
    """
    Get the hashtag mapping dictionary from dispocodes.
    
    Converts from:
    [
      { 
        "category": "some category",
        "hashtag": "#SomeHashtag",
        "description": "Some description"
      }
    ]
    
    To:
    {
      "SomeHashtag": {
        "description": "some description",
        "category": "some category"
      }
    }
    
    Returns:
        dict: The hashtag mapping dictionary
    """
    try:
        reader = get_dispocode_reader()
        hashtag_entries = reader.load_hashtag_dispocodes()
        
        if not hashtag_entries:
            logger.warning("No hashtag entries found in dispocodes")
            # Return fallback mapping if no dispocodes available
            return {
                "general_feedback": {
                    "description": "General feedback (fallback)",
                    "category": "General"
                }
            }
        
        # Convert to the required format
        hashtag_mapping = {}
        for entry in hashtag_entries:
            hashtag = entry.get('hashtag', '')
            category = entry.get('category', '')
            description = entry.get('description', '')
            
            # Remove the # sign from hashtag to use as key
            if hashtag.startswith('#'):
                hashtag_key = hashtag[1:]  # Remove the first character (#)
            else:
                hashtag_key = hashtag
            
            # Skip empty hashtags
            if not hashtag_key:
                continue
                
            hashtag_mapping[hashtag_key] = {
                "description": description,
                "category": category
            }
        
        logger.info(f"Loaded {len(hashtag_mapping)} hashtag mappings from dispocodes")
        return hashtag_mapping
        
    except Exception as e:
        logger.error(f"Error loading hashtag mapping from dispocodes: {e}")
        # Return fallback mapping on error
        return {
            "processing_error": {
                "description": "Error loading hashtag options",
                "category": "Error"
            }
        } 