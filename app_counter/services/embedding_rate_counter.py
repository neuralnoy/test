import asyncio
import time
import uuid
from typing import Dict, Any
from common_new.logger import get_logger

logger = get_logger("services")

class EmbeddingRateCounter:
    """
    In-memory embedding rate counter service for embedding API calls.
    Manages embedding request rate across applications to prevent rate limit issues.
    """
    def __init__(self, requests_per_minute: int = 500):
        """
        Initialize the embedding rate counter with the rate limit.
        
        Args:
            requests_per_minute: The maximum number of embedding requests per minute
        """
        self.requests_per_minute = requests_per_minute
        self.used_requests = 0
        self.locked_requests = 0
        self.last_reset = time.time()
        self.lock = asyncio.Lock()
        self.active_requests: Dict[str, Dict[str, Any]] = {}
        logger.info(f"Initialized EmbeddingRateCounter with {requests_per_minute} embedding requests per minute limit")
    
    async def _reset_if_needed(self):
        """Reset the counter if a minute has passed."""
        current_time = time.time()

        # Clean up stale locked requests older than 60 seconds
        stale_requests = [
            req_id for req_id, req_data in self.active_requests.items()
            if current_time - req_data.get("timestamp", 0) > 60
        ]

        if stale_requests:
            self.locked_requests -= len(stale_requests)
            for req_id in stale_requests:
                del self.active_requests[req_id]
            logger.warning(f"Cleaned up {len(stale_requests)} stale embedding rate requests.")

        if current_time - self.last_reset >= 60:
            logger.info(f"Resetting embedding rate counter. Before reset: used={self.used_requests}, locked={self.locked_requests}, total={(self.used_requests + self.locked_requests)}/{self.requests_per_minute}")
            self.used_requests = 0
            self.last_reset = current_time
            logger.info(f"After reset: used={self.used_requests}, locked={self.locked_requests}, total={(self.used_requests + self.locked_requests)}/{self.requests_per_minute}")
    
    async def lock_request(self, app_id: str) -> Dict[str, Any]:
        """
        Lock a request slot for embedding usage. Returns whether the request is allowed and a request ID.
        
        Args:
            app_id: The ID of the application requesting a slot
            
        Returns:
            Dict with 'allowed' boolean and 'request_id' if allowed
        """
        async with self.lock:
            await self._reset_if_needed()
            
            available = self.requests_per_minute - (self.used_requests + self.locked_requests)
            total_used = self.used_requests + self.locked_requests
            
            logger.info(f"EMBEDDING RATE CHECK: app={app_id}, used={self.used_requests}, locked={self.locked_requests}, total={total_used}/{self.requests_per_minute}, available={available}")
            
            if available > 0:
                request_id = str(uuid.uuid4())
                self.locked_requests += 1
                self.active_requests[request_id] = {
                    "app_id": app_id,
                    "timestamp": time.time()
                }
                new_total = self.used_requests + self.locked_requests
                logger.info(f"EMBEDDING RATE APPROVED: app={app_id}, request_id={request_id}, new_total={new_total}/{self.requests_per_minute}, locked={self.locked_requests}, used={self.used_requests}")
                return {
                    "allowed": True,
                    "request_id": request_id
                }
            else:
                logger.warning(f"EMBEDDING RATE DENIED: app={app_id}, available={available}, total={total_used}/{self.requests_per_minute}")
                return {
                    "allowed": False,
                    "message": f"Embedding rate limit would be exceeded. Available: {available}, Total: {total_used}/{self.requests_per_minute}"
                }
    
    async def confirm_request(self, app_id: str, request_id: str) -> bool:
        """
        Confirm an embedding request completion after successful API call.
        
        Args:
            app_id: The ID of the application confirming the request
            request_id: The request ID returned when the request was locked
            
        Returns:
            Boolean indicating if the confirmation was successful
        """
        async with self.lock:
            if request_id not in self.active_requests:
                logger.error(f"EMBEDDING RATE CONFIRM ERROR: Invalid request ID {request_id} from {app_id}")
                return False
            
            if self.active_requests[request_id]["app_id"] != app_id:
                logger.error(f"EMBEDDING RATE CONFIRM ERROR: App ID mismatch for request {request_id}: expected {self.active_requests[request_id]['app_id']}, got {app_id}")
                return False
            
            # Move from locked to used
            before_locked = self.locked_requests
            before_used = self.used_requests
            
            self.locked_requests -= 1
            self.used_requests += 1
            
            # Clean up the request
            del self.active_requests[request_id]
            
            total = self.used_requests + self.locked_requests
            logger.info(f"EMBEDDING RATE CONFIRMED: app={app_id}, request_id={request_id}, locked changed {before_locked}->{self.locked_requests}, used changed {before_used}->{self.used_requests}, total={total}/{self.requests_per_minute}")
            return True
    
    async def release_request(self, app_id: str, request_id: str) -> bool:
        """
        Release a locked embedding request that won't be used.
        
        Args:
            app_id: The ID of the application releasing the request
            request_id: The request ID returned when the request was locked
            
        Returns:
            Boolean indicating if the release was successful
        """
        async with self.lock:
            if request_id not in self.active_requests:
                logger.error(f"EMBEDDING RATE RELEASE ERROR: Invalid request ID {request_id} from {app_id}")
                return False
            
            if self.active_requests[request_id]["app_id"] != app_id:
                logger.error(f"EMBEDDING RATE RELEASE ERROR: App ID mismatch for request {request_id}: expected {self.active_requests[request_id]['app_id']}, got {app_id}")
                return False
            
            # Release the locked request
            before_locked = self.locked_requests
            self.locked_requests -= 1
            
            # Clean up the request
            del self.active_requests[request_id]
            
            total = self.used_requests + self.locked_requests
            logger.info(f"EMBEDDING RATE RELEASED: app={app_id}, request_id={request_id}, locked changed {before_locked}->{self.locked_requests}, total={total}/{self.requests_per_minute}")
            return True
    
    async def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the embedding rate counter.
        
        Returns:
            Dict with available requests, used requests, locked requests, and seconds until reset
        """
        async with self.lock:
            await self._reset_if_needed()
            
            current_time = time.time()
            seconds_until_reset = max(0, 60 - (current_time - self.last_reset))
            available_requests = max(0, self.requests_per_minute - (self.used_requests + self.locked_requests))
            total = self.used_requests + self.locked_requests
            
            logger.info(f"EMBEDDING RATE STATUS: used={self.used_requests}, locked={self.locked_requests}, total={total}/{self.requests_per_minute}, available={available_requests}, reset_in={int(seconds_until_reset)}s")
            
            return {
                "available_requests": available_requests,
                "used_requests": self.used_requests,
                "locked_requests": self.locked_requests,
                "reset_time_seconds": int(seconds_until_reset)
            } 