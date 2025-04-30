import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock, ANY

from common.azure_openai_service import AzureOpenAIService
from common.retry_helpers import RetryConfig

class TestAzureOpenAIService:
    """Test suite for the AzureOpenAIService class"""

    @pytest.fixture
    def mock_openai(self):
        """Mock the openai module"""
        with patch('common.azure_openai_service.openai') as mock_openai:
            # Set up mock response for completion
            mock_completion = MagicMock()
            mock_completion.choices = [MagicMock(message=MagicMock(content="Test response"))]
            mock_completion.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
            
            # Set up mock async client
            mock_openai.AsyncAzureOpenAI.return_value = AsyncMock()
            mock_openai.AsyncAzureOpenAI.return_value.chat.completions.create = AsyncMock(return_value=mock_completion)
            
            yield mock_openai

    @pytest.fixture
    def openai_service(self, mock_openai):
        """Create an Azure OpenAI service for testing"""
        service = AzureOpenAIService(
            endpoint="https://test.openai.azure.com/",
            api_version="2023-05-15",
            deployment_name="gpt-35-turbo"
        )
        return service

    @pytest.mark.asyncio
    async def test_initialize(self, openai_service, mock_openai):
        """Test initialization of the Azure OpenAI service"""
        assert openai_service.endpoint == "https://test.openai.azure.com/"
        assert openai_service.api_version == "2023-05-15"
        assert openai_service.deployment_name == "gpt-35-turbo"
        assert openai_service.client is not None
        mock_openai.AsyncAzureOpenAI.assert_called_once()

    @pytest.mark.asyncio
    async def test_completion_success(self, openai_service, mock_openai):
        """Test successful completion request"""
        result = await openai_service.completion(
            system_prompt="You are a helpful assistant.",
            user_prompt="Tell me a joke."
        )
        
        # Verify client was called with correct parameters
        openai_service.client.chat.completions.create.assert_called_once()
        call_kwargs = openai_service.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-35-turbo"
        assert len(call_kwargs["messages"]) == 2
        assert call_kwargs["messages"][0]["role"] == "system"
        assert call_kwargs["messages"][1]["role"] == "user"
        
        # Verify result is correct
        assert result["response"] == "Test response"
        assert result["tokens"]["prompt"] == 10
        assert result["tokens"]["completion"] == 5

    @pytest.mark.asyncio
    async def test_completion_with_history(self, openai_service, mock_openai):
        """Test completion with conversation history"""
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        
        result = await openai_service.completion(
            system_prompt="You are a helpful assistant.",
            user_prompt="Tell me a joke.",
            history=history
        )
        
        # Verify client was called with correct parameters
        openai_service.client.chat.completions.create.assert_called_once()
        call_kwargs = openai_service.client.chat.completions.create.call_args.kwargs
        assert len(call_kwargs["messages"]) == 4  # system + 2 history + user
        assert call_kwargs["messages"][0]["role"] == "system"
        assert call_kwargs["messages"][1]["role"] == "user"
        assert call_kwargs["messages"][2]["role"] == "assistant"
        assert call_kwargs["messages"][3]["role"] == "user"
        
        # Verify result is correct
        assert result["response"] == "Test response"

    @pytest.mark.asyncio
    async def test_completion_with_functions(self, openai_service, mock_openai):
        """Test completion with function calling"""
        # Create a function definition
        functions = [
            {
                "name": "get_weather",
                "description": "Get the weather for a location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city and state, e.g. San Francisco, CA"
                        }
                    },
                    "required": ["location"]
                }
            }
        ]
        
        # Mock response with function call
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=None,
                    function_call=MagicMock(
                        name="get_weather",
                        arguments='{"location": "San Francisco, CA"}'
                    )
                )
            )
        ]
        mock_response.usage = MagicMock(prompt_tokens=15, completion_tokens=8)
        
        # Set up the mock to return our function call response
        openai_service.client.chat.completions.create.return_value = mock_response
        
        result = await openai_service.completion(
            system_prompt="You are a helpful assistant.",
            user_prompt="What's the weather in San Francisco?",
            functions=functions
        )
        
        # Verify client was called with functions
        openai_service.client.chat.completions.create.assert_called_once()
        call_kwargs = openai_service.client.chat.completions.create.call_args.kwargs
        assert "tools" in call_kwargs
        assert len(call_kwargs["tools"]) == 1
        assert call_kwargs["tools"][0]["type"] == "function"
        
        # Verify result contains function call
        assert result["response"] is None
        assert "function_call" in result
        assert result["function_call"]["name"] == "get_weather"
        assert result["function_call"]["arguments"] == {"location": "San Francisco, CA"}

    @pytest.mark.asyncio
    async def test_completion_with_retry(self, openai_service, mock_openai):
        """Test completion with retry configuration"""
        # First call raises an exception, second succeeds
        openai_service.client.chat.completions.create.side_effect = [
            Exception("Rate limit exceeded"),
            openai_service.client.chat.completions.create.return_value
        ]
        
        # Configure retries
        retry_config = RetryConfig(
            max_retries=3,
            min_retry_delay=0.1,
            max_retry_delay=1.0,
            retry_codes=[429, 500, 503]
        )
        
        result = await openai_service.completion(
            system_prompt="You are a helpful assistant.",
            user_prompt="Tell me a joke.",
            retry_config=retry_config
        )
        
        # Verify client was called twice (first fails, second succeeds)
        assert openai_service.client.chat.completions.create.call_count == 2
        
        # Verify result is from the successful second call
        assert result["response"] == "Test response"

    @pytest.mark.asyncio
    async def test_completion_failure(self, openai_service, mock_openai):
        """Test handling of API failure"""
        # Set up the mock to always raise an exception
        openai_service.client.chat.completions.create.side_effect = Exception("API error")
        
        with pytest.raises(Exception) as excinfo:
            await openai_service.completion(
                system_prompt="You are a helpful assistant.",
                user_prompt="Tell me a joke."
            )
        
        assert "API error" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_completion_with_temperature(self, openai_service, mock_openai):
        """Test completion with custom temperature"""
        await openai_service.completion(
            system_prompt="You are a helpful assistant.",
            user_prompt="Tell me a joke.",
            temperature=0.2
        )
        
        # Verify temperature was passed correctly
        call_kwargs = openai_service.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.2

    @pytest.mark.asyncio
    async def test_completion_with_max_tokens(self, openai_service, mock_openai):
        """Test completion with max_tokens limit"""
        await openai_service.completion(
            system_prompt="You are a helpful assistant.",
            user_prompt="Tell me a joke.",
            max_tokens=100
        )
        
        # Verify max_tokens was passed correctly
        call_kwargs = openai_service.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 100

    @pytest.mark.asyncio
    async def test_completion_with_function_response(self, openai_service, mock_openai):
        """Test completion with function call response"""
        # Set up a function call response
        function_response = {
            "name": "get_weather",
            "response": {"temperature": 72, "condition": "sunny"}
        }
        
        await openai_service.completion(
            system_prompt="You are a helpful assistant.",
            user_prompt="What's the weather?",
            history=[],
            function_response=function_response
        )
        
        # Verify function response was passed correctly in the messages
        call_kwargs = openai_service.client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        
        # Find the function message
        function_messages = [m for m in messages if m.get("role") == "function"]
        assert len(function_messages) == 1
        assert function_messages[0]["name"] == "get_weather"
        assert json.loads(function_messages[0]["content"]) == {"temperature": 72, "condition": "sunny"}

    @pytest.mark.asyncio
    async def test_get_token_client(self, openai_service, mock_openai):
        """Test getting a token client"""
        with patch('common.azure_openai_service.TokenClient') as mock_token_client:
            # Configure the mock
            mock_token_client.return_value = "token-client-instance"
            
            # Get token client
            token_client = openai_service.get_token_client(
                counter_api_url="http://localhost:8000",
                app_id="test_app"
            )
            
            # Verify token client was created with correct parameters
            mock_token_client.assert_called_once_with(
                counter_api_url="http://localhost:8000",
                app_id="test_app"
            )
            assert token_client == "token-client-instance"

    @pytest.mark.asyncio
    async def test_completion_with_token_client(self, openai_service, mock_openai):
        """Test completion using token client for rate limiting"""
        # Mock token client
        mock_token_client = AsyncMock()
        mock_token_client.request_with_tokens.return_value = {
            "response": "Rate limited response",
            "tokens": {"prompt": 10, "completion": 5}
        }
        
        # Call completion with token client
        result = await openai_service.completion_with_token_client(
            token_client=mock_token_client,
            token_estimate=100,
            system_prompt="You are a helpful assistant.",
            user_prompt="Tell me a joke."
        )
        
        # Verify token client was called
        mock_token_client.request_with_tokens.assert_called_once()
        call_args, call_kwargs = mock_token_client.request_with_tokens.call_args
        assert call_kwargs["token_estimate"] == 100
        assert "api_call" in call_kwargs  # The API call function
        
        # Verify result comes from token client
        assert result["response"] == "Rate limited response"
        assert result["tokens"]["prompt"] == 10
        assert result["tokens"]["completion"] == 5 