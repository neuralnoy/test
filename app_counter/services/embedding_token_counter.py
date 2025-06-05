import asyncio
import time
import uuid
from typing import Dict, Any, Optional
from common_new.logger import get_logger

logger = get_logger("services")

class EmbeddingTokenCounter:
    """
    In-memory embedding token counter service for OpenAI embedding API calls.
    Manages embedding token usage across applications to prevent rate limit issues.
    """
    def __init__(self, tokens_per_minute: int = 1000000):
        """
        Initialize the embedding token counter with the rate limit.
        
        Args:
            tokens_per_minute: The embedding token rate limit per minute (typically higher than chat tokens)
        """
        self.tokens_per_minute = tokens_per_minute
        self.used_tokens = 0
        self.locked_tokens = 0
        self.last_reset = time.time()
        self.lock = asyncio.Lock()
        self.requests: Dict[str, Dict[str, Any]] = {}
        logger.info(f"Initialized EmbeddingTokenCounter with {tokens_per_minute} embedding tokens per minute limit")
    
    async def _reset_if_needed(self):
        """Reset the counter if a minute has passed."""
        current_time = time.time()
        if current_time - self.last_reset >= 60:
            logger.info(f"Resetting embedding token counter. Before reset: used={self.used_tokens}, locked={self.locked_tokens}, total={(self.used_tokens + self.locked_tokens)}/{self.tokens_per_minute}")
            self.used_tokens = 0
            self.last_reset = current_time
            logger.info(f"After reset: used={self.used_tokens}, locked={self.locked_tokens}, total={(self.used_tokens + self.locked_tokens)}/{self.tokens_per_minute}")
    
    async def lock_tokens(self, app_id: str, token_count: int) -> Dict[str, Any]:
        """
        Lock embedding tokens for usage. Returns whether the request is allowed and a request ID.
        
        Args:
            app_id: The ID of the application requesting tokens
            token_count: The number of embedding tokens to lock
            
        Returns:
            Dict with 'allowed' boolean and 'request_id' if allowed
        """
        async with self.lock:
            await self._reset_if_needed()
            
            available = self.tokens_per_minute - (self.used_tokens + self.locked_tokens)
            total_used = self.used_tokens + self.locked_tokens
            
            logger.info(f"EMBEDDING TOKEN CHECK: app={app_id}, requested={token_count}, used={self.used_tokens}, locked={self.locked_tokens}, total={total_used}/{self.tokens_per_minute}, available={available}")
            
            if token_count <= available:
                request_id = str(uuid.uuid4())
                self.locked_tokens += token_count
                self.requests[request_id] = {
                    "app_id": app_id,
                    "locked_tokens": token_count,
                    "timestamp": time.time()
                }
                new_total = self.used_tokens + self.locked_tokens
                logger.info(f"EMBEDDING TOKEN APPROVED: app={app_id}, request_id={request_id}, tokens={token_count}, new_total={new_total}/{self.tokens_per_minute}, locked={self.locked_tokens}, used={self.used_tokens}")
                return {
                    "allowed": True,
                    "request_id": request_id
                }
            else:
                logger.warning(f"EMBEDDING TOKEN DENIED: app={app_id}, requested={token_count}, available={available}, total={total_used}/{self.tokens_per_minute}")
                return {
                    "allowed": False,
                    "message": f"Embedding token limit would be exceeded. Available: {available}, Requested: {token_count}, Total: {total_used}/{self.tokens_per_minute}"
                }
    
    async def report_usage(self, app_id: str, request_id: str, prompt_tokens: int) -> bool:
        """
        Report actual embedding token usage after an API call.
        Note: Embeddings only have prompt tokens, no completion tokens.
        
        Args:
            app_id: The ID of the application reporting usage
            request_id: The request ID returned when tokens were locked
            prompt_tokens: Number of tokens used for embedding
            
        Returns:
            Boolean indicating if the report was successful
        """
        async with self.lock:
            if request_id not in self.requests:
                logger.error(f"EMBEDDING TOKEN REPORT ERROR: Invalid request ID {request_id} from {app_id}")
                return False
            
            if self.requests[request_id]["app_id"] != app_id:
                logger.error(f"EMBEDDING TOKEN REPORT ERROR: App ID mismatch for request {request_id}: expected {self.requests[request_id]['app_id']}, got {app_id}")
                return False
            
            # Get the locked tokens for this request
            locked_tokens = self.requests[request_id]["locked_tokens"]
            
            # For embeddings, actual usage is just prompt tokens
            actual_usage = prompt_tokens
            
            # Update counters
            before_locked = self.locked_tokens
            before_used = self.used_tokens
            
            self.locked_tokens -= locked_tokens
            self.used_tokens += actual_usage
            
            # Clean up the request
            del self.requests[request_id]
            
            total = self.used_tokens + self.locked_tokens
            logger.info(f"EMBEDDING TOKEN REPORTED: app={app_id}, request_id={request_id}, prompt={prompt_tokens}, actual={actual_usage}, expected={locked_tokens}, locked changed {before_locked}->{self.locked_tokens}, used changed {before_used}->{self.used_tokens}, total={total}/{self.tokens_per_minute}")
            return True
    
    async def release_tokens(self, app_id: str, request_id: str) -> bool:
        """
        Release locked embedding tokens that won't be used.
        
        Args:
            app_id: The ID of the application releasing tokens
            request_id: The request ID returned when tokens were locked
            
        Returns:
            Boolean indicating if the release was successful
        """
        async with self.lock:
            if request_id not in self.requests:
                logger.error(f"EMBEDDING TOKEN RELEASE ERROR: Invalid request ID {request_id} from {app_id}")
                return False
            
            if self.requests[request_id]["app_id"] != app_id:
                logger.error(f"EMBEDDING TOKEN RELEASE ERROR: App ID mismatch for request {request_id}: expected {self.requests[request_id]['app_id']}, got {app_id}")
                return False
            
            # Release the locked tokens
            before_locked = self.locked_tokens
            released_tokens = self.requests[request_id]["locked_tokens"]
            self.locked_tokens -= released_tokens
            
            # Clean up the request
            del self.requests[request_id]
            
            total = self.used_tokens + self.locked_tokens
            logger.info(f"EMBEDDING TOKEN RELEASED: app={app_id}, request_id={request_id}, tokens={released_tokens}, locked changed {before_locked}->{self.locked_tokens}, total={total}/{self.tokens_per_minute}")
            return True
    
    async def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the embedding token counter.
        
        Returns:
            Dict with available tokens, used tokens, locked tokens, and seconds until reset
        """
        async with self.lock:
            await self._reset_if_needed()
            
            current_time = time.time()
            seconds_until_reset = max(0, 60 - (current_time - self.last_reset))
            available_tokens = max(0, self.tokens_per_minute - (self.used_tokens + self.locked_tokens))
            total = self.used_tokens + self.locked_tokens
            
            logger.info(f"EMBEDDING TOKEN STATUS: used={self.used_tokens}, locked={self.locked_tokens}, total={total}/{self.tokens_per_minute}, available={available_tokens}, reset_in={int(seconds_until_reset)}s")
            
            return {
                "available_tokens": available_tokens,
                "used_tokens": self.used_tokens,
                "locked_tokens": self.locked_tokens,
                "reset_time_seconds": int(seconds_until_reset)
            } 