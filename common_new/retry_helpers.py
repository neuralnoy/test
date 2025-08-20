"""
Retry helper utilities for rate-limited API calls.
"""
import asyncio
import functools
from typing import Any, Callable, TypeVar, Optional, Dict, Awaitable
from common_new.logger import get_logger

logger = get_logger("common")

T = TypeVar('T')

async def with_token_limit_retry(
    func: Callable[..., Awaitable[T]],
    token_client: Any,
    max_retries: int = 3,
    *args: Any,
    **kwargs: Any
) -> T:
    """
    Wrapper for functions that might hit token rate limits or Whisper rate limits.
    Retries the function call after waiting for the rate limit window to reset.
    
    Args:
        func: The async function to call
        token_client: The token client with a get_status method (or get_whisper_status for Whisper)
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
            logger.debug(f"RETRY: Executing attempt {attempt+1}/{max_retries}")
            result = await func(*args, **kwargs)
            logger.debug(f"RETRY: Attempt {attempt+1}/{max_retries} succeeded")
            return result
        except ValueError as e:
            error_msg = str(e)
            logger.debug(f"RETRY: Caught ValueError in attempt {attempt+1}/{max_retries}: {error_msg}")
            
            # Check if it's a rate limit error of any type
            if "would be exceeded" in error_msg and attempt < max_retries - 1:
                logger.debug(f"RETRY: Detected a rate limit error, fetching status")
                
                # Determine which status method to use based on error type
                if "Whisper rate limit" in error_msg:
                    # Use Whisper-specific status
                    token_status = await token_client.get_status() if hasattr(token_client, 'get_status') else None
                else:
                    # Use regular token counter status
                    token_status = await token_client.get_status()
                
                if token_status and "reset_time_seconds" in token_status:
                    wait_time = token_status["reset_time_seconds"] + 1  # Add 1 second buffer
                    logger.debug(f"RETRY: Status retrieved: {token_status}")
                    
                    # Close any open sessions in the token client before long wait
                    if hasattr(token_client, 'close'):
                        try:
                            await token_client.close()
                            logger.debug(f"RETRY: Closed token client sessions before waiting")
                        except Exception as close_err:
                            logger.debug(f"RETRY: Error closing token client: {close_err}")
                    
                    # Use different log messages based on the type of limit
                    if "Whisper rate limit" in error_msg:
                        logger.info(f"RETRY: Whisper rate limit exceeded. Waiting {wait_time} seconds before retry (attempt {attempt+1}/{max_retries}).")
                    elif "API Rate limit" in error_msg:
                        logger.info(f"RETRY: API Rate limit exceeded. Waiting {wait_time} seconds before retry (attempt {attempt+1}/{max_retries}).")
                    elif "Token limit" in error_msg:
                        logger.info(f"RETRY: Token limit exceeded. Waiting {wait_time} seconds before retry (attempt {attempt+1}/{max_retries}).")
                    else:
                        logger.info(f"RETRY: Rate limit exceeded. Waiting {wait_time} seconds before retry (attempt {attempt+1}/{max_retries}).")
                        
                    await asyncio.sleep(wait_time)
                    logger.debug(f"RETRY: Finished waiting {wait_time} seconds, continuing to next attempt")
                    continue
                else:
                    logger.warning(f"RETRY: Could not get valid status from token client: {token_status}")
            
            # If it's not a rate limit error or we can't get status, re-raise
            last_exception = e
            logger.debug(f"RETRY: Re-raising exception: {error_msg}")
            raise
        except Exception as e:
            # For any other exception, save it and re-raise
            last_exception = e
            logger.debug(f"RETRY: Caught non-ValueError exception in attempt {attempt+1}/{max_retries}: {str(e)}")
            raise
    
    # If we've exhausted all retries, raise the last exception
    if last_exception:
        logger.warning(f"RETRY: All {max_retries} retry attempts failed")
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

async def with_whisper_rate_limit_retry(
    func: Callable[..., Awaitable[T]],
    whisper_token_client: Any,
    max_retries: int = 3,
    *args: Any,
    **kwargs: Any
) -> T:
    """
    Specialized wrapper for Whisper API functions that might hit Whisper rate limits.
    
    Args:
        func: The async function to call
        whisper_token_client: The token client with get_whisper_status method
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
            logger.debug(f"WHISPER RETRY: Executing attempt {attempt+1}/{max_retries}")
            result = await func(*args, **kwargs)
            logger.debug(f"WHISPER RETRY: Attempt {attempt+1}/{max_retries} succeeded")
            return result
        except ValueError as e:
            error_msg = str(e)
            logger.debug(f"WHISPER RETRY: Caught ValueError in attempt {attempt+1}/{max_retries}: {error_msg}")
            
            # Check if it's a Whisper rate limit error
            if "Whisper rate limit would be exceeded" in error_msg and attempt < max_retries - 1:
                logger.debug(f"WHISPER RETRY: Detected Whisper rate limit error, fetching status")
                
                # Get Whisper-specific status
                whisper_status = await whisper_token_client.get_status()
                
                if whisper_status and "reset_time_seconds" in whisper_status:
                    wait_time = whisper_status["reset_time_seconds"] + 2  # Add 2 second buffer for Whisper
                    logger.debug(f"WHISPER RETRY: Status retrieved: {whisper_status}")
                    
                    # Close any open sessions in the whisper token client before long wait
                    if hasattr(whisper_token_client, 'close'):
                        try:
                            await whisper_token_client.close()
                            logger.debug(f"WHISPER RETRY: Closed whisper token client sessions before waiting")
                        except Exception as close_err:
                            logger.debug(f"WHISPER RETRY: Error closing whisper token client: {close_err}")
                    elif hasattr(whisper_token_client, 'token_client') and hasattr(whisper_token_client.token_client, 'close'):
                        # Handle wrapper classes like WhisperTokenClientWrapper
                        try:
                            await whisper_token_client.token_client.close()
                            logger.debug(f"WHISPER RETRY: Closed underlying token client sessions before waiting")
                        except Exception as close_err:
                            logger.debug(f"WHISPER RETRY: Error closing underlying token client: {close_err}")
                    
                    logger.info(f"WHISPER RETRY: Whisper rate limit exceeded. Waiting {wait_time} seconds before retry (attempt {attempt+1}/{max_retries}).")
                    
                    await asyncio.sleep(wait_time)
                    logger.debug(f"WHISPER RETRY: Finished waiting {wait_time} seconds, continuing to next attempt")
                    continue
                else:
                    logger.warning(f"WHISPER RETRY: Could not get valid Whisper status from token client: {whisper_status}")
            
            # If it's not a Whisper rate limit error or we can't get status, re-raise
            last_exception = e
            logger.debug(f"WHISPER RETRY: Re-raising exception: {error_msg}")
            raise
        except Exception as e:
            # For any other exception, save it and re-raise
            last_exception = e
            logger.debug(f"WHISPER RETRY: Caught non-ValueError exception in attempt {attempt+1}/{max_retries}: {str(e)}")
            raise
    
    # If we've exhausted all retries, raise the last exception
    if last_exception:
        logger.warning(f"WHISPER RETRY: All {max_retries} retry attempts failed")
        raise last_exception 