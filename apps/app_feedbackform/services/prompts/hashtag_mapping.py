"""
Hashtag mapping for the feedback form application.
This is a temporary generic mapping and will be replaced with actual business logic later.
"""

HASHTAG_MAPPING = {
    "product": {
        "description": "Feedback related to product features or functionality",
        "examples": ["The product is great", "I really like the new feature"]
    },
    "service": {
        "description": "Feedback related to customer service",
        "examples": ["Support was very helpful", "Quick response from the team"]
    },
    "usability": {
        "description": "Feedback related to usability and user experience",
        "examples": ["The interface is intuitive", "Hard to navigate the menu"]
    },
    "performance": {
        "description": "Feedback related to system performance",
        "examples": ["App is fast", "Website is slow to load"]
    },
    "suggestion": {
        "description": "Suggestions for improvement",
        "examples": ["Would be nice to have dark mode", "Please add export functionality"]
    },
    "bug": {
        "description": "Reports of bugs or issues",
        "examples": ["App crashes when I try to save", "Can't upload images"]
    },
    "positive": {
        "description": "General positive feedback",
        "examples": ["Love this app!", "Great experience"]
    },
    "negative": {
        "description": "General negative feedback",
        "examples": ["Disappointed with the service", "Not what I expected"]
    }
}

def get_hashtag_mapping():
    """
    Get the hashtag mapping dictionary.
    
    Returns:
        dict: The hashtag mapping dictionary
    """
    return HASHTAG_MAPPING 