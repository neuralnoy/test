import asyncio
import time
import uuid
from typing import Dict, Any
from common.logger import get_logger

logger = get_logger("rate_counter")

class RateCounter:
    """
    In-memory rate counter service for API calls.
    Manages request rate across applications to prevent rate limit issues.
    """
    def __init__(self, requests_per_minute: int = 100):
        """
        Initialize the rate counter with the rate limit.
        
        Args:
            requests_per_minute: The maximum number of requests per minute
        """
        self.requests_per_minute = requests_per_minute
        self.used_requests = 0
        self.locked_requests = 0
        self.last_reset = time.time()
        self.lock = asyncio.Lock()
        self.active_requests: Dict[str, Dict[str, Any]] = {}
    
    async def _reset_if_needed(self):
        """Reset the counter if a minute has passed."""
        current_time = time.time()
        if current_time - self.last_reset >= 60:
            logger.info("Resetting rate counter")
            self.used_requests = 0
            self.last_reset = current_time
    
    async def lock_request(self, app_id: str) -> Dict[str, Any]:
        """
        Lock a request slot. Returns whether the request is allowed and a request ID.
        
        Args:
            app_id: The ID of the application requesting a slot
            
        Returns:
            Dict with 'allowed' boolean and 'request_id' if allowed
        """
        async with self.lock:
            await self._reset_if_needed()
            
            available = self.requests_per_minute - (self.used_requests + self.locked_requests)
            
            if available > 0:
                request_id = str(uuid.uuid4())
                self.locked_requests += 1
                self.active_requests[request_id] = {
                    "app_id": app_id,
                    "timestamp": time.time()
                }
                logger.info(f"Locked request slot for {app_id} with request ID {request_id}")
                return {
                    "allowed": True,
                    "request_id": request_id
                }
            else:
                logger.warning(f"Rate limit request denied for {app_id}: no available slots")
                return {
                    "allowed": False,
                    "message": f"Rate limit would be exceeded. No available request slots."
                }
    
    async def confirm_request(self, app_id: str, request_id: str) -> bool:
        """
        Confirm that a request was made, converting from locked to used.
        
        Args:
            app_id: The ID of the application confirming the request
            request_id: The request ID returned when the slot was locked
            
        Returns:
            Boolean indicating if the confirmation was successful
        """
        async with self.lock:
            if request_id not in self.active_requests:
                logger.error(f"Invalid request ID {request_id} from {app_id}")
                return False
            
            if self.active_requests[request_id]["app_id"] != app_id:
                logger.error(f"App ID mismatch for request {request_id}")
                return False
            
            # Update counters
            self.locked_requests -= 1
            self.used_requests += 1
            
            # Clean up the request
            del self.active_requests[request_id]
            
            logger.info(f"Confirmed request usage for {app_id}")
            return True
    
    async def release_request(self, app_id: str, request_id: str) -> bool:
        """
        Release a locked request slot that won't be used.
        
        Args:
            app_id: The ID of the application releasing the slot
            request_id: The request ID returned when the slot was locked
            
        Returns:
            Boolean indicating if the release was successful
        """
        async with self.lock:
            if request_id not in self.active_requests:
                logger.error(f"Invalid request ID {request_id} from {app_id}")
                return False
            
            if self.active_requests[request_id]["app_id"] != app_id:
                logger.error(f"App ID mismatch for request {request_id}")
                return False
            
            # Release the locked request
            self.locked_requests -= 1
            
            # Clean up the request
            del self.active_requests[request_id]
            
            logger.info(f"Released request slot for {app_id}")
            return True
    
    async def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the rate counter.
        
        Returns:
            Dict with available requests, used requests, locked requests, and seconds until reset
        """
        async with self.lock:
            await self._reset_if_needed()
            
            current_time = time.time()
            seconds_until_reset = max(0, 60 - (current_time - self.last_reset))
            available_requests = max(0, self.requests_per_minute - (self.used_requests + self.locked_requests))
            
            return {
                "available_requests": available_requests,
                "used_requests": self.used_requests,
                "locked_requests": self.locked_requests,
                "reset_time_seconds": int(seconds_until_reset)
            } 