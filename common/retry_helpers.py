"""
Retry helper utilities for rate-limited API calls.
"""
import asyncio
import functools
from typing import Any, Callable, TypeVar, Optional, Dict
from common.logger import get_logger

logger = get_logger("retry_helpers")

T = TypeVar('T')

async def with_token_limit_retry(
    func: Callable[..., T],
    token_client: Any,
    max_retries: int = 3,
    *args: Any,
    **kwargs: Any
) -> T:
    """
    Wrapper for functions that might hit token rate limits.
    Retries the function call after waiting for the rate limit window to reset.
    
    Args:
        func: The async function to call
        token_client: The token client with a get_status method
        max_retries: Maximum number of retries
        *args: Arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function
        
    Returns:
        The result of the function call
        
    Raises:
        The last exception encountered if all retries fail
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except ValueError as e:
            # Check if it's a rate limit error
            if "Rate limit would be exceeded" in str(e) and attempt < max_retries - 1:
                # Get the token counter status to check when we can retry
                token_status = await token_client.get_status()
                
                if token_status and "reset_time_seconds" in token_status:
                    wait_time = token_status["reset_time_seconds"] + 1  # Add 1 second buffer
                    logger.info(f"Rate limit exceeded. Waiting {wait_time} seconds before retry.")
                    await asyncio.sleep(wait_time)
                    continue
            
            # If it's not a rate limit error or we can't get status, re-raise
            last_exception = e
            raise
        except Exception as e:
            # For any other exception, save it and re-raise
            last_exception = e
            raise
    
    # If we've exhausted all retries, raise the last exception
    if last_exception:
        raise last_exception

def with_token_limit_retry_decorator(token_client: Any, max_retries: int = 3):
    """
    Decorator that adds token rate limit retry logic to an async function.
    
    Args:
        token_client: The token client with a get_status method
        max_retries: Maximum number of retries
        
    Returns:
        Decorated function with retry logic
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await with_token_limit_retry(func, token_client, max_retries, *args, **kwargs)
        return wrapper
    return decorator 