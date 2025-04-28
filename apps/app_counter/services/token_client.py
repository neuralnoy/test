import aiohttp
import asyncio
from typing import Dict, Any, Optional, Tuple
from common.logger import get_logger

logger = get_logger("token_client")

class TokenClient:
    """
    Client for interacting with the token counter service.
    Applications can use this to lock tokens, report usage, and release tokens.
    """
    def __init__(self, app_id: str, base_url: str = "http://localhost:8001"):
        """
        Initialize the token client.
        
        Args:
            app_id: The ID of the application using this client
            base_url: The base URL of the token counter service
        """
        self.app_id = app_id
        self.base_url = base_url.rstrip("/")
    
    async def lock_tokens(self, token_count: int) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Lock tokens for usage.
        
        Args:
            token_count: The number of tokens to lock
            
        Returns:
            Tuple of (allowed, request_id, error_message)
        """
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}/lock"
                data = {
                    "app_id": self.app_id,
                    "token_count": token_count
                }
                async with session.post(url, json=data) as response:
                    response_data = await response.json()
                    
                    if response.status == 200 and response_data.get("allowed", False):
                        return True, response_data.get("request_id"), None
                    else:
                        return False, None, response_data.get("message", "Unknown error")
            except Exception as e:
                logger.error(f"Error locking tokens: {str(e)}")
                return False, None, f"Client error: {str(e)}"
    
    async def report_usage(self, request_id: str, prompt_tokens: int, completion_tokens: int) -> bool:
        """
        Report actual token usage after an API call.
        
        Args:
            request_id: The request ID returned when tokens were locked
            prompt_tokens: Number of tokens used in the prompt
            completion_tokens: Number of tokens used in the completion
            
        Returns:
            Boolean indicating if the report was successful
        """
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}/report"
                data = {
                    "app_id": self.app_id,
                    "request_id": request_id,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens
                }
                async with session.post(url, json=data) as response:
                    return response.status == 200
            except Exception as e:
                logger.error(f"Error reporting token usage: {str(e)}")
                return False
    
    async def release_tokens(self, request_id: str) -> bool:
        """
        Release locked tokens that won't be used.
        
        Args:
            request_id: The request ID returned when tokens were locked
            
        Returns:
            Boolean indicating if the release was successful
        """
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}/release"
                data = {
                    "app_id": self.app_id,
                    "request_id": request_id
                }
                async with session.post(url, json=data) as response:
                    return response.status == 200
            except Exception as e:
                logger.error(f"Error releasing tokens: {str(e)}")
                return False
    
    async def get_status(self) -> Optional[Dict[str, Any]]:
        """
        Get the current status of the token counter.
        
        Returns:
            Dict with available tokens, used tokens, locked tokens, and seconds until reset
        """
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}/status"
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    return None
            except Exception as e:
                logger.error(f"Error getting token counter status: {str(e)}")
                return None 