import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock

from apps.app_feedbackform.services.data_processor import process_data
from apps.app_feedbackform.models.schemas import InputFeedbackForm, OutputFeedbackForm

class TestDataProcessor:
    """Test suite for the data_processor module"""

    @pytest.fixture
    def valid_feedback_data(self):
        """Return valid feedback form data for testing"""
        return {
            "id": "test-id-123",
            "taskId": "task-456",
            "language": "en",
            "text": "This is a test feedback. The service was good but could be improved."
        }

    @pytest.mark.asyncio
    @patch('apps.app_feedbackform.services.prompts.process_feedback')
    async def test_process_data_success(self, mock_process_feedback, valid_feedback_data):
        """Test successful processing of feedback data"""
        # Mock the process_feedback function to return successful results
        mock_process_feedback.return_value = (
            True, 
            {
                "ai_hashtag": "#positive",
                "hashtag": "#good",
                "summary": "Service was good but could be improved"
            }
        )
        
        # Convert input data to JSON string
        message_body = json.dumps(valid_feedback_data)
        
        # Process the data
        result = await process_data(message_body)
        
        # Assertions
        assert result is not None
        assert result["id"] == valid_feedback_data["id"]
        assert result["taskId"] == valid_feedback_data["taskId"]
        assert result["ai_hashtag"] == "#positive"
        assert result["hashtag"] == "#good"
        assert result["summary"] == "Service was good but could be improved"
        assert result["message"] == "SUCCESS"

    @pytest.mark.asyncio
    @patch('apps.app_feedbackform.services.prompts.process_feedback')
    async def test_process_data_processing_failure(self, mock_process_feedback, valid_feedback_data):
        """Test handling of processing failure"""
        # Mock the process_feedback function to return failure
        mock_process_feedback.return_value = (
            False,
            {
                "ai_hashtag": "#error",
                "hashtag": "#error",
                "summary": "Failed to process feedback"
            }
        )
        
        # Convert input data to JSON string
        message_body = json.dumps(valid_feedback_data)
        
        # Process the data
        result = await process_data(message_body)
        
        # Assertions
        assert result is not None
        assert result["id"] == valid_feedback_data["id"]
        assert result["taskId"] == valid_feedback_data["taskId"]
        assert result["ai_hashtag"] == "#error"
        assert result["hashtag"] == "#error"
        assert result["summary"] == "Failed to process feedback"
        assert result["message"] == "failed"

    @pytest.mark.asyncio
    async def test_process_data_invalid_json(self):
        """Test handling of invalid JSON input"""
        # Invalid JSON string
        message_body = "{invalid json"
        
        # Process the data
        result = await process_data(message_body)
        
        # Assertions
        assert result is not None
        assert result["id"] == "unknown"
        assert result["taskId"] == "unknown"
        assert result["ai_hashtag"] == "#error"
        assert result["hashtag"] == "#error"
        assert "JSON parsing error" in result["summary"]
        assert result["message"] == "failed"

    @pytest.mark.asyncio
    async def test_process_data_empty_message(self):
        """Test handling of empty message"""
        # Empty message
        message_body = ""
        
        # Process the data
        result = await process_data(message_body)
        
        # Assertions
        assert result is not None
        assert result["id"] == "unknown"
        assert result["taskId"] == "unknown"
        assert result["ai_hashtag"] == "#error"
        assert result["hashtag"] == "#error"
        assert "JSON parsing error" in result["summary"]
        assert result["message"] == "failed"

    @pytest.mark.asyncio
    async def test_process_data_missing_required_fields(self):
        """Test handling of data with missing required fields"""
        # Data with missing required fields
        incomplete_data = {
            "id": "test-id-123",
            # Missing taskId
            "language": "en",
            # Missing text
        }
        
        message_body = json.dumps(incomplete_data)
        
        # Process the data
        result = await process_data(message_body)
        
        # Assertions
        assert result is not None
        assert result["id"] == "test-id-123"  # Should use the provided id
        assert result["taskId"] == "unknown"  # Should use default for missing taskId
        assert result["ai_hashtag"] == "#error"
        assert result["hashtag"] == "#error"
        assert "error" in result["summary"].lower()
        assert result["message"] == "failed"

    @pytest.mark.asyncio
    @patch('apps.app_feedbackform.services.prompts.process_feedback')
    async def test_process_data_exception_during_processing(self, mock_process_feedback, valid_feedback_data):
        """Test handling of exceptions during processing"""
        # Mock the process_feedback function to raise an exception
        mock_process_feedback.side_effect = Exception("Processing error")
        
        # Convert input data to JSON string
        message_body = json.dumps(valid_feedback_data)
        
        # Process the data
        result = await process_data(message_body)
        
        # Assertions
        assert result is not None
        assert result["id"] == valid_feedback_data["id"]
        assert result["taskId"] == valid_feedback_data["taskId"]
        assert result["ai_hashtag"] == "#error"
        assert result["hashtag"] == "#error"
        assert "Processing error" in result["summary"]
        assert result["message"] == "failed"

    @pytest.mark.asyncio
    async def test_process_data_non_string_input(self):
        """Test handling of non-string input"""
        # Non-string input (e.g., bytes or some other object)
        message_body = bytes(json.dumps({"id": "test-id"}), 'utf-8')
        
        # Process the data
        result = await process_data(message_body)
        
        # Assertions
        assert result is not None
        assert "error" in result["ai_hashtag"].lower()
        assert result["message"] == "failed"

    @pytest.mark.asyncio
    @patch('apps.app_feedbackform.services.prompts.process_feedback')
    async def test_process_data_empty_text(self, mock_process_feedback):
        """Test handling of empty text field"""
        # Data with empty text field
        data_with_empty_text = {
            "id": "test-id-123",
            "taskId": "task-456",
            "language": "en",
            "text": ""  # Empty text
        }
        
        # Mock the process_feedback function
        mock_process_feedback.return_value = (
            True, 
            {
                "ai_hashtag": "#neutral",
                "hashtag": "#empty",
                "summary": "No feedback provided"
            }
        )
        
        message_body = json.dumps(data_with_empty_text)
        
        # Process the data
        result = await process_data(message_body)
        
        # Assertions
        assert result is not None
        assert result["id"] == data_with_empty_text["id"]
        assert result["taskId"] == data_with_empty_text["taskId"]
        assert result["message"] == "SUCCESS"
        
        # Verify process_feedback was called with empty string
        mock_process_feedback.assert_called_once_with("")

    @pytest.mark.asyncio
    @patch('apps.app_feedbackform.services.prompts.process_feedback')
    async def test_process_data_long_text(self, mock_process_feedback):
        """Test handling of very long text input"""
        # Create data with very long text
        long_text = "This is a very long feedback text. " * 100  # Repeat to make it long
        data_with_long_text = {
            "id": "test-id-123",
            "taskId": "task-456",
            "language": "en",
            "text": long_text
        }
        
        # Mock the process_feedback function
        mock_process_feedback.return_value = (
            True, 
            {
                "ai_hashtag": "#detailed",
                "hashtag": "#comprehensive",
                "summary": "Detailed feedback provided"
            }
        )
        
        message_body = json.dumps(data_with_long_text)
        
        # Process the data
        result = await process_data(message_body)
        
        # Assertions
        assert result is not None
        assert result["id"] == data_with_long_text["id"]
        assert result["message"] == "SUCCESS"
        
        # Verify process_feedback was called with the long text
        mock_process_feedback.assert_called_once_with(long_text) 