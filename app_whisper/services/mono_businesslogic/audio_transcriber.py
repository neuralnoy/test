"""
Whisper Transcriber for parallel channel-based transcription.
Handles concurrent transcription with rate limiting to avoid API blocks.
"""

from common_new.azure_openai_service import AzureOpenAIServiceWhisper
from common_new.logger import get_logger

logger = get_logger("mono_businesslogic_transcriber")

class WhisperTranscriber:
    """Handles parallel Whisper transcription for a list of audio chunks."""
    pass