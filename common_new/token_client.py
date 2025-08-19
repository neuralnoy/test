import os
import aiohttp
from typing import Dict, Any, Optional, Tuple
from common_new.logger import get_logger
import time
import asyncio
from dotenv import load_dotenv
from azure.identity.aio import DefaultAzureCredential

load_dotenv()

logger = get_logger("common")

BASE_URL = str(os.getenv("APP_COUNTER_APP_BASE_URL"))

# Azure authentication configuration for Counter API
COUNTER_API_SCOPE = os.getenv("APP_COUNTER_API_SCOPE")
# For backwards compatibility and optional UAMI specification
COUNTER_API_CLIENT_ID = os.getenv("APP_COUNTER_API_CLIENT_ID")


class TokenClient:
    """
    Client for interacting with the token counter service.
    Applications can use this to lock tokens, report usage, and release tokens.
    Includes timeout handling for long-running operations.
    """
    def __init__(self, app_id: str, base_url: str = BASE_URL, timeout_seconds: int = 1800):
        """
        Initialize the token client.
        
        Args:
            app_id: The ID of the application using this client
            base_url: The base URL of the token counter service
            timeout_seconds: Timeout for HTTP requests in seconds (default: 30 minutes for long operations)
        """

        self.app_id = app_id
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._credential = None
        
        # Use DefaultAzureCredential for authentication (supports UAMI, Service Principal, etc.)
        # This aligns with other Azure services in the codebase
        try:
            # If a specific client ID is provided, use it for UAMI
            if COUNTER_API_CLIENT_ID:
                self._credential = DefaultAzureCredential(
                    managed_identity_client_id=COUNTER_API_CLIENT_ID,
                    retry_total=3,
                    retry_backoff_factor=1
                )
                logger.info(f"Initialized DefaultAzureCredential with UAMI client ID: {COUNTER_API_CLIENT_ID}")
            else:
                self._credential = DefaultAzureCredential(
                    retry_total=3,
                    retry_backoff_factor=1
                )
                logger.info("Initialized DefaultAzureCredential with default authentication chain")
        except Exception as e:
            logger.warning(f"Failed to initialize Azure credentials: {e}. Will make unauthenticated requests.")
            self._credential = None
       
    async def _get_auth_header(self) -> Dict[str, str]:
        """Gets the Authorization header if authentication is configured."""
        if not self._credential or not COUNTER_API_SCOPE:
            return {}
        
        try:
            token = await self._credential.get_token(COUNTER_API_SCOPE)
            return {"Authorization": f"Bearer {token.token}"}
        except Exception as e:
            logger.error(f"Failed to acquire token for scope {COUNTER_API_SCOPE} using DefaultAzureCredential: {e}")
            return {}

    async def _make_request_with_retry(self, method: str, url: str, data: Optional[Dict] = None,
                                       max_retries: int = 3) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Make HTTP request with retry logic for timeout and connection errors.
        
        Args:
            method: HTTP method ('GET' or 'POST')
            url: Request URL
            data: Request data for POST requests
            max_retries: Maximum number of retry attempts
            
        Returns:
            Tuple[bool, Optional[Dict], Optional[str]]: (success, response_data, error_message)
        """
        last_exception = None
        
        headers = await self._get_auth_header()
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    if method.upper() == 'GET':
                        async with session.get(url, headers=headers) as response:
                            if response.status == 200:
                                response_data = await response.json()
                                return True, response_data, None
                            else:
                                error_data = await response.json() if response.content_type == 'application/json' else {}
                                return False, error_data, error_data.get("message", f"HTTP {response.status}")
                    else:  # POST
                        async with session.post(url, json=data, headers=headers) as response:
                            response_data = await response.json()
                            if response.status == 200:
                                return True, response_data, None
                            else:
                                return False, response_data, response_data.get("message", f"HTTP {response.status}")
                                
            except (aiohttp.ServerTimeoutError, asyncio.TimeoutError) as e:
                last_exception = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Request timeout (attempt {attempt + 1}/{max_retries}): {url}. Retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Request timed out after {max_retries} attempts: {url}")
                    return False, None, f"Request timeout after {max_retries} attempts: {str(e)}"
                    
            except (aiohttp.ClientError, aiohttp.ClientConnectionError) as e:
                last_exception = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Connection error (attempt {attempt + 1}/{max_retries}): {url}. Retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Connection failed after {max_retries} attempts: {url}")
                    return False, None, f"Connection error after {max_retries} attempts: {str(e)}"
                    
            except Exception as e:
                last_exception = e
                logger.error(f"Unexpected error in request: {str(e)}")
                return False, None, f"Client error: {str(e)}"
        
        # Should not reach here, but just in case
        return False, None, f"Request failed: {str(last_exception)}"
    
    async def lock_tokens(self, token_count: int) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Lock tokens for usage.
        
        Args:
            token_count: The number of tokens to lock
            
        Returns:
            Tuple of (allowed, request_id, error_message)
        """
        url = f"{self.base_url}/lock"
        data = {
            "app_id": self.app_id,
            "token_count": token_count
        }
        
        success, response_data, error_message = await self._make_request_with_retry('POST', url, data)
        
        if success and response_data and response_data.get("allowed", False):
            return True, response_data.get("request_id"), None
        else:
            return False, None, error_message or response_data.get("message", "Unknown error") if response_data else "Request failed"
    
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
        
        success, _, _ = await self._make_request_with_retry('POST', url, data)
        return success
    
    async def release_tokens(self, request_id: str) -> bool:
        """
        Release locked tokens that won't be used.
        
        Args:
            request_id: The request ID returned when tokens were locked
            
        Returns:
            Boolean indicating if the release was successful
        """
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
        
        success, _, _ = await self._make_request_with_retry('POST', url, data)
        return success
    
    async def lock_embedding_tokens(self, token_count: int) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Lock embedding tokens for usage.
        
        Args:
            token_count: The number of embedding tokens to lock
            
        Returns:
            Tuple of (allowed, request_id, error_message)
        """
        url = f"{self.base_url}/embedding/lock"
        data = {
            "app_id": self.app_id,
            "token_count": token_count
        }
        
        success, response_data, error_message = await self._make_request_with_retry('POST', url, data)
        
        if success and response_data and response_data.get("allowed", False):
            return True, response_data.get("request_id"), None
        else:
            return False, None, error_message or response_data.get("message", "Unknown error") if response_data else "Request failed"
    
    async def report_embedding_usage(self, request_id: str, prompt_tokens: int) -> bool:
        """
        Report actual embedding token usage after an API call.
        
        Args:
            request_id: The request ID returned when embedding tokens were locked
            prompt_tokens: Number of tokens used in the embedding request
            
        Returns:
            Boolean indicating if the report was successful
        """
        url = f"{self.base_url}/embedding/report"
        data = {
            "app_id": self.app_id,
            "request_id": request_id,
            "prompt_tokens": prompt_tokens
        }
        
        # Extract rate_request_id from request_id if it's in the format "token_id:rate_id"
        if ":" in request_id:
            token_id, rate_id = request_id.split(":", 1)
            data["request_id"] = token_id
            data["rate_request_id"] = rate_id
        
        success, _, _ = await self._make_request_with_retry('POST', url, data)
        return success
    
    async def release_embedding_tokens(self, request_id: str) -> bool:
        """
        Release locked embedding tokens that won't be used.
        
        Args:
            request_id: The request ID returned when embedding tokens were locked
            
        Returns:
            Boolean indicating if the release was successful
        """
        url = f"{self.base_url}/embedding/release"
        data = {
            "app_id": self.app_id,
            "request_id": request_id
        }
        
        # Extract rate_request_id from request_id if it's in the format "token_id:rate_id"
        if ":" in request_id:
            token_id, rate_id = request_id.split(":", 1)
            data["request_id"] = token_id
            data["rate_request_id"] = rate_id
        
        success, _, _ = await self._make_request_with_retry('POST', url, data)
        return success

    async def get_status(self) -> Optional[Dict[str, Any]]:
        """
        Get the current status of the token counter.
        
        Returns:
            Dict with available tokens, used tokens, locked tokens, available requests, and seconds until reset
        """
        url = f"{self.base_url}/status"
        success, status_data, error_message = await self._make_request_with_retry('GET', url)
        
        if success and status_data:
            # Add client information to help with debugging
            status_data["client_app_id"] = self.app_id
            status_data["client_timestamp"] = time.time()
            
            # Calculate the effective time until reset - the minimum of token and rate reset times
            token_reset = status_data.get("reset_time_seconds", 0)
            
            # Log the status information for debugging
            logger.debug(f"STATUS: Retrieved for {self.app_id}: token_avail={status_data.get('available_tokens')}, req_avail={status_data.get('available_requests')}, reset_in={token_reset}s")
            
            return status_data
        else:
            logger.warning(f"Failed to get status: {error_message}")
            return None
    
    async def get_embedding_status(self) -> Optional[Dict[str, Any]]:
        """
        Get the current status of the embedding token counter.
        
        Returns:
            Dict with available embedding tokens, used tokens, locked tokens, and seconds until reset
        """
        url = f"{self.base_url}/embedding/status"
        success, status_data, error_message = await self._make_request_with_retry('GET', url)
        
        if success and status_data:
            # Add client information to help with debugging
            status_data["client_app_id"] = self.app_id
            status_data["client_timestamp"] = time.time()
            
            # Log the status information for debugging
            logger.debug(f"EMBEDDING STATUS: Retrieved for {self.app_id}: embedding_avail={status_data.get('available_tokens')}, reset_in={status_data.get('reset_time_seconds', 0)}s")
            
            return status_data
        else:
            logger.warning(f"Failed to get embedding status: {error_message}")
            return None

    # Whisper rate limiting methods
    async def lock_whisper_rate(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Lock a Whisper API rate slot.
        
        Returns:
            Tuple of (allowed, request_id, error_message)
        """
        url = f"{self.base_url}/whisper/lock"
        data = {
            "app_id": self.app_id
        }
        
        success, response_data, error_message = await self._make_request_with_retry('POST', url, data)
        
        if success and response_data and response_data.get("allowed", False):
            return True, response_data.get("request_id"), None
        else:
            return False, None, error_message or response_data.get("message", "Whisper rate limit exceeded") if response_data else "Request failed"
    
    async def report_whisper_usage(self, request_id: str) -> bool:
        """
        Report that a Whisper API request was completed.
        
        Args:
            request_id: The request ID returned when the rate slot was locked
            
        Returns:
            Boolean indicating if the report was successful
        """
        url = f"{self.base_url}/whisper/report"
        data = {
            "app_id": self.app_id,
            "request_id": request_id
        }
        
        success, _, _ = await self._make_request_with_retry('POST', url, data)
        return success
    
    async def release_whisper_rate(self, request_id: str) -> bool:
        """
        Release a locked Whisper rate slot that won't be used.
        
        Args:
            request_id: The request ID returned when the rate slot was locked
            
        Returns:
            Boolean indicating if the release was successful
        """
        url = f"{self.base_url}/whisper/release"
        data = {
            "app_id": self.app_id,
            "request_id": request_id
        }
        
        success, _, _ = await self._make_request_with_retry('POST', url, data)
        return success

    async def get_whisper_status(self) -> Optional[Dict[str, Any]]:
        """
        Get the current status of the Whisper rate counter.
        
        Returns:
            Dict with available requests, used requests, locked requests, and seconds until reset
        """
        url = f"{self.base_url}/whisper/status"
        success, status_data, error_message = await self._make_request_with_retry('GET', url)
        
        if success and status_data:
            # Add client information to help with debugging
            status_data["client_app_id"] = self.app_id
            status_data["client_timestamp"] = time.time()
            
            # Log the status information for debugging
            logger.debug(f"WHISPER STATUS: Retrieved for {self.app_id}: req_avail={status_data.get('available_requests')}, reset_in={status_data.get('reset_time_seconds', 0)}s")
            
            return status_data
        else:
            logger.warning(f"Failed to get Whisper status: {error_message}")
            return None
