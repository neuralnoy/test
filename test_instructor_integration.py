#!/usr/bin/env python3
"""
Test script to verify Instructor integration with Azure OpenAI service.
This is a standalone test that can be run to validate the integration.
"""

import asyncio
import sys
import os
from dotenv import load_dotenv

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv()

from app_feedbackform.models.schemas import FeedbackProcessingResponse
from app_reasoner.models.schemas import CallProcessingResponse
from common_new.azure_openai_service import AzureOpenAIService

async def test_structured_completion():
    """Test the structured completion functionality."""
    
    # Check if we have the required environment variables
    required_vars = ["APP_OPENAI_API_VERSION", "APP_OPENAI_API_BASE"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {missing_vars}")
        print("Please set these in your .env file or environment.")
        return False
    
    try:
        # Initialize the service
        print("🔧 Initializing Azure OpenAI service with Instructor...")
        ai_service = AzureOpenAIService(app_id="test_instructor")
        
        # Test 1: Feedback processing
        print("\n📝 Testing feedback processing with structured validation...")
        
        test_feedback = "The customer service was excellent, but the wait time was too long. My account number is 12345."
        
        messages = [
            {
                "role": "system", 
                "content": """You are a specialized AI assistant that processes customer feedback. Your task is to:
1. Summarize the feedback concisely, removing all personal identifiable information (PII).
2. Classify the feedback into a predefined hashtag category.
3. Generate a secondary AI-suggested hashtag that's relevant but not in the predefined list.
4. Detect if the original feedback text contains any PII or CID (Customer Identifiers).

For the predefined hashtag, select from: #service, #wait_time, #quality, #staff"""
            },
            {
                "role": "user",
                "content": f"Process this feedback: {test_feedback}"
            }
        ]
        
        feedback_response = await ai_service.structured_completion(
            response_model=FeedbackProcessingResponse,
            messages=messages,
            temperature=0.0,
            max_retries=2
        )
        
        print(f"✅ Feedback processing successful!")
        print(f"   Summary: {feedback_response.summary}")
        print(f"   Hashtag: {feedback_response.hashtag}")
        print(f"   AI Hashtag: {feedback_response.ai_hashtag}")
        print(f"   Contains PII/CID: {feedback_response.contains_pii_or_cid}")
        
        # Test 2: Call transcript processing
        print("\n📞 Testing call transcript processing with structured validation...")
        
        test_call = "Customer called about billing issue. They mentioned their contract number ABC123 and wanted to understand charges."
        
        messages = [
            {
                "role": "system",
                "content": """You are a specialized AI assistant that processes call transcripts. Your task is to:
1. Summarize the call transcript concisely, removing all personal identifiable information (PII).
2. Classify the transcript using a predefined reason category.
3. Generate a secondary AI-suggested reason that's relevant but not in the predefined list.
4. Detect if the original call transcript contains any PII or CID (Customer Identifiers).

For the predefined reason, select from: #logical, #empirical, #billing, #support"""
            },
            {
                "role": "user",
                "content": f"Process this call transcript: {test_call}"
            }
        ]
        
        call_response = await ai_service.structured_completion(
            response_model=CallProcessingResponse,
            messages=messages,
            temperature=0.0,
            max_retries=2
        )
        
        print(f"✅ Call processing successful!")
        print(f"   Summary: {call_response.summary}")
        print(f"   Reason: {call_response.reason}")
        print(f"   AI Reason: {call_response.ai_reason}")
        print(f"   Contains PII/CID: {call_response.contains_pii_or_cid}")
        
        print("\n🎉 All tests passed! Instructor integration is working correctly.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_structured_completion())
    sys.exit(0 if success else 1) 