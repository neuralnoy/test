"""
Reason mapping for the reasoner application.
This is a temporary generic mapping and will be replaced with actual business logic later.
"""

REASON_MAPPING = {
    "logical": {
        "description": "Reason based on logical reasoning and deduction",
        "examples": ["This follows from the given premises", "The conclusion is logically sound"]
    },
    "empirical": {
        "description": "Reason based on empirical evidence or observation",
        "examples": ["The data shows this trend", "Based on experimental results"]
    },
    "theoretical": {
        "description": "Reason based on theoretical models or frameworks",
        "examples": ["According to the theory", "The model predicts this outcome"]
    },
    "analogical": {
        "description": "Reason based on analogies or comparisons",
        "examples": ["Similar to what happens in this case", "By comparison with a known system"]
    },
    "causal": {
        "description": "Reason based on cause and effect relationships",
        "examples": ["This causes that to happen", "The effect is a result of this cause"]
    },
    "probabilistic": {
        "description": "Reason based on probability or statistical inference",
        "examples": ["There's a high likelihood", "Statistically speaking"]
    },
    "authoritative": {
        "description": "Reason based on expert opinion or authority",
        "examples": ["According to experts", "Research indicates"]
    },
    "intuitive": {
        "description": "Reason based on intuition or common sense",
        "examples": ["It seems obvious that", "Intuitively, this makes sense"]
    }
}

def get_reason_mapping():
    """
    Get the reason mapping dictionary.
    
    Returns:
        dict: The reason mapping dictionary
    """
    return REASON_MAPPING 