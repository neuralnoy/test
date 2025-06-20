"""
Speaker Diarizer for channel-based speaker identification.
Converts Whisper transcription results into speaker-labeled segments.
"""
from typing import List
from app_whisper.models.schemas import SpeakerSegment, TranscribedChunk
from common_new.logger import get_logger

logger = get_logger("businesslogic")

class SpeakerDiarizer:
    """
    Performs simple speaker diarization by ordering segments by time
    and merging consecutive segments from the same speaker.
    """

    pass