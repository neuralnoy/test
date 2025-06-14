import os
import aiohttp
from typing import Dict, Any, Optional, Tuple
from common_new.logger import get_logger
import time
from dotenv import load_dotenv

load_dotenv()

logger = get_logger("common")

BASE_URL = str(os.getenv("COUNTER_APP_BASE_URL"))

class TokenClient:
    """
    Client for interacting with the token counter service.
    Applications can use this to lock tokens, report usage, and release tokens.
    """
    def __init__(self, app_id: str, base_url: str = BASE_URL):
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
                
                # Extract rate_request_id from request_id if it's in the format "token_id:rate_id"
                if ":" in request_id:
                    token_id, rate_id = request_id.split(":", 1)
                    data["request_id"] = token_id
                    data["rate_request_id"] = rate_id
                
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
                
                # Extract rate_request_id from request_id if it's in the format "token_id:rate_id"
                if ":" in request_id:
                    token_id, rate_id = request_id.split(":", 1)
                    data["request_id"] = token_id
                    data["rate_request_id"] = rate_id
                
                async with session.post(url, json=data) as response:
                    return response.status == 200
            except Exception as e:
                logger.error(f"Error releasing tokens: {str(e)}")
                return False
    
    async def lock_embedding_tokens(self, token_count: int) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Lock embedding tokens for usage.
        
        Args:
            token_count: The number of embedding tokens to lock
            
        Returns:
            Tuple of (allowed, request_id, error_message)
        """
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}/embedding/lock"
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
                logger.error(f"Error locking embedding tokens: {str(e)}")
                return False, None, f"Client error: {str(e)}"
    
    async def report_embedding_usage(self, request_id: str, prompt_tokens: int) -> bool:
        """
        Report actual embedding token usage after an API call.
        
        Args:
            request_id: The request ID returned when tokens were locked
            prompt_tokens: Number of tokens used for embedding
            
        Returns:
            Boolean indicating if the report was successful
        """
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}/embedding/report"
                data = {
                    "app_id": self.app_id,
                    "request_id": request_id,
                    "prompt_tokens": prompt_tokens
                }
                
                async with session.post(url, json=data) as response:
                    return response.status == 200
            except Exception as e:
                logger.error(f"Error reporting embedding token usage: {str(e)}")
                return False
    
    async def release_embedding_tokens(self, request_id: str) -> bool:
        """
        Release locked embedding tokens that won't be used.
        
        Args:
            request_id: The request ID returned when tokens were locked
            
        Returns:
            Boolean indicating if the release was successful
        """
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}/embedding/release"
                data = {
                    "app_id": self.app_id,
                    "request_id": request_id
                }
                
                async with session.post(url, json=data) as response:
                    return response.status == 200
            except Exception as e:
                logger.error(f"Error releasing embedding tokens: {str(e)}")
                return False

    async def get_status(self) -> Optional[Dict[str, Any]]:
        """
        Get the current status of the token counter.
        
        Returns:
            Dict with available tokens, used tokens, locked tokens, available requests, and seconds until reset
        """
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}/status"               
                async with session.get(url) as response:
                    if response.status == 200:
                        status_data = await response.json()
                        
                        # Add client information to help with debugging
                        status_data["client_app_id"] = self.app_id
                        status_data["client_timestamp"] = time.time()
                        
                        # Calculate the effective time until reset - the minimum of token and rate reset times
                        token_reset = status_data.get("reset_time_seconds", 0)
                        
                        # Log the status information for debugging
                        logger.debug(f"STATUS: Retrieved for {self.app_id}: token_avail={status_data.get('available_tokens')}, req_avail={status_data.get('available_requests')}, reset_in={token_reset}s")
                        
                        return status_data
                    else:
                        logger.warning(f"Failed to get status: HTTP {response.status}")
                        return None
            except Exception as e:
                logger.error(f"Error getting token counter status: {str(e)}")
                return None
    
    async def get_embedding_status(self) -> Optional[Dict[str, Any]]:
        """
        Get the current status of the embedding token counter.
        
        Returns:
            Dict with available embedding tokens, used tokens, locked tokens, and seconds until reset
        """
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}/embedding/status"               
                async with session.get(url) as response:
                    if response.status == 200:
                        status_data = await response.json()
                        
                        # Add client information to help with debugging
                        status_data["client_app_id"] = self.app_id
                        status_data["client_timestamp"] = time.time()
                        
                        # Log the status information for debugging
                        logger.debug(f"EMBEDDING STATUS: Retrieved for {self.app_id}: embedding_avail={status_data.get('available_tokens')}, reset_in={status_data.get('reset_time_seconds', 0)}s")
                        
                        return status_data
                    else:
                        logger.warning(f"Failed to get embedding status: HTTP {response.status}")
                        return None
            except Exception as e:
                logger.error(f"Error getting embedding counter status: {str(e)}")
                return None

    # Whisper rate limiting methods
    async def lock_whisper_rate(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Lock a Whisper API rate slot.
        
        Returns:
            Tuple of (allowed, request_id, error_message)
        """
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}/whisper/lock"
                data = {
                    "app_id": self.app_id
                }                
                async with session.post(url, json=data) as response:
                    response_data = await response.json()
                    
                    if response.status == 200 and response_data.get("allowed", False):
                        return True, response_data.get("request_id"), None
                    else:
                        return False, None, response_data.get("message", "Whisper rate limit exceeded")
            except Exception as e:
                logger.error(f"Error locking Whisper rate slot: {str(e)}")
                return False, None, f"Client error: {str(e)}"
    
    async def report_whisper_usage(self, request_id: str) -> bool:
        """
        Report that a Whisper API request was completed.
        
        Args:
            request_id: The request ID returned when the rate slot was locked
            
        Returns:
            Boolean indicating if the report was successful
        """
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}/whisper/report"
                data = {
                    "app_id": self.app_id,
                    "request_id": request_id
                }
                
                async with session.post(url, json=data) as response:
                    return response.status == 200
            except Exception as e:
                logger.error(f"Error reporting Whisper usage: {str(e)}")
                return False
    
    async def release_whisper_rate(self, request_id: str) -> bool:
        """
        Release a locked Whisper rate slot that won't be used.
        
        Args:
            request_id: The request ID returned when the rate slot was locked
            
        Returns:
            Boolean indicating if the release was successful
        """
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}/whisper/release"
                data = {
                    "app_id": self.app_id,
                    "request_id": request_id
                }
                
                async with session.post(url, json=data) as response:
                    return response.status == 200
            except Exception as e:
                logger.error(f"Error releasing Whisper rate slot: {str(e)}")
                return False

    async def get_whisper_status(self) -> Optional[Dict[str, Any]]:
        """
        Get the current status of the Whisper rate counter.
        
        Returns:
            Dict with available requests, used requests, locked requests, and seconds until reset
        """
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}/whisper/status"               
                async with session.get(url) as response:
                    if response.status == 200:
                        status_data = await response.json()
                        
                        # Add client information to help with debugging
                        status_data["client_app_id"] = self.app_id
                        status_data["client_timestamp"] = time.time()
                        
                        # Log the status information for debugging
                        logger.debug(f"WHISPER STATUS: Retrieved for {self.app_id}: req_avail={status_data.get('available_requests')}, reset_in={status_data.get('reset_time_seconds', 0)}s")
                        
                        return status_data
                    else:
                        logger.warning(f"Failed to get Whisper status: HTTP {response.status}")
                        return None
            except Exception as e:
                logger.error(f"Error getting Whisper counter status: {str(e)}")
                return None 