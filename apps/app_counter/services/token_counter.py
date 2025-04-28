import asyncio
import time
import uuid
from typing import Dict, Any, Optional
from common.logger import get_logger

logger = get_logger("token_counter")

class TokenCounter:
    """
    In-memory token counter service for OpenAI API calls.
    Manages token usage across applications to prevent rate limit issues.
    """
    def __init__(self, tokens_per_minute: int = 100000):
        """
        Initialize the token counter with the rate limit.
        
        Args:
            tokens_per_minute: The token rate limit per minute
        """
        self.tokens_per_minute = tokens_per_minute
        self.used_tokens = 0
        self.locked_tokens = 0
        self.last_reset = time.time()
        self.lock = asyncio.Lock()
        self.requests: Dict[str, Dict[str, Any]] = {}
    
    async def _reset_if_needed(self):
        """Reset the counter if a minute has passed."""
        current_time = time.time()
        if current_time - self.last_reset >= 60:
            logger.info("Resetting token counter")
            self.used_tokens = 0
            self.last_reset = current_time
    
    async def lock_tokens(self, app_id: str, token_count: int) -> Dict[str, Any]:
        """
        Lock tokens for usage. Returns whether the request is allowed and a request ID.
        
        Args:
            app_id: The ID of the application requesting tokens
            token_count: The number of tokens to lock
            
        Returns:
            Dict with 'allowed' boolean and 'request_id' if allowed
        """
        async with self.lock:
            await self._reset_if_needed()
            
            available = self.tokens_per_minute - (self.used_tokens + self.locked_tokens)
            
            if token_count <= available:
                request_id = str(uuid.uuid4())
                self.locked_tokens += token_count
                self.requests[request_id] = {
                    "app_id": app_id,
                    "locked_tokens": token_count,
                    "timestamp": time.time()
                }
                logger.info(f"Locked {token_count} tokens for {app_id} with request ID {request_id}")
                return {
                    "allowed": True,
                    "request_id": request_id
                }
            else:
                logger.warning(f"Token request denied for {app_id}: requested {token_count}, available {available}")
                return {
                    "allowed": False,
                    "message": f"Rate limit would be exceeded. Available: {available}, Requested: {token_count}"
                }
    
    async def report_usage(self, app_id: str, request_id: str, prompt_tokens: int, completion_tokens: int) -> bool:
        """
        Report actual token usage after an API call.
        
        Args:
            app_id: The ID of the application reporting usage
            request_id: The request ID returned when tokens were locked
            prompt_tokens: Number of tokens used in the prompt
            completion_tokens: Number of tokens used in the completion
            
        Returns:
            Boolean indicating if the report was successful
        """
        async with self.lock:
            if request_id not in self.requests:
                logger.error(f"Invalid request ID {request_id} from {app_id}")
                return False
            
            if self.requests[request_id]["app_id"] != app_id:
                logger.error(f"App ID mismatch for request {request_id}: expected {self.requests[request_id]['app_id']}, got {app_id}")
                return False
            
            # Get the locked tokens for this request
            locked_tokens = self.requests[request_id]["locked_tokens"]
            
            # Calculate actual usage
            actual_usage = prompt_tokens + completion_tokens
            
            # Update counters
            self.locked_tokens -= locked_tokens
            self.used_tokens += actual_usage
            
            # Clean up the request
            del self.requests[request_id]
            
            logger.info(f"Reported usage for {app_id}: prompt={prompt_tokens}, completion={completion_tokens}")
            return True
    
    async def release_tokens(self, app_id: str, request_id: str) -> bool:
        """
        Release locked tokens that won't be used.
        
        Args:
            app_id: The ID of the application releasing tokens
            request_id: The request ID returned when tokens were locked
            
        Returns:
            Boolean indicating if the release was successful
        """
        async with self.lock:
            if request_id not in self.requests:
                logger.error(f"Invalid request ID {request_id} from {app_id}")
                return False
            
            if self.requests[request_id]["app_id"] != app_id:
                logger.error(f"App ID mismatch for request {request_id}: expected {self.requests[request_id]['app_id']}, got {app_id}")
                return False
            
            # Release the locked tokens
            self.locked_tokens -= self.requests[request_id]["locked_tokens"]
            
            # Clean up the request
            del self.requests[request_id]
            
            logger.info(f"Released tokens for {app_id} with request ID {request_id}")
            return True
    
    async def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the token counter.
        
        Returns:
            Dict with available tokens, used tokens, locked tokens, and seconds until reset
        """
        async with self.lock:
            await self._reset_if_needed()
            
            current_time = time.time()
            seconds_until_reset = max(0, 60 - (current_time - self.last_reset))
            available_tokens = max(0, self.tokens_per_minute - (self.used_tokens + self.locked_tokens))
            
            return {
                "available_tokens": available_tokens,
                "used_tokens": self.used_tokens,
                "locked_tokens": self.locked_tokens,
                "reset_time_seconds": int(seconds_until_reset)
            } 