"""
Comprehensive unit tests for common_new.azure_openai_service module.
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pydantic import BaseModel, ValidationError
import os
import tiktoken

from common_new.azure_openai_service import AzureOpenAIService

class _TestModel(BaseModel):
    """Test Pydantic model for structured output tests."""
    name: str
    value: int

class TestAzureOpenAIServiceInit:
    """Test AzureOpenAIService initialization."""
    
    def test_init_with_env_vars(self):
        """Test service initialization with environment variables."""
        with patch.dict(os.environ, {
            'APP_OPENAI_API_VERSION': '2023-05-15',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4'
        }):
            with patch('common_new.azure_openai_service.TokenClient'):
                service = AzureOpenAIService(app_id="test-app", token_counter_url="http://localhost:8001")
                
                assert service.api_version == '2023-05-15'
                assert service.azure_endpoint == 'https://test.openai.azure.com/'
                assert service.default_model == 'gpt-4'
                assert service.app_id == 'test-app'

    def test_init_with_custom_model(self):
        """Test service initialization with custom model override."""
        with patch.dict(os.environ, {
            'APP_OPENAI_API_VERSION': '2023-05-15',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-3.5-turbo'
        }):
            with patch('common_new.azure_openai_service.TokenClient'):
                service = AzureOpenAIService(
                    model="gpt-4-32k", 
                    app_id="test-app",
                    token_counter_url="http://localhost:8001"
                )
                
                assert service.default_model == 'gpt-4-32k'

    def test_init_missing_env_vars(self):
        """Test service initialization fails with missing environment variables."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="APP_OPENAI_API_VERSION and APP_OPENAI_API_BASE must be set"):
                AzureOpenAIService(app_id="test-app", token_counter_url="http://localhost:8001")

class TestAzureOpenAIServiceTokenCounting:
    """Test token counting functionality."""
    
    def test_get_encoding_for_model_known_model(self):
        """Test getting encoding for a known model."""
        with patch.dict(os.environ, {
            'APP_OPENAI_API_VERSION': '2023-05-15',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4'
        }):
            with patch('common_new.azure_openai_service.TokenClient'):
                service = AzureOpenAIService(app_id="test-app", token_counter_url="http://localhost:8001")
                
                encoding = service._get_encoding_for_model("gpt-4")
                assert encoding is not None

    def test_get_encoding_for_model_unknown_model(self):
        """Test getting encoding for an unknown model falls back to cl100k_base."""
        with patch.dict(os.environ, {
            'APP_OPENAI_API_VERSION': '2023-05-15',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4'
        }):
            with patch('common_new.azure_openai_service.TokenClient'):
                service = AzureOpenAIService(app_id="test-app", token_counter_url="http://localhost:8001")
                
                with patch('tiktoken.encoding_for_model', side_effect=KeyError("Model not found")):
                    with patch('tiktoken.get_encoding') as mock_get_encoding:
                        mock_encoding = Mock()
                        mock_get_encoding.return_value = mock_encoding
                        
                        encoding = service._get_encoding_for_model("unknown-model")
                        
                        mock_get_encoding.assert_called_once_with("cl100k_base")
                        assert encoding == mock_encoding

    def test_count_tokens_for_message(self):
        """Test counting tokens for a message."""
        with patch.dict(os.environ, {
            'APP_OPENAI_API_VERSION': '2023-05-15',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4'
        }):
            with patch('common_new.azure_openai_service.TokenClient'):
                service = AzureOpenAIService(app_id="test-app", token_counter_url="http://localhost:8001")
                
                mock_encoding = Mock()
                mock_encoding.encode.return_value = [1, 2, 3, 4, 5]  # 5 tokens
                
                message = {"role": "user", "content": "Hello world"}
                token_count = service._count_tokens_for_message(message, mock_encoding)
                
                # 5 tokens for content + 4 for metadata = 9 tokens
                assert token_count == 9

    def test_count_tokens_for_message_with_name(self):
        """Test counting tokens for a message with name field."""
        with patch.dict(os.environ, {
            'APP_OPENAI_API_VERSION': '2023-05-15',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4'
        }):
            with patch('common_new.azure_openai_service.TokenClient'):
                service = AzureOpenAIService(app_id="test-app", token_counter_url="http://localhost:8001")
                
                mock_encoding = Mock()
                mock_encoding.encode.side_effect = lambda text: [1] * len(text.split())
                
                message = {"role": "user", "content": "Hello world", "name": "TestUser"}
                token_count = service._count_tokens_for_message(message, mock_encoding)
                
                # 2 tokens for content + 1 token for name + 4 for metadata = 7 tokens
                assert token_count == 7

    def test_estimate_token_count(self):
        """Test estimating token count for a list of messages."""
        with patch.dict(os.environ, {
            'APP_OPENAI_API_VERSION': '2023-05-15',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4'
        }):
            with patch('common_new.azure_openai_service.TokenClient'):
                service = AzureOpenAIService(app_id="test-app", token_counter_url="http://localhost:8001")
                
                with patch.object(service, '_get_encoding_for_model') as mock_encoding_getter:
                    mock_encoding = Mock()
                    mock_encoding.encode.return_value = [1, 2, 3]  # 3 tokens per message
                    mock_encoding_getter.return_value = mock_encoding
                    
                    messages = [
                        {"role": "user", "content": "Hello"},
                        {"role": "assistant", "content": "Hi there"}
                    ]
                    
                    estimated = service._estimate_token_count(messages, "gpt-4", max_tokens=100)
                    
                    # 3 base + 2 messages * (3 content + 4 metadata) + 100 completion = 117
                    assert estimated == 117

@pytest.mark.asyncio
class TestAzureOpenAIServiceStructuredOutput:
    """Test structured output functionality."""

    async def test_structured_completion_success(self):
        """Test successful structured completion."""
        with patch.dict(os.environ, {
            'APP_OPENAI_API_VERSION': '2023-05-15',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4'
        }):
            mock_token_client = AsyncMock()
            mock_token_client.lock_tokens.return_value = (True, "req_123", "")
            mock_token_client.report_usage.return_value = None
            
            with patch('common_new.azure_openai_service.TokenClient', return_value=mock_token_client):
                service = AzureOpenAIService(app_id="test-app", token_counter_url="http://localhost:8001")
                
                # Mock the instructor response
                mock_response = _TestModel(name="test", value=42)
                mock_response._raw_response = Mock()
                mock_response._raw_response.usage = Mock()
                mock_response._raw_response.usage.prompt_tokens = 20
                mock_response._raw_response.usage.completion_tokens = 10
                
                service.instructor_client.chat.completions.create = Mock(return_value=mock_response)
                
                messages = [{"role": "user", "content": "Generate test data"}]
                result = await service.structured_completion(_TestModel, messages)
                
                assert isinstance(result, _TestModel)
                assert result.name == "test"
                assert result.value == 42
                
                mock_token_client.report_usage.assert_called_once_with(
                    request_id="req_123", 
                    prompt_tokens=20, 
                    completion_tokens=10
                )

    async def test_structured_completion_validation_error(self):
        """Test structured completion with validation error."""
        with patch.dict(os.environ, {
            'APP_OPENAI_API_VERSION': '2023-05-15',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4'
        }):
            mock_token_client = AsyncMock()
            mock_token_client.lock_tokens.return_value = (True, "req_123", "")
            mock_token_client.release_tokens.return_value = None
            
            with patch('common_new.azure_openai_service.TokenClient', return_value=mock_token_client):
                service = AzureOpenAIService(app_id="test-app", token_counter_url="http://localhost:8001")
                
                # Create a proper ValidationError
                validation_error = ValidationError.from_exception_data("_TestModel", [
                    {
                        'type': 'missing',
                        'loc': ('name',),
                        'msg': 'Field required',
                        'input': {}
                    }
                ])
                
                service.instructor_client.chat.completions.create = Mock(side_effect=validation_error)
                
                messages = [{"role": "user", "content": "Generate invalid data"}]
                
                with pytest.raises(ValidationError):
                    await service.structured_completion(_TestModel, messages)
                
                mock_token_client.release_tokens.assert_called_once_with("req_123")

@pytest.mark.asyncio
class TestAzureOpenAIServiceIntegration:
    """Integration tests for AzureOpenAIService."""

    async def test_service_lifecycle(self):
        """Test complete service lifecycle."""
        with patch.dict(os.environ, {
            'APP_OPENAI_API_VERSION': '2023-05-15',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4'
        }):
            mock_token_client = AsyncMock()
            mock_token_client.lock_tokens.return_value = (True, "req_123", "")
            
            with patch('common_new.azure_openai_service.TokenClient', return_value=mock_token_client):
                service = AzureOpenAIService(app_id="test-app", token_counter_url="http://localhost:8001")
                
                # Test service is properly initialized
                assert service.api_version == '2023-05-15'
                assert service.azure_endpoint == 'https://test.openai.azure.com/'
                assert service.default_model == 'gpt-4'
                assert service.app_id == 'test-app'
                assert service.token_client is not None
                assert service.client is not None
                assert service.instructor_client is not None

    async def test_error_handling_token_client_failure(self):
        """Test error handling when token client operations fail."""
        with patch.dict(os.environ, {
            'APP_OPENAI_API_VERSION': '2023-05-15',
            'APP_OPENAI_API_BASE': 'https://test.openai.azure.com/',
            'APP_OPENAI_ENGINE': 'gpt-4'
        }):
            mock_token_client = AsyncMock()
            mock_token_client.lock_tokens.side_effect = Exception("Token client error")
            
            with patch('common_new.azure_openai_service.TokenClient', return_value=mock_token_client):
                service = AzureOpenAIService(app_id="test-app", token_counter_url="http://localhost:8001")
                
                messages = [{"role": "user", "content": "Hello"}]
                
                with pytest.raises(Exception, match="Token client error"):
                    await service.chat_completion(messages) 