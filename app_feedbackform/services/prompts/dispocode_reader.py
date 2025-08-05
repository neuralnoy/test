"""
Dispocode reader for loading and filtering dispocodes from local JSON file.
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any
from common_new.logger import get_logger

logger = get_logger("prompts")

class DispocodeReader:
    """Service for reading and filtering dispocodes from local JSON file."""
    
    def __init__(self):
        # Path to the dispocodes.json file in the project root
        self.project_root = Path(__file__).resolve().parent.parent.parent.parent
        self.json_path = self.project_root / "dispocodes.json"
    
    def load_hashtag_dispocodes(self) -> List[Dict[str, Any]]:
        """
        Load and filter dispocodes to get only hashtag entries.
        
        Input format (direct array):
        [
          {
            "id": "AC01",
            "category": "some category",
            "typeName": "hashtag",
            "typeValue": "#SomeHashtag",
            "hashtags": "",
            "description": "Some description"
          }
        ]
        
        Output format:
        [
          { 
            "category": "some category",
            "hashtag": "#SomeHashtag", # typeValue becomes hashtag
            "description": "Some description"
          }
        ]
        
        Returns:
            List[Dict[str, Any]]: List of filtered hashtag entries in output format
        """
        try:
            # Check if file exists
            if not self.json_path.exists():
                logger.warning(f"Dispocodes file not found at {self.json_path}")
                return []
            
            # Load the JSON file - it's already a direct array
            with open(self.json_path, 'r', encoding='utf-8') as f:
                dispocodes = json.load(f)
            
            # Filter for hashtag entries only (typeName == "hashtag")
            hashtag_entries = []
            for entry in dispocodes:
                if entry.get('typeName', '').lower() == 'hashtag':
                    # Transform to output format
                    output_entry = {
                        "category": entry.get('category', ''),
                        "hashtag": entry.get('typeValue', ''),
                        "description": entry.get('description', '')
                    }
                    hashtag_entries.append(output_entry)
            
            logger.info(f"Loaded {len(hashtag_entries)} hashtag entries from dispocodes.json")
            
            return hashtag_entries
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in dispocodes.json: {e}")
            return []
        except IOError as e:
            logger.error(f"Error reading dispocodes.json: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error loading dispocodes: {e}")
            return []

# Global instance
_dispocode_reader = DispocodeReader()

def get_dispocode_reader() -> DispocodeReader:
    """
    Get the global dispocode reader instance.
    
    Returns:
        DispocodeReader: The dispocode reader instance
    """
    return _dispocode_reader