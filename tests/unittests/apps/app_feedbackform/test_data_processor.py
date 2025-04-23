import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from apps.app_feedbackform.services.data_processor import process_data


class TestFeedbackFormProcessor:
    """Unit tests for the feedback form data processor."""
    
    @pytest.mark.asyncio
    async def test_process_data_success(self, sample_feedback_data):
        """Test successful processing of feedback form data."""
        # Convert sample data to JSON string
        message_body = json.dumps(sample_feedback_data)
        
        # Process the data
        result = await process_data(message_body)
        
        # Assert result contains expected fields
        assert result is not None
        assert "id" in result
        assert result["id"] == sample_feedback_data["id"]
        assert "ai_hashtag" in result
        assert "hashtag" in result
        assert "summary" in result
        
        # Check hashtag contains the language
        assert sample_feedback_data["language"].lower() in result["hashtag"]
        
        # Check the summary contains part of the original text
        assert result["summary"].startswith(sample_feedback_data["text"][:10])
    
    @pytest.mark.asyncio
    async def test_process_data_missing_fields(self):
        """Test processing data with missing required fields."""
        # Create data with missing fields
        incomplete_data = {
            "id": "test-id-123",
            # Missing taskId
            "language": "en",
            # Missing text
        }
        
        # Process the data
        result = await process_data(json.dumps(incomplete_data))
        
        # Assert result is None due to missing fields
        assert result is None
    
    @pytest.mark.asyncio
    async def test_process_data_invalid_json(self):
        """Test processing invalid JSON data."""
        # Invalid JSON string
        invalid_json = "{invalid: json}"
        
        # Process the data
        result = await process_data(invalid_json)
        
        # Assert result is None due to JSON decode error
        assert result is None
    
    @pytest.mark.asyncio
    async def test_process_data_empty_text(self):
        """Test processing data with empty text field."""
        # Create data with empty text
        data_with_empty_text = {
            "id": "test-id-123",
            "taskId": "task-abc",
            "language": "en",
            "text": ""
        }
        
        # Process the data
        result = await process_data(json.dumps(data_with_empty_text))
        
        # Assert result contains expected fields
        assert result is not None
        assert "id" in result
        assert result["id"] == data_with_empty_text["id"]
        
        # Check ai_hashtag defaults to "unknown" when text is empty
        assert result["ai_hashtag"] == "#unknown"
    
    @pytest.mark.asyncio
    async def test_process_data_long_text(self):
        """Test processing data with long text that gets truncated in summary."""
        # Create data with long text
        long_text = "A" * 2000  # 2000 character string
        data_with_long_text = {
            "id": "test-id-123",
            "taskId": "task-abc",
            "language": "en",
            "text": long_text
        }
        
        # Process the data
        result = await process_data(json.dumps(data_with_long_text))
        
        # Assert summary is truncated with ellipsis
        assert result is not None
        assert len(result["summary"]) < len(long_text)
        assert result["summary"].endswith("...")
        
        # Check the summary contains first 100 chars + "..."
        assert result["summary"] == long_text[:100] + "..."
    
    @pytest.mark.asyncio
    async def test_process_data_handles_exception(self):
        """Test that process_data handles exceptions properly."""
        # Mock json.loads to raise an unexpected exception
        with patch('json.loads', side_effect=Exception("Unexpected error")):
            # Process the data
            result = await process_data("test message")
            
            # Assert result is None due to error
            assert result is None 