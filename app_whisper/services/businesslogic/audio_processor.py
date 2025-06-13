"""
Audio processor service that uses Azure OpenAI Whisper to process audio files
and return the transcription and diarization.
"""
from app_whisper.models.schemas import InternalWhisperResult
from common_new.azure_openai_service import AzureOpenAIService

# Initialize the Azure OpenAI service
ai_service = AzureOpenAIService(app_id="app_whisper")

async def process_audio(filename: str) -> InternalWhisperResult:
    """
    Process audio file using Azure OpenAI Whisper.
    """
    pass