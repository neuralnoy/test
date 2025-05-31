#!/usr/bin/env python3

import os
from unittest.mock import patch

def debug_base_url():
    print("=== DEBUG: Environment Variable Behavior ===")
    
    # Test 1: Normal environment
    print(f"Current COUNTER_APP_BASE_URL: {os.getenv('COUNTER_APP_BASE_URL')}")
    print(f"str(os.getenv('COUNTER_APP_BASE_URL')): {str(os.getenv('COUNTER_APP_BASE_URL'))}")
    
    # Test 2: Clear environment
    with patch.dict('os.environ', {}, clear=True):
        print(f"After clear - os.getenv('COUNTER_APP_BASE_URL'): {os.getenv('COUNTER_APP_BASE_URL')}")
        print(f"After clear - str(os.getenv('COUNTER_APP_BASE_URL')): {str(os.getenv('COUNTER_APP_BASE_URL'))}")
        
        # Test module behavior
        import importlib
        from common_new import token_client
        importlib.reload(token_client)
        
        print(f"After reload - token_client.BASE_URL: {token_client.BASE_URL}")
        print(f"After reload - type: {type(token_client.BASE_URL)}")
        
        client = token_client.TokenClient(app_id="test_app")
        print(f"Client base_url: {client.base_url}")
        print(f"Client base_url type: {type(client.base_url)}")

if __name__ == "__main__":
    debug_base_url() 