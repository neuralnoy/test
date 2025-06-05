"""
Azure OpenAI Embedding Service for converting text to vector embeddings.

Required Environment Variables:
- APP_EMBEDDING_API_BASE: Azure OpenAI embedding endpoint URL
- APP_EMBEDDING_API_VERSION: API version (defaults to 2024-02-01)
- APP_EMBEDDING_ENGINE: Embedding model deployment name (defaults to text-embedding-3-large)
- COUNTER_APP_BASE_URL: Token counter service URL
"""
import os
import tiktoken
from typing import List, Optional, Union

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI
from dotenv import load_dotenv
from common_new.logger import get_logger
from common_new.token_client import TokenClient

load_dotenv()

logger = get_logger("common")

COUNTER_BASE_URL = os.getenv("COUNTER_APP_BASE_URL")

class AzureEmbeddingService:
    """
    Service for generating text embeddings using Azure-hosted OpenAI embedding models.
    Provides functionality for authentication, token tracking, and embedding generation.
    """
    
    def __init__(self, model: Optional[str] = None, app_id: str = "default_app", token_counter_url: str = COUNTER_BASE_URL):
        """
        Initialize the Azure OpenAI embedding service with credentials from environment variables.
        
        Args:
            model: Optional embedding model to use. If not specified, uses text-embedding-3-large.
            app_id: ID of the application using this service. Used for token tracking.
            token_counter_url: URL of the token counter service.
        """
        self.api_version = os.getenv("APP_EMBEDDING_API_VERSION", "2024-02-01")
        self.azure_endpoint = os.getenv("APP_EMBEDDING_API_BASE")
        self.default_model = model or os.getenv("APP_EMBEDDING_ENGINE", "text-embedding-3-large")
        self.app_id = app_id
        
        # Authentication setup - identical to the main service
        self.token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default"
        )
        
        self.token_client = TokenClient(app_id=app_id, base_url=token_counter_url)
        
        if not self.azure_endpoint:
            raise ValueError("APP_EMBEDDING_API_BASE must be set in .env file or exported as environment variables")
        
        logger.info(f"Initializing Azure OpenAI embedding service with endpoint: {self.azure_endpoint}")
        logger.info(f"Using embedding model: {self.default_model}")
        
        self.client = self._initialize_client()
    
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
    
    def _get_encoding_for_model(self, model: str) -> tiktoken.Encoding:
        """
        Get the correct tokenizer for the specified embedding model.
        
        Args:
            model: Model name or deployment name
            
        Returns:
            Tiktoken encoding for the model
        """
        try:
            # For embedding models, most use cl100k_base encoding
            if any(x in model.lower() for x in ["ada-002", "text-embedding-3", "text-embedding"]):
                return tiktoken.get_encoding("cl100k_base")
            else:
                # Try to get direct encoding first
                try:
                    return tiktoken.encoding_for_model(model)
                except KeyError:
                    logger.warning(f"Model {model} not found, falling back to cl100k_base encoding")
                    return tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Error getting encoding for model {model}: {str(e)}. Falling back to cl100k_base encoding.")
            return tiktoken.get_encoding("cl100k_base")
    
    def _estimate_tokens(self, texts: Union[str, List[str]], model: str) -> int:
        """
        Estimate token count for embedding request.
        
        Args:
            texts: Text or list of texts to embed
            model: Model to use for token counting
            
        Returns:
            int: Estimated token count
        """
        if isinstance(texts, str):
            texts = [texts]
        
        encoding = self._get_encoding_for_model(model)
        
        total_tokens = 0
        for text in texts:
            total_tokens += len(encoding.encode(text))
        
        return total_tokens
    
    async def create_embedding(
        self,
        text: Union[str, List[str]],
        model: Optional[str] = None,
        user: Optional[str] = None
    ) -> List[List[float]]:
        """
        Create embeddings for the given text(s).
        
        Args:
            text: Text string or list of text strings to embed
            model: Model to use (defaults to self.default_model)
            user: Optional user identifier for tracking
            
        Returns:
            List[List[float]]: List of embedding vectors
            
        Raises:
            ValueError: If token limit would be exceeded
        """
        model = model or self.default_model
        
        # Ensure text is a list for consistent processing
        if isinstance(text, str):
            texts = [text]
            single_text = True
        else:
            texts = text
            single_text = False
        
        # Estimate token usage
        estimated_tokens = self._estimate_tokens(texts, model)
        
        # Check embedding token availability
        allowed, request_id, error_message = await self.token_client.lock_embedding_tokens(estimated_tokens)
        
        if not allowed:
            logger.warning(f"Embedding request denied: {error_message}")
            raise ValueError(error_message)
        
        try:
            logger.debug(f"Creating embeddings for {len(texts)} text(s) using model: {model}")
            
            # Create embeddings
            response = self.client.embeddings.create(
                model=model,
                input=texts,
                user=user
            )
            
            # Report actual embedding token usage
            if hasattr(response, 'usage') and response.usage:
                await self.token_client.report_embedding_usage(
                    request_id=request_id,
                    prompt_tokens=response.usage.prompt_tokens
                )
            
            # Extract embeddings from response
            embeddings = [data.embedding for data in response.data]
            
            logger.debug(f"Successfully created {len(embeddings)} embeddings")
            
            # Return single embedding if single text was provided
            if single_text:
                return embeddings[0]
            return embeddings
            
        except Exception as e:
            # Release embedding tokens if API call fails
            await self.token_client.release_embedding_tokens(request_id)
            logger.error(f"Error creating embeddings: {str(e)}")
            raise
    
    async def create_embedding_batch(
        self,
        texts: List[str],
        model: Optional[str] = None,
        batch_size: int = 100,
        user: Optional[str] = None
    ) -> List[List[float]]:
        """
        Create embeddings for a large batch of texts, processing in smaller chunks.
        
        Args:
            texts: List of text strings to embed
            model: Model to use (defaults to self.default_model)
            batch_size: Number of texts to process in each batch
            user: Optional user identifier for tracking
            
        Returns:
            List[List[float]]: List of embedding vectors
        """
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1} of {(len(texts) + batch_size - 1)//batch_size}")
            
            batch_embeddings = await self.create_embedding(
                text=batch,
                model=model,
                user=user
            )
            
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings
    