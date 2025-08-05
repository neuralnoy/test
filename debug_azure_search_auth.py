#!/usr/bin/env python3
"""
Debug script to help diagnose Azure Search authentication issues.
This script will help identify whether the issue is with token acquisition or permissions.
"""
import asyncio
import os
import sys
import logging
from dotenv import load_dotenv

# Add the current directory to path to import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from azure.identity import DefaultAzureCredential
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from common_new.azure_search_service import AzureSearchCredential
from common_new.logger import get_logger

# Load environment variables
load_dotenv()

# Set up logging to see debug messages
logging.basicConfig(level=logging.DEBUG)
logger = get_logger("debug_search_auth")

async def debug_authentication():
    """Debug Azure Search authentication step by step."""
    
    print("=" * 80)
    print("Azure Search Authentication Debug")
    print("=" * 80)
    
    # 1. Check environment variables
    search_endpoint = os.getenv("APP_SEARCH_ENDPOINT")
    if not search_endpoint:
        print("❌ APP_SEARCH_ENDPOINT environment variable is not set")
        return False
    else:
        print(f"✅ Search Endpoint: {search_endpoint}")
    
    # 2. Test basic credential acquisition
    print("\n🔍 Testing DefaultAzureCredential...")
    try:
        base_credential = DefaultAzureCredential()
        print("✅ DefaultAzureCredential created successfully")
    except Exception as e:
        print(f"❌ Failed to create DefaultAzureCredential: {e}")
        return False
    
    # 3. Test token acquisition with Azure Search scope
    print("\n🔍 Testing token acquisition with Azure Search scope...")
    try:
        search_credential = AzureSearchCredential(base_credential)
        token = search_credential.get_token()
        print(f"✅ Successfully acquired token for Azure Search scope")
        print(f"   Token expires at: {token.expires_on}")
        
        # Check if token looks valid (basic validation)
        if hasattr(token, 'token') and len(token.token) > 10:
            print(f"   Token starts with: {token.token[:20]}...")
        else:
            print("⚠️  Token seems to be empty or invalid")
            
    except Exception as e:
        print(f"❌ Failed to acquire token: {e}")
        print(f"   Exception type: {type(e).__name__}")
        return False
    
    # 4. Test Azure CLI authentication (alternative method)
    print("\n🔍 Testing if Azure CLI is logged in...")
    try:
        from azure.identity import AzureCliCredential
        cli_credential = AzureCliCredential()
        cli_token = cli_credential.get_token("https://search.azure.com/.default")
        print("✅ Azure CLI is logged in and can get Azure Search tokens")
        print(f"   CLI token expires at: {cli_token.expires_on}")
    except Exception as e:
        print(f"⚠️  Azure CLI authentication failed: {e}")
        print("   You might need to run 'az login' first")
    
    # 5. Manual Azure Search API test
    print("\n🔍 Testing direct Azure Search API call...")
    try:
        import aiohttp
        
        # Get a fresh token
        token = search_credential.get_token()
        
        headers = {
            "Authorization": f"Bearer {token.token}",
            "Content-Type": "application/json",
            "api-version": "2023-11-01"
        }
        
        # Try to list indexes (minimal permission required)
        async with aiohttp.ClientSession() as session:
            url = f"{search_endpoint}/indexes"
            
            print(f"   Making GET request to: {url}")
            print(f"   Using headers: {{'Authorization': 'Bearer ...', 'Content-Type': 'application/json', 'api-version': '2023-11-01'}}")
            
            async with session.get(url, headers=headers) as response:
                print(f"   Response status: {response.status}")
                
                if response.status == 200:
                    print("✅ Direct API call succeeded!")
                    data = await response.json()
                    indexes = data.get('value', [])
                    print(f"   Found {len(indexes)} indexes")
                    for idx in indexes:
                        print(f"     - {idx.get('name', 'Unknown')}")
                        
                elif response.status == 403:
                    print("❌ Direct API call returned 403 Forbidden")
                    error_text = await response.text()
                    print(f"   Error response: {error_text}")
                    print("\n🔧 POSSIBLE SOLUTIONS:")
                    print("   1. Check if your Azure identity has the proper roles assigned:")
                    print("      - Search Service Contributor (for index management)")
                    print("      - Search Index Data Contributor (for document operations)")
                    print("      - Search Index Data Reader (for read operations)")
                    print("   2. Make sure you're signed in to the correct Azure tenant")
                    print("   3. Verify the search service allows your IP address")
                    
                elif response.status == 401:
                    print("❌ Direct API call returned 401 Unauthorized")
                    print("   This suggests a token/authentication issue")
                    
                else:
                    print(f"❌ Direct API call returned unexpected status: {response.status}")
                    error_text = await response.text()
                    print(f"   Error response: {error_text}")
                    
    except Exception as e:
        print(f"❌ Direct API test failed: {e}")
        print(f"   Exception type: {type(e).__name__}")
    
    print("\n" + "=" * 80)
    print("Debug complete. Check the output above for issues.")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(debug_authentication())