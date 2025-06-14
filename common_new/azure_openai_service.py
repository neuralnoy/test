"""
Azure OpenAI Service for making API calls to Azure-hosted OpenAI models.
"""
import os
import tiktoken
import instructor
import asyncio
import time
from typing import Dict, List, Any, Optional, TypeVar, Type
from collections import deque

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError
from common_new.logger import get_logger
from common_new.retry_helpers import with_token_limit_retry

from common_new.token_client import TokenClient
load_dotenv()

logger = get_logger("common")

COUNTER_BASE_URL = os.getenv("COUNTER_APP_BASE_URL")

# Type variable for Pydantic models
T = TypeVar('T', bound=BaseModel)

class WhisperRateLimiter:
    """
    Rate limiter specifically designed for Azure OpenAI Whisper API requests.
    Tracks requests per minute with sliding window approach.
    Thread-safe and async-compatible.
    """
    def __init__(self, requests_per_minute: int = 15):
        """
        Initialize Whisper API rate limiter.
        
        Args:
            requests_per_minute: Maximum Whisper API requests allowed per minute (default: 50)
        """
        self.requests_per_minute = requests_per_minute
        self.requests = deque()
        self._lock = asyncio.Lock()
        
    async def can_make_request(self) -> bool:
        """
        Check if a Whisper API request can be made without exceeding rate limit.
        
        Returns:
            bool: True if Whisper request can be made, False otherwise
        """
        async with self._lock:
            now = time.time()
            
            # Remove requests older than 1 minute
            while self.requests and now - self.requests[0] > 60:
                self.requests.popleft()
            
            # Check if we can make another request
            return len(self.requests) < self.requests_per_minute
    
    async def record_request(self) -> None:
        """
        Record that a Whisper API request was made.
        """
        async with self._lock:
            self.requests.append(time.time())
    
    async def wait_for_availability(self) -> None:
        """
        Wait until a Whisper API request can be made without exceeding rate limit.
        """
        while not await self.can_make_request():
            # Calculate how long to wait
            async with self._lock:
                if self.requests:
                    oldest_request = self.requests[0]
                    wait_time = 60 - (time.time() - oldest_request) + 1  # Add 1 second buffer
                    wait_time = max(1, wait_time)  # Wait at least 1 second
                else:
                    wait_time = 1
            
            logger.info(f"Whisper API rate limit reached, waiting {wait_time:.1f} seconds")
            await asyncio.sleep(wait_time)
    
    def get_current_usage(self) -> Dict[str, Any]:
        """
        Get current Whisper API rate limit usage statistics.
        
        Returns:
            Dict with current Whisper API usage information
        """
        now = time.time()
        # Count requests in the last minute
        recent_requests = sum(1 for req_time in self.requests if now - req_time <= 60)
        
        return {
            "requests_in_last_minute": recent_requests,
            "requests_per_minute_limit": self.requests_per_minute,
            "utilization_percentage": (recent_requests / self.requests_per_minute) * 100
        }

class AzureOpenAIService:
    """
    Service for interacting with Azure-hosted OpenAI models.
    Provides functionality for authentication, prompt management, and API calls.
    Includes token usage tracking to prevent rate limit issues.
    """
    
    def __init__(self, model: Optional[str] = None, app_id: str = "default_app", token_counter_url: str = COUNTER_BASE_URL):
        """
        Initialize the Azure OpenAI service with credentials from environment variables.
        
        Args:
            model: Optional default model to use. If not specified, uses the AZURE_OPENAI_DEPLOYMENT_NAME from .env.
            app_id: ID of the application using this service. Used for token tracking.
            token_counter_url: URL of the token counter service.
            token_counter_resource_uri: Resource URI for authenticating with token counter service.
        """
        self.api_version = os.getenv("APP_OPENAI_API_VERSION")
        self.azure_endpoint = os.getenv("APP_OPENAI_API_BASE")
        self.default_model = model or os.getenv("APP_OPENAI_ENGINE")
        self.app_id = app_id
        self.token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default"
        )
        
        self.token_client = TokenClient(app_id=app_id, base_url=token_counter_url)
        
        if not self.api_version or not self.azure_endpoint:
            raise ValueError("APP_OPENAI_API_VERSION and APP_OPENAI_API_BASE must be set in .env file or exported as environment variables")
        
        logger.info(f"Initializing Azure OpenAI service with endpoint: {self.azure_endpoint}")
        self.client = self._initialize_client()
        
        # Initialize instructor client for structured outputs
        self.instructor_client = instructor.from_openai(self.client, mode=instructor.Mode.TOOLS)
    
    
    def _initialize_client(self) -> AzureOpenAI:
        """
        Initialize the Azure OpenAI client with the appropriate configuration.
        
        Returns:
            AzureOpenAI: An initialized Azure OpenAI client.
        """
        return AzureOpenAI(
            api_version=self.api_version,
            azure_endpoint=self.azure_endpoint,
            azure_ad_token_provider=self.token_provider
        )
    
    def _get_encoding_for_model(self, model: str) -> Any:
        """
        Get the correct tokenizer for the specified model.
        
        Args:
            model: Model name or deployment name
            
        Returns:
            Tiktoken encoding for the model
        """
        try:
            # For Azure deployments, needs to map to base model names
            # This is a simplified mapping - check if this is correct!!!
            model_mapping = {
                "gpt-4": "gpt-4",
                "gpt-4-32k": "gpt-4-32k",
                "gpt-3.5-turbo": "gpt-3.5-turbo",
                "text-embedding-ada-002": "text-embedding-ada-002"
            }
            
            # Try to get a direct encoding for the model
            try:
                return tiktoken.encoding_for_model(model)
            except KeyError:
                # If the model is not found directly, try to find it in our mapping
                for base_model, openai_model in model_mapping.items():
                    if base_model in model.lower():
                        return tiktoken.encoding_for_model(openai_model)
                
                # Fall back to cl100k_base for newer models
                logger.warning(f"Model {model} not found, falling back to cl100k_base encoding")
                return tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Error getting encoding for model {model}: {str(e)}. Falling back to cl100k_base encoding.")
            return tiktoken.get_encoding("cl100k_base")
    
    def _count_tokens_for_message(self, message: Dict[str, str], encoding: Any) -> int:
        """
        Count tokens for a single message.
        
        Args:
            message: A single message dictionary
            encoding: Tiktoken encoding to use
            
        Returns:
            int: Number of tokens in the message
        """
        # Per OpenAI's documentation about token counting in chat API:
        # https://platform.openai.com/docs/guides/chat/managing-tokens
        
        # Count tokens in message content
        content = message.get("content", "")
        token_count = len(encoding.encode(content))
        
        # Add tokens for message metadata
        # Every message follows <im_start>{role/name}\n{content}<im_end>\n
        token_count += 4  # For im_start, role, im_end, and final \n
        
        # If there's a name field, count those tokens too
        if "name" in message:
            token_count += len(encoding.encode(message["name"]))
        
        return token_count
    
    def _estimate_token_count(self, messages: List[Dict[str, str]], model: str, max_tokens: Optional[int] = None) -> int:
        """
        Estimate token count for a request using tiktoken for accurate counting.
        
        Args:
            messages: Messages to estimate tokens for
            model: Model to use for encoding
            max_tokens: Maximum completion tokens
            
        Returns:
            int: Estimated token count
        """
        # Get the appropriate encoding for the model
        encoding = self._get_encoding_for_model(model)
        
        # Token count starts with a base for the model
        token_count = 3  # Every reply is primed with <|start|>assistant<|message|>
        
        # Count tokens in each message
        for message in messages:
            token_count += self._count_tokens_for_message(message, encoding)
        
        # Add estimated completion tokens
        completion_tokens = max_tokens or 1000  # Default to 1000 if not specified
        token_count += completion_tokens
        
        return token_count
    
    
    def format_prompt(
        self,
        system_prompt: str,
        user_prompt: str,
        variables: Dict[str, Any] = None,
        examples: List[Dict[str, str]] = None
    ) -> List[Dict[str, str]]:
        """
        Format a prompt with system message, examples, and user message with variable substitution.
        
        Args:
            system_prompt: The system prompt that sets context for the AI.
            user_prompt: The user prompt template with placeholders for variables.
            variables: Dictionary of variables to substitute in the template.
            examples: Optional list of few-shot examples as message dictionaries.
            
        Returns:
            List[Dict[str, str]]: A list of message dictionaries ready for the OpenAI API.
        """
        variables = variables or {}
        examples = examples or []
        
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add few-shot examples if provided
        messages.extend(examples)
        
        # Format and add the user prompt
        try:
            formatted_user_prompt = user_prompt.format(**variables)
            messages.append({"role": "user", "content": formatted_user_prompt})
        except KeyError as e:
            error_msg = f"Missing template variable: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)
            
        return messages


    async def structured_completion(
        self,
        response_model: Type[T],
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> T:
        """
        Generate a structured completion using Instructor for Pydantic model validation.
        
        Args:
            response_model: Pydantic model class for response validation
            messages: List of messages for the conversation
            model: Model to use (defaults to self.default_model)
            temperature: Temperature for generation (defaults to 0.0 for deterministic outputs)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters for the completion
            
        Returns:
            T: Validated Pydantic model instance
            
        Raises:
            ValidationError: If response doesn't match the schema after retries
            ValueError: If token limit would be exceeded
        """
        model = model or self.default_model
        
        # Estimate token usage (including schema overhead for function calling)
        estimated_tokens = self._estimate_token_count(messages, model, max_tokens)
        # Add extra tokens for function calling overhead
        estimated_tokens += 500
        
        # Check token availability
        allowed, request_id, error_message = await self.token_client.lock_tokens(estimated_tokens)
        
        if not allowed:
            logger.warning(f"Structured completion request denied: {error_message}")
            raise ValueError(error_message)
        
        try:
            logger.debug(f"Sending structured completion request to model: {model}")
            
            # Use instructor for structured completion
            response = self.instructor_client.chat.completions.create(
                model=model,
                response_model=response_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            # Report actual token usage if available
            # Instructor responses have access to the raw OpenAI response via _raw_response
            if hasattr(response, '_raw_response') and hasattr(response._raw_response, 'usage'):
                await self.token_client.report_usage(
                    request_id=request_id,
                    prompt_tokens=response._raw_response.usage.prompt_tokens,
                    completion_tokens=response._raw_response.usage.completion_tokens
                )
            
            logger.debug("Successfully received and validated structured response")
            return response
            
        except ValidationError as e:
            # Release tokens if validation fails
            await self.token_client.release_tokens(request_id)
            logger.error(f"Validation error in structured completion: {str(e)}")
            raise
        except Exception as e:
            # Release tokens if API call fails
            await self.token_client.release_tokens(request_id)
            logger.error(f"Error in structured completion: {str(e)}")
            raise
    
    async def structured_prompt(
        self,
        response_model: Type[T],
        system_prompt: str,
        user_prompt: str,
        variables: Dict[str, Any] = None,
        examples: List[Dict[str, str]] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> T:
        """
        Send a structured prompt and get a validated Pydantic model response.
        Includes retry logic for token rate limit errors.
        
        Args:
            response_model: Pydantic model class for response validation
            system_prompt: System prompt
            user_prompt: User prompt template
            variables: Variables for prompt formatting
            examples: Example messages
            model: Model to use
            temperature: Temperature for generation (defaults to 0.0 for deterministic outputs)
            max_tokens: Maximum tokens
            max_retries: Maximum retries for validation
            **kwargs: Additional parameters
            
        Returns:
            T: Validated Pydantic model instance
        """
        # Create a helper function for retry logic
        async def _do_structured_prompt():
            # Format the prompt using existing method
            messages = self.format_prompt(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                variables=variables,
                examples=examples
            )
            
            return await self.structured_completion(
                response_model=response_model,
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        
        # Use retry helper for token limit handling
        try:
            return await with_token_limit_retry(_do_structured_prompt, self.token_client)
        except Exception as e:
            logger.error(f"Error in structured prompt: {str(e)}")
            raise

class AzureOpenAIServiceWhisper(AzureOpenAIService):
    """
    Service for interacting with Azure-hosted OpenAI Whisper models.
    Provides functionality for audio transcription with proper rate limiting and error handling.
    """
    def __init__(self, model: Optional[str] = None, app_id: str = "default_app"):
        super().__init__(model=model, app_id=app_id)
        
        self.api_version = os.getenv("APP_OPENAI_API_VERSION")
        self.azure_endpoint = os.getenv("APP_OPENAI_API_BASE")
        self.default_model = model or os.getenv("APP_OPENAI_ENGINE")
        self.app_id = app_id
        
        # Initialize rate limiter for Whisper API
        whisper_rpm = int(os.getenv("WHISPER_REQUESTS_PER_MINUTE", "15"))
        self.rate_limiter = WhisperRateLimiter(requests_per_minute=whisper_rpm)
        logger.info(f"Initialized Whisper rate limiter with {whisper_rpm} requests per minute")
        
        # Initialize a separate client for audio operations
        self._audio_client = None
        
    def _initialize_audio_client(self) -> AzureOpenAI:
        """
        Initialize the Azure OpenAI client specifically for audio operations.
        """
        if self._audio_client is None:
            token_provider = get_bearer_token_provider(
                DefaultAzureCredential(), 
                "https://cognitiveservices.azure.com/.default"
            )
            
            self._audio_client = AzureOpenAI(
                api_version=self.api_version,
                azure_endpoint=self.azure_endpoint,
                azure_ad_token_provider=token_provider,
            )
            
        return self._audio_client
    
    async def transcribe_audio(
        self,
        audio_file_path: str,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        response_format: str = "json",
        temperature: float = 0.0,
        timestamp_granularities: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Transcribe audio file using Azure OpenAI Whisper.
        
        Args:
            audio_file_path: Path to the audio file to transcribe
            language: Language of the audio (ISO-639-1 format, e.g., 'en', 'es')
            prompt: Optional text to guide the model's style or continue a previous audio segment
            response_format: Format of the response ('json', 'text', 'srt', 'verbose_json', 'vtt')
            temperature: Sampling temperature (0 to 1)
            timestamp_granularities: List of timestamp granularities ('word', 'segment')
            **kwargs: Additional parameters for the transcription
            
        Returns:
            Dict containing transcription results
            
        Raises:
            FileNotFoundError: If audio file doesn't exist
            ValueError: If file format is not supported
            Exception: For other API errors
        """
        if not os.path.exists(audio_file_path):
            raise FileNotFoundError(f"Audio file not found: {audio_file_path}")
        
        # Validate audio file before processing
        if not self.validate_audio_file(audio_file_path):
            raise ValueError(f"Invalid audio file: {audio_file_path}")
        
        # Wait for rate limit availability
        await self.rate_limiter.wait_for_availability()
        
        try:
            logger.info(f"Starting audio transcription for file: {audio_file_path}")
            
            # Record the request for rate limiting
            await self.rate_limiter.record_request()
            
            # Initialize audio client
            client = self._initialize_audio_client()
            
            # Prepare transcription parameters
            transcription_params = {
                "model": self.default_model,
                "response_format": response_format,
                "temperature": temperature,
            }
            
            if language:
                transcription_params["language"] = language
            if prompt:
                transcription_params["prompt"] = prompt
            if timestamp_granularities:
                transcription_params["timestamp_granularities"] = timestamp_granularities
            
            # Add any additional parameters
            transcription_params.update(kwargs)
            
            # Open and transcribe the audio file
            with open(audio_file_path, "rb") as audio_file:
                logger.debug(f"Sending transcription request with params: {transcription_params}")
                
                response = client.audio.transcriptions.create(
                    file=audio_file,
                    **transcription_params
                )
            
            # Process response based on format
            if response_format == "json" or response_format == "verbose_json":
                result = response.model_dump() if hasattr(response, 'model_dump') else response
            else:
                # For text, srt, vtt formats, response is a string
                result = {"text": str(response)}
            
            logger.info(f"Successfully transcribed audio file: {audio_file_path}")
            return result
            
        except Exception as e:
            logger.error(f"Error in audio transcription: {str(e)}")
            raise
    
    async def transcribe_audio_with_retry(
        self,
        audio_file_path: str,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Transcribe audio with retry logic for handling transient failures.
        
        Args:
            audio_file_path: Path to the audio file to transcribe
            max_retries: Maximum number of retry attempts
            retry_delay: Base delay between retries in seconds (uses exponential backoff)
            **kwargs: Additional parameters passed to transcribe_audio
            
        Returns:
            Dict containing transcription results
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                return await self.transcribe_audio(audio_file_path, **kwargs)
            except Exception as e:
                last_exception = e
                
                if attempt < max_retries:
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"Transcription attempt {attempt + 1} failed: {str(e)}. Retrying in {wait_time} seconds")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All {max_retries + 1} transcription attempts failed")
        
        # If we get here, all retries failed
        raise last_exception
    
    async def transcribe_audio_chunks(
        self,
        audio_file_paths: List[str],
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Transcribe multiple audio chunks concurrently.
        
        Args:
            audio_file_paths: List of paths to audio files to transcribe
            **kwargs: Additional parameters passed to transcribe_audio
            
        Returns:
            List of transcription results in the same order as input files
        """
        import asyncio
        
        logger.info(f"Starting concurrent transcription of {len(audio_file_paths)} audio chunks")
        
        # Create transcription tasks
        tasks = []
        for audio_path in audio_file_paths:
            task = self.transcribe_audio_with_retry(audio_path, **kwargs)
            tasks.append(task)
        
        try:
            # Execute all transcriptions concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results and handle any exceptions
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to transcribe chunk {i} ({audio_file_paths[i]}): {str(result)}")
                    processed_results.append({
                        "error": str(result),
                        "text": "",
                        "file_path": audio_file_paths[i]
                    })
                else:
                    processed_results.append(result)
            
            logger.info(f"Completed transcription of {len(audio_file_paths)} audio chunks")
            return processed_results
            
        except Exception as e:
            logger.error(f"Error in concurrent audio transcription: {str(e)}")
            raise
    
    def validate_audio_file(self, audio_file_path: str) -> bool:
        """
        Validate audio file format and size.
        
        Args:
            audio_file_path: Path to the audio file
            
        Returns:
            bool: True if file is valid, False otherwise
        """
        if not os.path.exists(audio_file_path):
            logger.error(f"Audio file does not exist: {audio_file_path}")
            return False
        
        # Check file size (Whisper has a 25MB limit)
        file_size = os.path.getsize(audio_file_path)
        max_size = 25 * 1024 * 1024  # 25MB in bytes
        
        if file_size > max_size:
            logger.error(f"Audio file too large: {file_size} bytes (max: {max_size} bytes)")
            return False
        
        # Check file extension
        supported_formats = {'.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'}
        file_extension = os.path.splitext(audio_file_path)[1].lower()
        
        if file_extension not in supported_formats:
            logger.error(f"Unsupported audio format: {file_extension}")
            return False
        
        logger.debug(f"Audio file validation passed: {audio_file_path}")
        return True
    
