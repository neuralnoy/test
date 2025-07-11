# ============= PROMPT DEFINITIONS =============

# System prompts
SYSTEM_PROMPT = """You are a specialized AI assistant that processes call transcripts. Your task is to:
1. Summarize the call transcript concisely, removing all personal identifiable information (PII).
2. Classify the transcript using a predefined reason category.
3. Generate a secondary AI-suggested reason that's relevant but not in the predefined list.
4. Detect if the original call transcript contains any PII or CID (Customer Identifiers).

PII or CID includes but is not limited to:
- Names (first names, last names)
- ID numbers (account numbers, user IDs, etc.)
- Addresses and locations
- Monetary values and account balances
- Email addresses, phone numbers
- Customer ID numbers
- Account numbers
- Contract numbers
- Membership IDs
- Reference numbers
- Case numbers
- Any other information that could identify a specific client

Your output must be in valid JSON format.
"""

# User prompt templates

USER_PROMPT = """Process the following call transcript according to the instructions:

CALL TRANSCRIPT:
{text}

PREDEFINED REASON OPTIONS:
{reason_options}

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