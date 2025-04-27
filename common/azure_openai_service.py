"""
Azure OpenAI Service for making API calls to Azure-hosted OpenAI models.
"""
import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Callable

from azure.identity import DefaultAzureCredential
from openai import AzureOpenAI
from dotenv import load_dotenv
from common.logger import get_logger

logger = get_logger("common")

load_dotenv()

class AzureOpenAIService:
    """
    Service for interacting with Azure-hosted OpenAI models.
    Provides functionality for authentication, prompt management, and API calls.
    """
    
    def __init__(self, model: Optional[str] = None):
        """
        Initialize the Azure OpenAI service with credentials from environment variables.
        
        Args:
            model: Optional default model to use. If not specified, uses the AZURE_OPENAI_DEPLOYMENT_NAME from .env.
        """
        self.api_version = os.getenv("AZURE_OPENAI_API_VERSION")
        self.azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.default_model = model or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4")
        
        if not self.api_version or not self.azure_endpoint:
            raise ValueError("AZURE_OPENAI_API_VERSION and AZURE_OPENAI_ENDPOINT must be set in .env file or exported as environment variables")
        
        logger.info(f"Initializing Azure OpenAI service with endpoint: {self.azure_endpoint}")
        self.client = self._initialize_client()
    
    def _get_bearer_token_provider(self) -> Callable[[], str]:
        """
        Get a bearer token provider using Azure Default Credentials.
        
        Returns:
            Callable: A bearer token provider function.
        """
        credential = DefaultAzureCredential()
        scope = f"{self.azure_endpoint}/.default"
        
        def bearer_token_provider():
            token = credential.get_token(scope)
            return token.token
        
        return bearer_token_provider
    
    def _initialize_client(self) -> AzureOpenAI:
        """
        Initialize the Azure OpenAI client with the appropriate configuration.
        
        Returns:
            AzureOpenAI: An initialized Azure OpenAI client.
        """
        return AzureOpenAI(
            api_version=self.api_version,
            azure_endpoint=self.azure_endpoint,
            azure_ad_token_provider=self._get_bearer_token_provider()
        )
    
    def chat_completion(
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
        """
        model = model or self.default_model
        
        logger.debug(f"Sending chat completion request to model: {model}")
        return self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            stop=stop,
            **kwargs
        )
    
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
    
    def send_prompt(
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
        # Format the prompt with system message, examples, and user message with variable substitution
        messages = self.format_prompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            variables=variables,
            examples=examples
        )
        
        # Send the chat completion request
        try:
            response = self.chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            # Extract and return the response text
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error sending prompt: {str(e)}")
            raise 