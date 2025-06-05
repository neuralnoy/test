"""
Comprehensive unit tests for common_new.azure_embedding_service module.
"""
import pytest
import os
from unittest.mock import patch, Mock, AsyncMock

from common_new.azure_embedding_service import AzureEmbeddingService


class TestAzureEmbeddingServiceInit:
    """Test AzureEmbeddingService initialization."""
    
    def test_init_missing_required_env_var(self):
        """Test service initialization fails with missing required environment variable APP_EMBEDDING_API_BASE."""
        # Clear environment variables to simulate missing configuration
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="APP_EMBEDDING_API_BASE must be set in .env file or exported as environment variables"):
                AzureEmbeddingService(app_id="test-app", token_counter_url="http://localhost:8001")
    
    def test_init_with_env_vars(self):
        """Test service initialization with environment variables."""
        with patch.dict(os.environ, {
            'APP_EMBEDDING_API_VERSION': '2024-02-01',
            'APP_EMBEDDING_API_BASE': 'https://test-embedding.openai.azure.com/',
            'APP_EMBEDDING_ENGINE': 'text-embedding-3-large'
        }):
            with patch('common_new.azure_embedding_service.TokenClient') as mock_token_client:
                with patch('common_new.azure_embedding_service.DefaultAzureCredential'):
                    with patch('common_new.azure_embedding_service.get_bearer_token_provider'):
                        with patch('common_new.azure_embedding_service.AzureOpenAI'):
                            service = AzureEmbeddingService(app_id="test-app", token_counter_url="http://localhost:8001")
                            
                            assert service.api_version == '2024-02-01'
                            assert service.azure_endpoint == 'https://test-embedding.openai.azure.com/'
                            assert service.default_model == 'text-embedding-3-large'
                            assert service.app_id == 'test-app'
                            
                            # Verify TokenClient was initialized with correct parameters
                            mock_token_client.assert_called_once_with(
                                app_id="test-app", 
                                base_url="http://localhost:8001"
                            )
    
    def test_init_with_custom_model_override(self):
        """Test service initialization with custom model parameter overriding environment variable."""
        with patch.dict(os.environ, {
            'APP_EMBEDDING_API_VERSION': '2024-02-01',
            'APP_EMBEDDING_API_BASE': 'https://test-embedding.openai.azure.com/',
            'APP_EMBEDDING_ENGINE': 'text-embedding-3-large'  # This should be overridden
        }):
            with patch('common_new.azure_embedding_service.TokenClient'):
                with patch('common_new.azure_embedding_service.DefaultAzureCredential'):
                    with patch('common_new.azure_embedding_service.get_bearer_token_provider'):
                        with patch('common_new.azure_embedding_service.AzureOpenAI'):
                            service = AzureEmbeddingService(
                                model="text-embedding-ada-002",  # Custom model override
                                app_id="test-app", 
                                token_counter_url="http://localhost:8001"
                            )
                            
                            # Custom model should take precedence over environment variable
                            assert service.default_model == 'text-embedding-ada-002'
                            assert service.api_version == '2024-02-01'
                            assert service.azure_endpoint == 'https://test-embedding.openai.azure.com/'


class TestAzureEmbeddingServiceTokenCounting:
    """Test token counting and encoding functionality."""
    
    def test_get_encoding_for_known_embedding_model(self):
        """Test getting encoding for a known embedding model."""
        with patch.dict(os.environ, {
            'APP_EMBEDDING_API_BASE': 'https://test-embedding.openai.azure.com/',
        }):
            with patch('common_new.azure_embedding_service.TokenClient'):
                with patch('common_new.azure_embedding_service.DefaultAzureCredential'):
                    with patch('common_new.azure_embedding_service.get_bearer_token_provider'):
                        with patch('common_new.azure_embedding_service.AzureOpenAI'):
                            service = AzureEmbeddingService(app_id="test-app", token_counter_url="http://localhost:8001")
                            
                            # Test known embedding models
                            with patch('tiktoken.get_encoding') as mock_get_encoding:
                                mock_encoding = Mock()
                                mock_get_encoding.return_value = mock_encoding
                                
                                encoding = service._get_encoding_for_model("text-embedding-3-large")
                                
                                mock_get_encoding.assert_called_once_with("cl100k_base")
                                assert encoding == mock_encoding
    
    def test_get_encoding_for_unknown_model_fallback(self):
        """Test getting encoding for an unknown model falls back to cl100k_base."""
        with patch.dict(os.environ, {
            'APP_EMBEDDING_API_BASE': 'https://test-embedding.openai.azure.com/',
        }):
            with patch('common_new.azure_embedding_service.TokenClient'):
                with patch('common_new.azure_embedding_service.DefaultAzureCredential'):
                    with patch('common_new.azure_embedding_service.get_bearer_token_provider'):
                        with patch('common_new.azure_embedding_service.AzureOpenAI'):
                            service = AzureEmbeddingService(app_id="test-app", token_counter_url="http://localhost:8001")
                            
                            with patch('tiktoken.encoding_for_model', side_effect=KeyError("Model not found")):
                                with patch('tiktoken.get_encoding') as mock_get_encoding:
                                    mock_encoding = Mock()
                                    mock_get_encoding.return_value = mock_encoding
                                    
                                    encoding = service._get_encoding_for_model("unknown-custom-model")
                                    
                                    mock_get_encoding.assert_called_with("cl100k_base")
                                    assert encoding == mock_encoding
    
    def test_estimate_tokens_single_string(self):
        """Test estimating token count for a single string input."""
        with patch.dict(os.environ, {
            'APP_EMBEDDING_API_BASE': 'https://test-embedding.openai.azure.com/',
        }):
            with patch('common_new.azure_embedding_service.TokenClient'):
                with patch('common_new.azure_embedding_service.DefaultAzureCredential'):
                    with patch('common_new.azure_embedding_service.get_bearer_token_provider'):
                        with patch('common_new.azure_embedding_service.AzureOpenAI'):
                            service = AzureEmbeddingService(app_id="test-app", token_counter_url="http://localhost:8001")
                            
                            # Mock the encoding with a predictable token count
                            with patch.object(service, '_get_encoding_for_model') as mock_get_encoding:
                                mock_encoding = Mock()
                                mock_encoding.encode.return_value = [1, 2, 3, 4, 5]  # 5 tokens
                                mock_get_encoding.return_value = mock_encoding
                                
                                token_count = service._estimate_tokens("Hello world", "text-embedding-3-large")
                                
                                assert token_count == 5
                                mock_encoding.encode.assert_called_once_with("Hello world")
    
    def test_estimate_tokens_list_of_strings(self):
        """Test estimating token count for a list of strings."""
        with patch.dict(os.environ, {
            'APP_EMBEDDING_API_BASE': 'https://test-embedding.openai.azure.com/',
        }):
            with patch('common_new.azure_embedding_service.TokenClient'):
                with patch('common_new.azure_embedding_service.DefaultAzureCredential'):
                    with patch('common_new.azure_embedding_service.get_bearer_token_provider'):
                        with patch('common_new.azure_embedding_service.AzureOpenAI'):
                            service = AzureEmbeddingService(app_id="test-app", token_counter_url="http://localhost:8001")
                            
                            # Mock the encoding with a predictable token count
                            with patch.object(service, '_get_encoding_for_model') as mock_get_encoding:
                                mock_encoding = Mock()
                                mock_encoding.encode.side_effect = [
                                    [1, 2, 3],      # 3 tokens for "Hello"
                                    [1, 2, 3, 4]    # 4 tokens for "World"
                                ]
                                mock_get_encoding.return_value = mock_encoding
                                
                                texts = ["Hello", "World"]
                                token_count = service._estimate_tokens(texts, "text-embedding-3-large")
                                
                                assert token_count == 7  # 3 + 4 = 7 tokens
                                assert mock_encoding.encode.call_count == 2


@pytest.mark.asyncio
class TestAzureEmbeddingServiceEmbedding:
    """Test embedding creation functionality."""
    
    async def test_create_embedding_success(self):
        """Test successful embedding creation for a single text."""
        with patch.dict(os.environ, {
            'APP_EMBEDDING_API_BASE': 'https://test-embedding.openai.azure.com/',
        }):
            # Mock TokenClient
            mock_token_client = AsyncMock()
            mock_token_client.lock_embedding_tokens.return_value = (True, "test-request-id", None)
            mock_token_client.report_embedding_usage.return_value = None
            
            # Mock Azure OpenAI client
            mock_client = Mock()
            mock_response = Mock()
            mock_response.data = [Mock(embedding=[0.1, 0.2, 0.3, 0.4, 0.5])]
            mock_response.usage = Mock(prompt_tokens=10)
            mock_client.embeddings.create.return_value = mock_response
            
            with patch('common_new.azure_embedding_service.TokenClient', return_value=mock_token_client):
                with patch('common_new.azure_embedding_service.DefaultAzureCredential'):
                    with patch('common_new.azure_embedding_service.get_bearer_token_provider'):
                        with patch('common_new.azure_embedding_service.AzureOpenAI', return_value=mock_client):
                            service = AzureEmbeddingService(app_id="test-app", token_counter_url="http://localhost:8001")
                            
                            # Mock token estimation
                            with patch.object(service, '_estimate_tokens', return_value=10):
                                embeddings = await service.create_embedding("Hello world")
                                
                                # Verify results
                                assert len(embeddings) == 1
                                assert embeddings[0] == [0.1, 0.2, 0.3, 0.4, 0.5]
                                
                                # Verify API calls
                                mock_token_client.lock_embedding_tokens.assert_called_once_with(10)
                                mock_client.embeddings.create.assert_called_once_with(
                                    model="text-embedding-3-large",
                                    input=["Hello world"]
                                )
                                mock_token_client.report_embedding_usage.assert_called_once_with(
                                    request_id="test-request-id",
                                    prompt_tokens=10
                                )
    
    async def test_create_embedding_token_limit_exceeded(self):
        """Test embedding creation when token limit is exceeded."""
        with patch.dict(os.environ, {
            'APP_EMBEDDING_API_BASE': 'https://test-embedding.openai.azure.com/',
        }):
            # Mock TokenClient that denies the request
            mock_token_client = AsyncMock()
            mock_token_client.lock_embedding_tokens.return_value = (False, None, "Token limit exceeded")
            
            with patch('common_new.azure_embedding_service.TokenClient', return_value=mock_token_client):
                with patch('common_new.azure_embedding_service.DefaultAzureCredential'):
                    with patch('common_new.azure_embedding_service.get_bearer_token_provider'):
                        with patch('common_new.azure_embedding_service.AzureOpenAI'):
                            service = AzureEmbeddingService(app_id="test-app", token_counter_url="http://localhost:8001")
                            
                            # Mock token estimation
                            with patch.object(service, '_estimate_tokens', return_value=1000):
                                # Should raise ValueError when token limit exceeded
                                with pytest.raises(ValueError, match="Token limit exceeded"):
                                    await service.create_embedding("This is a very long text that exceeds limits")
                                
                                # Verify token lock was attempted
                                mock_token_client.lock_embedding_tokens.assert_called_once_with(1000)
                                
                                # Verify no other token client methods were called
                                mock_token_client.report_embedding_usage.assert_not_called()
                                mock_token_client.release_embedding_tokens.assert_not_called()
    
    async def test_create_embedding_api_failure_with_token_release(self):
        """Test embedding creation API failure triggers token release."""
        with patch.dict(os.environ, {
            'APP_EMBEDDING_API_BASE': 'https://test-embedding.openai.azure.com/',
        }):
            # Mock TokenClient that allows the request
            mock_token_client = AsyncMock()
            mock_token_client.lock_embedding_tokens.return_value = (True, "test-request-id", None)
            mock_token_client.release_embedding_tokens.return_value = None
            
            # Mock Azure OpenAI client that fails
            mock_client = Mock()
            mock_client.embeddings.create.side_effect = Exception("API rate limit exceeded")
            
            with patch('common_new.azure_embedding_service.TokenClient', return_value=mock_token_client):
                with patch('common_new.azure_embedding_service.DefaultAzureCredential'):
                    with patch('common_new.azure_embedding_service.get_bearer_token_provider'):
                        with patch('common_new.azure_embedding_service.AzureOpenAI', return_value=mock_client):
                            service = AzureEmbeddingService(app_id="test-app", token_counter_url="http://localhost:8001")
                            
                            # Mock token estimation
                            with patch.object(service, '_estimate_tokens', return_value=10):
                                # Should raise the API exception
                                with pytest.raises(Exception, match="API rate limit exceeded"):
                                    await service.create_embedding("Hello world")
                                
                                # Verify token operations
                                mock_token_client.lock_embedding_tokens.assert_called_once_with(10)
                                mock_client.embeddings.create.assert_called_once_with(
                                    model="text-embedding-3-large",
                                    input=["Hello world"]
                                )
                                # Verify tokens were released on failure
                                mock_token_client.release_embedding_tokens.assert_called_once_with("test-request-id")
                                
                                # Verify usage was not reported since API failed
                                mock_token_client.report_embedding_usage.assert_not_called()
    
    async def test_create_embedding_batch_success(self):
        """Test successful batch processing of multiple texts."""
        with patch.dict(os.environ, {
            'APP_EMBEDDING_API_BASE': 'https://test-embedding.openai.azure.com/',
        }):
            with patch('common_new.azure_embedding_service.TokenClient'):
                with patch('common_new.azure_embedding_service.DefaultAzureCredential'):
                    with patch('common_new.azure_embedding_service.get_bearer_token_provider'):
                        with patch('common_new.azure_embedding_service.AzureOpenAI'):
                            service = AzureEmbeddingService(app_id="test-app", token_counter_url="http://localhost:8001")
                            
                            # Mock the create_embedding method to return predictable results
                            async def mock_create_embedding(text, model=None):
                                # Return different embeddings for different batches
                                if text == ["Text 1", "Text 2"]:
                                    return [[0.1, 0.2], [0.3, 0.4]]
                                elif text == ["Text 3"]:
                                    return [[0.5, 0.6]]
                                
                            with patch.object(service, 'create_embedding', side_effect=mock_create_embedding) as mock_create:
                                texts = ["Text 1", "Text 2", "Text 3"]
                                embeddings = await service.create_embedding_batch(texts, batch_size=2)
                                
                                # Verify results - should combine all embeddings
                                assert len(embeddings) == 3
                                assert embeddings[0] == [0.1, 0.2]
                                assert embeddings[1] == [0.3, 0.4] 
                                assert embeddings[2] == [0.5, 0.6]
                                
                                # Verify create_embedding was called twice (2 batches)
                                assert mock_create.call_count == 2
                                mock_create.assert_any_call(text=["Text 1", "Text 2"], model=None)
                                mock_create.assert_any_call(text=["Text 3"], model=None)
    
    async def test_create_embedding_batch_large_batch_size(self):
        """Test batch processing when batch size is larger than input list."""
        with patch.dict(os.environ, {
            'APP_EMBEDDING_API_BASE': 'https://test-embedding.openai.azure.com/',
        }):
            with patch('common_new.azure_embedding_service.TokenClient'):
                with patch('common_new.azure_embedding_service.DefaultAzureCredential'):
                    with patch('common_new.azure_embedding_service.get_bearer_token_provider'):
                        with patch('common_new.azure_embedding_service.AzureOpenAI'):
                            service = AzureEmbeddingService(app_id="test-app", token_counter_url="http://localhost:8001")
                            
                            # Mock the create_embedding method
                            async def mock_create_embedding(text, model=None):
                                # Should be called with all texts in one batch
                                if text == ["Text 1", "Text 2"]:
                                    return [[0.1, 0.2], [0.3, 0.4]]
                                
                            with patch.object(service, 'create_embedding', side_effect=mock_create_embedding) as mock_create:
                                texts = ["Text 1", "Text 2"]
                                # Batch size larger than input list
                                embeddings = await service.create_embedding_batch(texts, batch_size=10)
                                
                                # Verify results
                                assert len(embeddings) == 2
                                assert embeddings[0] == [0.1, 0.2]
                                assert embeddings[1] == [0.3, 0.4]
                                
                                # Verify create_embedding was called only once (single batch)
                                assert mock_create.call_count == 1
                                mock_create.assert_called_once_with(text=["Text 1", "Text 2"], model=None) 