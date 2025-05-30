"""
Comprehensive unit tests for common_new.azure_openai_service module.
"""
import pytest
import os
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from pydantic import BaseModel
from common_new.azure_openai_service import AzureOpenAIService


class TestModel(BaseModel):
    """Test Pydantic model for structured output tests."""
    name: str
    age: int
    description: str


class TestAzureOpenAIServiceInit:
    """Test AzureOpenAIService initialization."""
    
    @pytest.mark.unit
    def test_init_with_env_vars(self):
        """Test initialization with environment variables."""
        env_vars = {
            'APP_OPENAI_API_VERSION': '2023-12-01-preview',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4',
            'COUNTER_APP_BASE_URL': 'http://counter.test.com'
        }
        
        with patch.dict(os.environ, env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider') as mock_token_provider:
                with patch('common_new.azure_openai_service.AzureOpenAI') as mock_client:
                    with patch('common_new.azure_openai_service.TokenClient') as mock_token_client:
                        with patch('instructor.from_openai') as mock_instructor:
                            service = AzureOpenAIService(app_id="test-app")
                            
                            assert service.api_version == '2023-12-01-preview'
                            assert service.azure_endpoint == 'https://test.openai.azure.com/'
                            assert service.default_model == 'gpt-4'
                            assert service.app_id == "test-app"
                            mock_token_client.assert_called_once()
                            mock_client.assert_called_once()
                            mock_instructor.assert_called_once()
    
    @pytest.mark.unit
    def test_init_with_custom_model(self):
        """Test initialization with custom model override."""
        env_vars = {
            'APP_OPENAI_API_VERSION': '2023-12-01-preview',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4'
        }
        
        with patch.dict(os.environ, env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider'):
                with patch('common_new.azure_openai_service.AzureOpenAI'):
                    with patch('common_new.azure_openai_service.TokenClient'):
                        with patch('instructor.from_openai'):
                            service = AzureOpenAIService(model="gpt-3.5-turbo", app_id="test-app")
                            
                            assert service.default_model == "gpt-3.5-turbo"
    
    @pytest.mark.unit
    def test_init_missing_env_vars(self):
        """Test initialization fails with missing environment variables."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="APP_OPENAI_API_VERSION and APP_OPENAI_API_BASE must be set"):
                AzureOpenAIService(app_id="test-app")


class TestAzureOpenAIServiceTokenCounting:
    """Test token counting functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.env_vars = {
            'APP_OPENAI_API_VERSION': '2023-12-01-preview',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4'
        }
    
    @pytest.mark.unit
    def test_get_encoding_for_model_known_model(self):
        """Test getting encoding for known model."""
        with patch.dict(os.environ, self.env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider'):
                with patch('common_new.azure_openai_service.AzureOpenAI'):
                    with patch('common_new.azure_openai_service.TokenClient'):
                        with patch('instructor.from_openai'):
                            with patch('tiktoken.encoding_for_model') as mock_encoding:
                                mock_encoding.return_value = "test_encoding"
                                
                                service = AzureOpenAIService(app_id="test-app")
                                encoding = service._get_encoding_for_model("gpt-4")
                                
                                assert encoding == "test_encoding"
                                mock_encoding.assert_called_once_with("gpt-4")
    
    @pytest.mark.unit
    def test_get_encoding_for_model_unknown_model(self):
        """Test getting encoding for unknown model falls back to cl100k_base."""
        with patch.dict(os.environ, self.env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider'):
                with patch('common_new.azure_openai_service.AzureOpenAI'):
                    with patch('common_new.azure_openai_service.TokenClient'):
                        with patch('instructor.from_openai'):
                            with patch('tiktoken.encoding_for_model', side_effect=KeyError("Model not found")):
                                with patch('tiktoken.get_encoding') as mock_get_encoding:
                                    mock_get_encoding.return_value = "fallback_encoding"
                                    
                                    service = AzureOpenAIService(app_id="test-app")
                                    encoding = service._get_encoding_for_model("unknown-model")
                                    
                                    assert encoding == "fallback_encoding"
                                    mock_get_encoding.assert_called_once_with("cl100k_base")
    
    @pytest.mark.unit
    def test_count_tokens_for_message(self):
        """Test token counting for individual message."""
        with patch.dict(os.environ, self.env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider'):
                with patch('common_new.azure_openai_service.AzureOpenAI'):
                    with patch('common_new.azure_openai_service.TokenClient'):
                        with patch('instructor.from_openai'):
                            service = AzureOpenAIService(app_id="test-app")
                            
                            mock_encoding = Mock()
                            mock_encoding.encode.return_value = [1, 2, 3, 4, 5]  # 5 tokens
                            
                            message = {"content": "Hello world", "role": "user"}
                            token_count = service._count_tokens_for_message(message, mock_encoding)
                            
                            assert token_count == 9  # 5 content tokens + 4 metadata tokens
    
    @pytest.mark.unit
    def test_count_tokens_for_message_with_name(self):
        """Test token counting for message with name field."""
        with patch.dict(os.environ, self.env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider'):
                with patch('common_new.azure_openai_service.AzureOpenAI'):
                    with patch('common_new.azure_openai_service.TokenClient'):
                        with patch('instructor.from_openai'):
                            service = AzureOpenAIService(app_id="test-app")
                            
                            mock_encoding = Mock()
                            mock_encoding.encode.side_effect = lambda text: [1] * len(text.split())
                            
                            message = {"content": "Hello world", "role": "user", "name": "test_user"}
                            token_count = service._count_tokens_for_message(message, mock_encoding)
                            
                            # 2 (content) + 1 (name) + 4 (metadata) = 7 tokens
                            assert token_count == 7
    
    @pytest.mark.unit
    def test_estimate_token_count(self):
        """Test estimation of total token count for request."""
        with patch.dict(os.environ, self.env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider'):
                with patch('common_new.azure_openai_service.AzureOpenAI'):
                    with patch('common_new.azure_openai_service.TokenClient'):
                        with patch('instructor.from_openai'):
                            service = AzureOpenAIService(app_id="test-app")
                            
                            with patch.object(service, '_get_encoding_for_model') as mock_get_encoding:
                                with patch.object(service, '_count_tokens_for_message', return_value=10):
                                    messages = [
                                        {"content": "Hello", "role": "user"},
                                        {"content": "Hi there", "role": "assistant"}
                                    ]
                                    
                                    total_tokens = service._estimate_token_count(messages, "gpt-4", max_tokens=100)
                                    
                                    # 3 (base) + 2*10 (messages) + 100 (completion) = 123 tokens
                                    assert total_tokens == 123


class TestAzureOpenAIServiceChatCompletion:
    """Test chat completion functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.env_vars = {
            'APP_OPENAI_API_VERSION': '2023-12-01-preview',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4'
        }
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_chat_completion_success(self):
        """Test successful chat completion."""
        with patch.dict(os.environ, self.env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider'):
                mock_client = Mock()
                mock_client.chat.completions.create.return_value = {
                    "choices": [{"message": {"content": "Hello!"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
                }
                
                with patch('common_new.azure_openai_service.AzureOpenAI', return_value=mock_client):
                    mock_token_client = Mock()
                    mock_token_client.lock_tokens = AsyncMock(return_value=(True, "req_123", None))
                    mock_token_client.report_usage = AsyncMock(return_value=True)
                    
                    with patch('common_new.azure_openai_service.TokenClient', return_value=mock_token_client):
                        with patch('instructor.from_openai'):
                            service = AzureOpenAIService(app_id="test-app")
                            
                            with patch.object(service, '_estimate_token_count', return_value=100):
                                with patch('common_new.azure_openai_service.with_token_limit_retry') as mock_retry:
                                    mock_retry.return_value = {
                                        "choices": [{"message": {"content": "Hello!"}}],
                                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
                                    }
                                    
                                    messages = [{"content": "Hi", "role": "user"}]
                                    result = await service.chat_completion(messages)
                                    
                                    assert result["choices"][0]["message"]["content"] == "Hello!"
                                    mock_token_client.lock_tokens.assert_called_once_with(100)
                                    mock_token_client.report_usage.assert_called_once_with("req_123", 10, 5)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_chat_completion_token_lock_failed(self):
        """Test chat completion when token lock fails."""
        with patch.dict(os.environ, self.env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider'):
                with patch('common_new.azure_openai_service.AzureOpenAI'):
                    mock_token_client = Mock()
                    mock_token_client.lock_tokens = AsyncMock(return_value=(False, None, "Rate limit exceeded"))
                    
                    with patch('common_new.azure_openai_service.TokenClient', return_value=mock_token_client):
                        with patch('instructor.from_openai'):
                            service = AzureOpenAIService(app_id="test-app")
                            
                            with patch.object(service, '_estimate_token_count', return_value=100):
                                messages = [{"content": "Hi", "role": "user"}]
                                
                                with pytest.raises(ValueError, match="Token limit would be exceeded"):
                                    await service.chat_completion(messages)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_chat_completion_with_custom_params(self):
        """Test chat completion with custom parameters."""
        with patch.dict(os.environ, self.env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider'):
                mock_client = Mock()
                
                with patch('common_new.azure_openai_service.AzureOpenAI', return_value=mock_client):
                    mock_token_client = Mock()
                    mock_token_client.lock_tokens = AsyncMock(return_value=(True, "req_123", None))
                    mock_token_client.report_usage = AsyncMock(return_value=True)
                    
                    with patch('common_new.azure_openai_service.TokenClient', return_value=mock_token_client):
                        with patch('instructor.from_openai'):
                            service = AzureOpenAIService(app_id="test-app")
                            
                            with patch.object(service, '_estimate_token_count', return_value=100):
                                with patch('common_new.azure_openai_service.with_token_limit_retry') as mock_retry:
                                    mock_retry.return_value = {"choices": [{"message": {"content": "Response"}}]}
                                    
                                    messages = [{"content": "Hi", "role": "user"}]
                                    await service.chat_completion(
                                        messages,
                                        model="gpt-3.5-turbo",
                                        temperature=0.5,
                                        max_tokens=200,
                                        top_p=0.9
                                    )
                                    
                                    # Verify the retry function was called with correct parameters
                                    mock_retry.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_chat_completion_report_usage_failure(self):
        """Test chat completion when usage reporting fails."""
        with patch.dict(os.environ, self.env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider'):
                with patch('common_new.azure_openai_service.AzureOpenAI'):
                    mock_token_client = Mock()
                    mock_token_client.lock_tokens = AsyncMock(return_value=(True, "req_123", None))
                    mock_token_client.report_usage = AsyncMock(return_value=False)  # Reporting fails
                    
                    with patch('common_new.azure_openai_service.TokenClient', return_value=mock_token_client):
                        with patch('instructor.from_openai'):
                            service = AzureOpenAIService(app_id="test-app")
                            
                            with patch.object(service, '_estimate_token_count', return_value=100):
                                with patch('common_new.azure_openai_service.with_token_limit_retry') as mock_retry:
                                    mock_retry.return_value = {
                                        "choices": [{"message": {"content": "Hello!"}}],
                                        "usage": {"prompt_tokens": 10, "completion_tokens": 5}
                                    }
                                    
                                    messages = [{"content": "Hi", "role": "user"}]
                                    result = await service.chat_completion(messages)
                                    
                                    # Should still return result despite reporting failure
                                    assert result["choices"][0]["message"]["content"] == "Hello!"


class TestAzureOpenAIServiceStructuredOutput:
    """Test structured output functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.env_vars = {
            'APP_OPENAI_API_VERSION': '2023-12-01-preview',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4'
        }
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_structured_completion_success(self):
        """Test successful structured completion."""
        with patch.dict(os.environ, self.env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider'):
                with patch('common_new.azure_openai_service.AzureOpenAI'):
                    mock_token_client = Mock()
                    mock_token_client.lock_tokens = AsyncMock(return_value=(True, "req_123", None))
                    mock_token_client.report_usage = AsyncMock(return_value=True)
                    
                    with patch('common_new.azure_openai_service.TokenClient', return_value=mock_token_client):
                        mock_instructor_client = Mock()
                        mock_instructor_client.chat.completions.create.return_value = TestModel(
                            name="John Doe",
                            age=30,
                            description="A test person"
                        )
                        
                        with patch('instructor.from_openai', return_value=mock_instructor_client):
                            service = AzureOpenAIService(app_id="test-app")
                            
                            with patch.object(service, '_estimate_token_count', return_value=100):
                                with patch('common_new.azure_openai_service.with_token_limit_retry') as mock_retry:
                                    mock_retry.return_value = TestModel(name="John Doe", age=30, description="A test person")
                                    
                                    messages = [{"content": "Create a person", "role": "user"}]
                                    result = await service.structured_completion(messages, TestModel)
                                    
                                    assert isinstance(result, TestModel)
                                    assert result.name == "John Doe"
                                    assert result.age == 30
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_structured_completion_validation_error(self):
        """Test structured completion with validation error."""
        with patch.dict(os.environ, self.env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider'):
                with patch('common_new.azure_openai_service.AzureOpenAI'):
                    mock_token_client = Mock()
                    mock_token_client.lock_tokens = AsyncMock(return_value=(True, "req_123", None))
                    mock_token_client.report_usage = AsyncMock(return_value=True)
                    
                    with patch('common_new.azure_openai_service.TokenClient', return_value=mock_token_client):
                        with patch('instructor.from_openai'):
                            service = AzureOpenAIService(app_id="test-app")
                            
                            with patch.object(service, '_estimate_token_count', return_value=100):
                                from pydantic import ValidationError
                                with patch('common_new.azure_openai_service.with_token_limit_retry', side_effect=ValidationError([], TestModel)):
                                    messages = [{"content": "Create invalid data", "role": "user"}]
                                    
                                    with pytest.raises(ValidationError):
                                        await service.structured_completion(messages, TestModel)


class TestAzureOpenAIServiceEmbeddings:
    """Test embedding functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.env_vars = {
            'APP_OPENAI_API_VERSION': '2023-12-01-preview',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4'
        }
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_create_embeddings_success(self):
        """Test successful embedding creation."""
        with patch.dict(os.environ, self.env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider'):
                mock_client = Mock()
                mock_client.embeddings.create.return_value = {
                    "data": [{"embedding": [0.1, 0.2, 0.3]}],
                    "usage": {"prompt_tokens": 5, "total_tokens": 5}
                }
                
                with patch('common_new.azure_openai_service.AzureOpenAI', return_value=mock_client):
                    mock_token_client = Mock()
                    mock_token_client.lock_tokens = AsyncMock(return_value=(True, "req_123", None))
                    mock_token_client.report_usage = AsyncMock(return_value=True)
                    
                    with patch('common_new.azure_openai_service.TokenClient', return_value=mock_token_client):
                        with patch('instructor.from_openai'):
                            service = AzureOpenAIService(app_id="test-app")
                            
                            with patch('common_new.azure_openai_service.with_token_limit_retry') as mock_retry:
                                mock_retry.return_value = {
                                    "data": [{"embedding": [0.1, 0.2, 0.3]}],
                                    "usage": {"prompt_tokens": 5, "total_tokens": 5}
                                }
                                
                                result = await service.create_embeddings("test text", model="text-embedding-ada-002")
                                
                                assert result["data"][0]["embedding"] == [0.1, 0.2, 0.3]
                                mock_token_client.report_usage.assert_called_once_with("req_123", 5, 0)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_create_embeddings_multiple_texts(self):
        """Test embedding creation with multiple texts."""
        with patch.dict(os.environ, self.env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider'):
                with patch('common_new.azure_openai_service.AzureOpenAI'):
                    mock_token_client = Mock()
                    mock_token_client.lock_tokens = AsyncMock(return_value=(True, "req_123", None))
                    mock_token_client.report_usage = AsyncMock(return_value=True)
                    
                    with patch('common_new.azure_openai_service.TokenClient', return_value=mock_token_client):
                        with patch('instructor.from_openai'):
                            service = AzureOpenAIService(app_id="test-app")
                            
                            with patch('common_new.azure_openai_service.with_token_limit_retry') as mock_retry:
                                mock_retry.return_value = {
                                    "data": [
                                        {"embedding": [0.1, 0.2]},
                                        {"embedding": [0.3, 0.4]}
                                    ],
                                    "usage": {"prompt_tokens": 10, "total_tokens": 10}
                                }
                                
                                result = await service.create_embeddings(
                                    ["text1", "text2"],
                                    model="text-embedding-ada-002"
                                )
                                
                                assert len(result["data"]) == 2
                                assert result["data"][0]["embedding"] == [0.1, 0.2]
                                assert result["data"][1]["embedding"] == [0.3, 0.4]


class TestAzureOpenAIServiceIntegration:
    """Integration tests for AzureOpenAIService."""
    
    def setup_method(self):
        """Set up test environment."""
        self.env_vars = {
            'APP_OPENAI_API_VERSION': '2023-12-01-preview',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4'
        }
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_service_lifecycle(self):
        """Test complete service lifecycle."""
        with patch.dict(os.environ, self.env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider'):
                with patch('common_new.azure_openai_service.AzureOpenAI'):
                    mock_token_client = Mock()
                    mock_token_client.lock_tokens = AsyncMock(return_value=(True, "req_123", None))
                    mock_token_client.report_usage = AsyncMock(return_value=True)
                    
                    with patch('common_new.azure_openai_service.TokenClient', return_value=mock_token_client):
                        with patch('instructor.from_openai'):
                            # Initialize service
                            service = AzureOpenAIService(app_id="test-app")
                            
                            assert service.app_id == "test-app"
                            assert service.default_model == "gpt-4"
                            
                            # Test token counting
                            with patch.object(service, '_get_encoding_for_model') as mock_encoding:
                                mock_encoding.return_value.encode.return_value = [1, 2, 3]
                                
                                token_count = service._estimate_token_count(
                                    [{"content": "test", "role": "user"}],
                                    "gpt-4"
                                )
                                
                                assert token_count > 0
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_error_handling_token_client_failure(self):
        """Test error handling when token client operations fail."""
        with patch.dict(os.environ, self.env_vars):
            with patch('common_new.azure_openai_service.get_bearer_token_provider'):
                with patch('common_new.azure_openai_service.AzureOpenAI'):
                    mock_token_client = Mock()
                    mock_token_client.lock_tokens = AsyncMock(side_effect=Exception("Token client error"))
                    
                    with patch('common_new.azure_openai_service.TokenClient', return_value=mock_token_client):
                        with patch('instructor.from_openai'):
                            service = AzureOpenAIService(app_id="test-app")
                            
                            with patch.object(service, '_estimate_token_count', return_value=100):
                                messages = [{"content": "Hi", "role": "user"}]
                                
                                with pytest.raises(Exception, match="Token client error"):
                                    await service.chat_completion(messages) 