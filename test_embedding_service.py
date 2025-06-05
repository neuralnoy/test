#!/usr/bin/env python3
"""
Simple test script for Azure Embedding Service.
Tests basic embedding creation without similarity calculations.
"""

import asyncio
import os
from dotenv import load_dotenv
from common_new.azure_embedding_service import AzureEmbeddingService
from common_new.logger import get_logger

# Load environment variables
load_dotenv()

# Setup logging
logger = get_logger("embedding_test")

async def test_embedding_service():
    """Test the Azure embedding service with sample texts."""
    
    print("=" * 60)
    print("Azure Embedding Service Test")
    print("=" * 60)
    
    # Sample texts to test
    test_texts = [
        "The quick brown fox jumps over the lazy dog.",
        "Machine learning is a subset of artificial intelligence.",
        "Python is a popular programming language for data science.",
        "Azure OpenAI provides powerful AI capabilities in the cloud."
    ]
    
    try:
        # Initialize the embedding service
        print("\n1. Initializing Azure Embedding Service...")
        service = AzureEmbeddingService(app_id="embedding_test")
        print(f"✓ Service initialized successfully")
        print(f"  - Endpoint: {service.azure_endpoint}")
        print(f"  - Model: {service.default_model}")
        print(f"  - API Version: {service.api_version}")
        
        # Test 1: Single text embedding
        print("\n2. Testing single text embedding...")
        single_text = test_texts[0]
        print(f"Text: '{single_text}'")
        
        embedding = await service.create_embedding(single_text)
        print(f"✓ Single embedding created successfully")
        print(f"  - Type: {type(embedding)}")
        print(f"  - Length: {len(embedding)} embeddings")
        print(f"  - Vector dimension: {len(embedding[0]) if embedding else 'N/A'}")
        print(f"  - First 5 values: {embedding[0][:5] if embedding and embedding[0] else 'N/A'}")
        
        # Test 2: Multiple texts embedding
        print("\n3. Testing multiple texts embedding...")
        print(f"Number of texts: {len(test_texts)}")
        for i, text in enumerate(test_texts):
            print(f"  {i+1}. '{text[:50]}{'...' if len(text) > 50 else ''}'")
        
        embeddings = await service.create_embedding(test_texts)
        print(f"✓ Multiple embeddings created successfully")
        print(f"  - Type: {type(embeddings)}")
        print(f"  - Number of embeddings: {len(embeddings)}")
        print(f"  - Vector dimension: {len(embeddings[0]) if embeddings else 'N/A'}")
        
        # Show sample from each embedding
        for i, emb in enumerate(embeddings[:2]):  # Show first 2 only
            print(f"  - Embedding {i+1} first 3 values: {emb[:3]}")
        
        # Test 3: Token estimation
        print("\n4. Testing token estimation...")
        for i, text in enumerate(test_texts[:2]):  # Test first 2 texts
            estimated_tokens = service._estimate_tokens(text, service.default_model)
            print(f"  Text {i+1}: {estimated_tokens} tokens")
        
        print("\n" + "=" * 60)
        print("✅ All tests completed successfully!")
        print("The Azure Embedding Service is working correctly.")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        logger.error(f"Embedding service test failed: {str(e)}", exc_info=True)
        return False

async def test_error_scenarios():
    """Test error scenarios to ensure proper error handling."""
    
    print("\n" + "=" * 60)
    print("Testing Error Scenarios")
    print("=" * 60)
    
    try:
        service = AzureEmbeddingService(app_id="embedding_test_errors")
        
        # Test with empty text
        print("\n1. Testing empty text...")
        try:
            await service.create_embedding("")
            print("✓ Empty text handled gracefully")
        except Exception as e:
            print(f"⚠️  Empty text error (expected): {str(e)[:100]}")
        
        # Test with very long text
        print("\n2. Testing very long text...")
        long_text = "This is a test. " * 1000  # Very long text
        try:
            estimated_tokens = service._estimate_tokens(long_text, service.default_model)
            print(f"✓ Long text token estimation: {estimated_tokens} tokens")
        except Exception as e:
            print(f"⚠️  Long text error: {str(e)[:100]}")
            
    except Exception as e:
        print(f"❌ Error scenario test failed: {str(e)}")

def check_environment():
    """Check if required environment variables are set."""
    
    print("Checking environment variables...")
    
    required_vars = [
        "APP_EMBEDDING_API_BASE",
        "COUNTER_APP_BASE_URL"
    ]
    
    optional_vars = [
        "APP_EMBEDDING_API_VERSION",
        "APP_EMBEDDING_ENGINE"
    ]
    
    missing_vars = []
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"✓ {var}: {value}")
        else:
            print(f"❌ {var}: Not set")
            missing_vars.append(var)
    
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            print(f"✓ {var}: {value}")
        else:
            print(f"⚠️  {var}: Not set (will use default)")
    
    if missing_vars:
        print(f"\n❌ Missing required environment variables: {', '.join(missing_vars)}")
        return False
    
    print("✓ Environment variables look good!")
    return True

async def main():
    """Main test function."""
    
    print("Starting Azure Embedding Service Tests...")
    
    # Check environment
    if not check_environment():
        print("\nPlease set the required environment variables and try again.")
        return
    
    # Run main tests
    success = await test_embedding_service()
    
    # Run error scenario tests
    await test_error_scenarios()
    
    if success:
        print("\n🎉 All tests passed! The embedding service is ready to use.")
    else:
        print("\n💥 Some tests failed. Please check the logs and configuration.")

if __name__ == "__main__":
    # Run the async test
    asyncio.run(main()) 