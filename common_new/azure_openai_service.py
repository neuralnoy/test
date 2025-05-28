"""
Azure OpenAI Service for making API calls to Azure-hosted OpenAI models.
"""
import os
import tiktoken
import instructor
from typing import Dict, List, Any, Optional, Union, TypeVar, Type

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
        self.default_model = model or os.getenv("APP_OPENAI_ENGIBE")
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
        self.instructor_client = instructor.from_openai(self.client)
    
    
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
    
    async def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        stop: Optional[Union[str, List[str]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a chat completion using the specified Azure OpenAI model.
        This method now includes token tracking to prevent rate limit issues.
        
        Args:
            messages: A list of messages in the conversation.
            model: The deployment name of the model. Defaults to self.default_model.
            temperature: Controls randomness. Higher values mean more random completions.
            max_tokens: The maximum number of tokens to generate.
            top_p: Controls diversity via nucleus sampling.
            frequency_penalty: How much to penalize new tokens based on their frequency.
            presence_penalty: How much to penalize new tokens based on their presence.
            stop: Sequences where the API will stop generating tokens.
            
        Returns:
            Dict[str, Any]: The completion response.
            
        Raises:
            ValueError: If token limit would be exceeded
        """
        model = model or self.default_model
        
        # Estimate token usage with tiktoken
        estimated_tokens = self._estimate_token_count(messages, model, max_tokens)
        
        # Attempt to lock tokens
        allowed, request_id, error_message = await self.token_client.lock_tokens(estimated_tokens)
        
        if not allowed:
            logger.warning(f"Request denied: {error_message}")
            # Pass through the exact error message to preserve the rate vs token limit distinction
            raise ValueError(error_message)
            
        try:
            logger.debug(f"Sending chat completion request to model: {model}")
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                stop=stop,
                response_format={"type": "json_object"},
                **kwargs
            )
            
            # Report actual token usage
            if hasattr(response, 'usage'):
                await self.token_client.report_usage(
                    request_id=request_id,
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens
                )
            
            return response
        except Exception as e:
            # Release tokens if API call fails
            await self.token_client.release_tokens(request_id)
            logger.error(f"Error in chat completion: {str(e)}")
            raise
    
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
    
    async def send_prompt(
        self,
        system_prompt: str,
        user_prompt: str,
        variables: Dict[str, Any] = None,
        examples: List[Dict[str, str]] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Send a prompt with the provided system prompt, user prompt, and variables.
        Includes retry logic for token rate limit errors.
        
        Args:
            system_prompt: The system prompt that sets context for the AI.
            user_prompt: The user prompt template with placeholders for variables.
            variables: Dictionary of variables to substitute in the template.
            examples: Optional list of few-shot examples as message dictionaries.
            model: The model to use (defaults to self.default_model).
            temperature: Controls randomness. Higher values mean more random completions.
            max_tokens: The maximum number of tokens to generate.
            **kwargs: Additional parameters to pass to the chat completion.
            
        Returns:
            str: The generated text response.
        """
        # Create a helper function that doesn't use self as first arg to work with our retry helper
        async def _do_send_prompt():
            # Format the prompt with system message, examples, and user message with variable substitution
            messages = self.format_prompt(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                variables=variables,
                examples=examples
            )
            
            # Send the chat completion request
            response = await self.chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            # Extract and return the response text
            return response.choices[0].message.content
            
        # Use our retry helper that will automatically handle waiting for rate limit windows
        try:
            return await with_token_limit_retry(_do_send_prompt, self.token_client, max_retries=3)
        except Exception as e:
            logger.error(f"Error sending prompt: {str(e)}")
            raise 
    
    async def structured_completion(
        self,
        response_model: Type[T],
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        max_retries: int = 3,
        **kwargs
    ) -> T:
        """
        Generate a structured completion using Instructor for Pydantic model validation.
        Includes retry logic for token rate limit errors.
        
        Args:
            response_model: Pydantic model class for response validation
            messages: List of messages for the conversation
            model: Model to use (defaults to self.default_model)
            temperature: Temperature for generation (defaults to 0.0 for deterministic outputs)
            max_tokens: Maximum tokens to generate
            max_retries: Maximum retries for validation failures
            **kwargs: Additional parameters for the completion
            
        Returns:
            T: Validated Pydantic model instance
            
        Raises:
            ValidationError: If response doesn't match the schema after retries
            ValueError: If token limit would be exceeded
        """
        model = model or self.default_model
        
        # Create a helper function that doesn't use self as first arg to work with our retry helper
        async def _do_structured_completion():
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
                    max_retries=max_retries,
                    **kwargs
                )
                
                logger.debug("Successfully received and validated structured response")
                return response
                
            except ValidationError as e:
                logger.error(f"Validation error in structured completion: {str(e)}")
                raise
            except Exception as e:
                logger.error(f"Error in structured completion: {str(e)}")
                raise
            finally:
                # Always release tokens
                await self.token_client.release_tokens(request_id)
        
        # Use our retry helper that will automatically handle waiting for rate limit windows
        try:
            return await with_token_limit_retry(_do_structured_completion, self.token_client, max_retries=3)
        except Exception as e:
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
        max_retries: int = 3,
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
            max_retries=max_retries,
            **kwargs
        ) 