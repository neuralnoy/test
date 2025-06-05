#!/usr/bin/env python3
"""
Simple test script for Azure Embedding Service - Direct API test.
Tests basic embedding creation without token counter integration.
"""

import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI
import tiktoken

# Load environment variables
load_dotenv()

def test_direct_azure_embedding():
    """Test Azure OpenAI embeddings directly without the service wrapper."""
    
    print("=" * 60)
    print("Direct Azure OpenAI Embedding Test")
    print("=" * 60)
    
    # Check environment variables
    api_base = os.getenv("APP_EMBEDDING_API_BASE")
    api_version = os.getenv("APP_EMBEDDING_API_VERSION", "2024-02-01")
    model = os.getenv("APP_EMBEDDING_ENGINE", "text-embedding-3-large")
    
    print(f"API Base: {api_base}")
    print(f"API Version: {api_version}")
    print(f"Model: {model}")
    
    if not api_base:
        print("❌ APP_EMBEDDING_API_BASE not set!")
        return False
    
    try:
        # Initialize Azure credential and token provider
        print("\n1. Setting up Azure authentication...")
        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default"
        )
        print("✓ Azure authentication configured")
        
        # Initialize Azure OpenAI client
        print("\n2. Initializing Azure OpenAI client...")
        client = AzureOpenAI(
            api_version=api_version,
            azure_endpoint=api_base,
            azure_ad_token_provider=token_provider
        )
        print("✓ Azure OpenAI client initialized")
        
        # Test data
        test_texts = [
            "Hello, world!",
            "Machine learning is fascinating.",
            "Python programming is versatile."
        ]
        
        # Test single text embedding
        print(f"\n3. Testing single text embedding...")
        single_text = test_texts[0]
        print(f"Text: '{single_text}'")
        
        response = client.embeddings.create(
            model=model,
            input=single_text
        )
        
        embedding = response.data[0].embedding
        print(f"✓ Single embedding created successfully")
        print(f"  - Vector dimension: {len(embedding)}")
        print(f"  - First 5 values: {embedding[:5]}")
        print(f"  - Usage: {response.usage.prompt_tokens} tokens")
        
        # Test multiple texts
        print(f"\n4. Testing multiple texts embedding...")
        print(f"Number of texts: {len(test_texts)}")
        
        response = client.embeddings.create(
            model=model,
            input=test_texts
        )
        
        embeddings = [data.embedding for data in response.data]
        print(f"✓ Multiple embeddings created successfully")
        print(f"  - Number of embeddings: {len(embeddings)}")
        print(f"  - Vector dimension: {len(embeddings[0])}")
        print(f"  - Usage: {response.usage.prompt_tokens} tokens")
        
        # Test token counting
        print(f"\n5. Testing token estimation...")
        encoding = tiktoken.get_encoding("cl100k_base")
        for i, text in enumerate(test_texts):
            tokens = len(encoding.encode(text))
            print(f"  Text {i+1}: '{text}' = {tokens} tokens")
        
        print("\n" + "=" * 60)
        print("✅ Direct Azure OpenAI embedding test completed successfully!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        return False

def main():
    """Main test function."""
    
    print("Starting Direct Azure Embedding API Test...")
    print("This test bypasses the token counter service and tests Azure OpenAI directly.\n")
    
    success = test_direct_azure_embedding()
    
    if success:
        print("\n🎉 Direct API test passed! Azure embedding endpoint is working.")
        print("\nYou can now test the full service with: python test_embedding_service.py")
    else:
        print("\n💥 Direct API test failed. Please check your Azure configuration.")

if __name__ == "__main__":
    main() 