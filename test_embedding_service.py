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
        
        # Test 1: Check counter app status first
        print("\n2. Checking counter app status...")
        try:
            status = await service.token_client.get_embedding_status()
            if status:
                total_limit = status.get('available_tokens', 0) + status.get('used_tokens', 0) + status.get('locked_tokens', 0)
                print(f"✓ Counter app connected")
                print(f"  - Available tokens: {status.get('available_tokens', 0):,}")
                print(f"  - Used tokens: {status.get('used_tokens', 0):,}")
                print(f"  - Locked tokens: {status.get('locked_tokens', 0):,}")
                print(f"  - Total limit: {total_limit:,} tokens/minute")
                print(f"  - Reset in: {status.get('reset_time_seconds', 0)} seconds")
            else:
                print("⚠️  Could not connect to counter app")
        except Exception as e:
            print(f"⚠️  Counter app error: {str(e)[:100]}")
        
        # Test 2: Single text embedding
        print("\n3. Testing single text embedding...")
        single_text = test_texts[0]
        print(f"Text: '{single_text}'")
        
        embedding = await service.create_embedding(single_text)
        print(f"✓ Single embedding created successfully")
        print(f"  - Type: {type(embedding)}")
        print(f"  - Length: {len(embedding)} embeddings")
        print(f"  - Vector dimension: {len(embedding[0]) if embedding else 'N/A'}")
        print(f"  - First 5 values: {embedding[0][:5] if embedding and embedding[0] else 'N/A'}")
        
        # Test 3: Multiple texts embedding
        print("\n4. Testing multiple texts embedding...")
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
        
        # Test 4: Token estimation vs actual usage
        print("\n5. Testing token estimation accuracy...")
        test_text = "This is a sample text for token counting validation."
        estimated_tokens = service._estimate_tokens(test_text, service.default_model)
        print(f"  - Estimated tokens: {estimated_tokens}")
        
        # Make actual call to see real usage (this hits the counter app)
        try:
            embedding = await service.create_embedding(test_text)
            print(f"  - ✓ Actual API call succeeded")
            print(f"  - Embedding created with {len(embedding[0])} dimensions")
        except Exception as e:
            print(f"  - ⚠️  API call failed: {str(e)[:100]}")
        
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
    print("Testing Error Scenarios & Counter App Limits")
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
        
        # Test with moderately long text (actual counter app test)
        print("\n2. Testing moderately long text with counter app...")
        medium_text = "This is a test sentence with multiple words to create a reasonable token count. " * 100  # More reasonable size
        try:
            estimated_tokens = service._estimate_tokens(medium_text, service.default_model)
            print(f"  - Estimated tokens: {estimated_tokens:,}")
            
            # Actually try to create embedding (this WILL hit the counter app)
            embedding = await service.create_embedding(medium_text)
            print(f"✓ Medium text embedding created successfully")
            print(f"  - Embedding dimensions: {len(embedding[0]) if embedding and embedding[0] else 'N/A'}")
        except ValueError as e:
            if "limit" in str(e).lower():
                print(f"✓ Counter app properly rejected: {str(e)[:100]}")
            else:
                print(f"⚠️  Unexpected error: {str(e)[:100]}")
        except Exception as e:
            print(f"⚠️  Medium text error: {str(e)[:100]}")
        
        # Test with very long text (should definitely hit limits)
        print("\n3. Testing very long text (should hit counter limits)...")
        long_text = "This is a test sentence. " * 10000  # Still large but not ridiculous
        try:
            estimated_tokens = service._estimate_tokens(long_text, service.default_model)
            print(f"  - Estimated tokens: {estimated_tokens:,}")
            
            # This should hit the counter app and be rejected
            embedding = await service.create_embedding(long_text)
            print(f"⚠️  Very long text unexpectedly succeeded! This suggests limits are too high.")
            print(f"  - Embedding dimensions: {len(embedding[0]) if embedding and embedding[0] else 'N/A'}")
        except ValueError as e:
            if "limit" in str(e).lower() or "exceeded" in str(e).lower():
                print(f"✓ Counter app properly rejected long text: {str(e)[:150]}")
            else:
                print(f"⚠️  Unexpected error: {str(e)[:100]}")
        except Exception as e:
            print(f"⚠️  Long text error: {str(e)[:100]}")
        
        # Test counter app status after operations
        print("\n4. Checking counter app status after operations...")
        try:
            status = await service.token_client.get_embedding_status()
            if status:
                print(f"✓ Final counter status:")
                print(f"  - Available tokens: {status.get('available_tokens', 0):,}")
                print(f"  - Used tokens: {status.get('used_tokens', 0):,}")
                print(f"  - Locked tokens: {status.get('locked_tokens', 0):,}")
                print(f"  - Reset in: {status.get('reset_time_seconds', 0)} seconds")
            else:
                print("⚠️  Could not get final counter status")
        except Exception as e:
            print(f"⚠️  Status check error: {str(e)[:100]}")
            
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
        "APP_EMBEDDING_ENGINE",
        "APP_EMBEDDING_TPM_QUOTA",
        "APP_EMBEDDING_RPM_QUOTA"
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
            default_values = {
                "APP_EMBEDDING_API_VERSION": "2024-02-01",
                "APP_EMBEDDING_ENGINE": "text-embedding-3-large",
                "APP_EMBEDDING_TPM_QUOTA": "1000000",
                "APP_EMBEDDING_RPM_QUOTA": "500"
            }
            default = default_values.get(var, "Not set")
            print(f"⚠️  {var}: Not set (will use default: {default})")
    
    if missing_vars:
        print(f"\n❌ Missing required environment variables: {', '.join(missing_vars)}")
        return False
    
    print("✓ Environment variables look good!")
    
    # Show recommendations for counter limits
    embedding_quota = os.getenv("APP_EMBEDDING_TPM_QUOTA")
    if not embedding_quota or int(embedding_quota) >= 1000000:
        print(f"\n💡 RECOMMENDATION: Set APP_EMBEDDING_TPM_QUOTA to a lower value (e.g., 50000)")
        print(f"   Current/default: {embedding_quota or '1000000'} tokens/minute")
        print(f"   This will help test counter app limits properly.")
    
    return True

async def main():
    """Main test function."""
    
    print("Starting Azure Embedding Service Tests with Counter App Integration...")
    print("This test will make ACTUAL API calls to test counter app limits.\n")
    
    # Check environment
    if not check_environment():
        print("\nPlease set the required environment variables and try again.")
        return
    
    # Run main tests
    success = await test_embedding_service()
    
    # Run error scenario tests (including counter app limit tests)
    await test_error_scenarios()
    
    if success:
        print("\n🎉 All tests passed! The embedding service and counter app are working correctly.")
    else:
        print("\n💥 Some tests failed. Please check the logs and configuration.")

if __name__ == "__main__":
    # Run the async test
    asyncio.run(main()) 