"""
Hashtag mapping for the feedback form application.
This is a temporary generic mapping and will be replaced with actual business logic later.
"""

HASHTAG_MAPPING = {
    "product": {
        "description": "Feedback related to product features or functionality",
        "category": "A"
    },
    "service": {
        "description": "Feedback related to customer service",
        "category": "B"
    },
    "usability": {
        "description": "Feedback related to usability and user experience",
        "category": "C"
    },
    "performance": {
        "description": "Feedback related to system performance",
        "category": "A"
    },
    "suggestion": {
        "description": "Suggestions for improvement",
        "category": "B"
    },
    "bug": {
        "description": "Reports of bugs or issues",
        "category": "C"
    },
    "positive": {
        "description": "General positive feedback",
        "category": "A"
    },
    "negative": {
        "description": "General negative feedback",
        "category": "B"
    }
}

def get_hashtag_mapping():
    """
    Get the hashtag mapping dictionary.
    
    Returns:
        dict: The hashtag mapping dictionary
    """
    return HASHTAG_MAPPING 