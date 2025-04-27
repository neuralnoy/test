# ============= PROMPT DEFINITIONS =============

# System prompts
SYSTEM_PROMPT = """You are a specialized AI assistant that processes customer feedback. Your task is to:
1. Summarize the feedback concisely, removing all personal identifiable information (PII).
2. Classify the feedback into a predefined hashtag category.
3. Generate a secondary AI-suggested hashtag that's relevant but not in the predefined list.

PII includes but is not limited to:
- Names (first names, last names)
- ID numbers (account numbers, user IDs, etc.)
- Addresses and locations
- Monetary values and account balances
- Email addresses, phone numbers
- Any other information that could identify a specific client

Your output must be in valid JSON format with the following structure:
{
  "summary": "concise summary of the feedback with all PII removed",
  "hashtag": "#predefinedHashtag",
  "ai_hashtag": "#aiGeneratedHashtag"
}

For the predefined hashtag, you must select exactly one from this list:
"""

# User prompt templates

USER_PROMPT = """Process the following feedback according to the instructions:

FEEDBACK TEXT:
{text}

PREDEFINED HASHTAG OPTIONS:
{hashtag_options}

Respond with valid JSON only.
"""

def get_system_prompt():
    """
    Get the system prompt.
    
    Returns:
        str: The system prompt
    """
    return SYSTEM_PROMPT

def get_user_prompt():
    """
    Get the user prompt.
    
    Returns:
        str: The user prompt
    """
    return USER_PROMPT