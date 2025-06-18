"""
Transcription Post-Processor for final assembly and formatting.
Creates diarized transcripts with proper speaker labels and conversation flow.
"""

from app_whisper.models.schemas import SpeakerSegment
from common_new.logger import get_logger
from typing import List

logger = get_logger("businesslogic")

class TranscriptionPostProcessor:
    
    def assemble_transcript(self, speaker_segments: List[SpeakerSegment]) -> str:
        """
        Assembles a final transcript string from a list of speaker segments.

        Args:
            speaker_segments: A list of SpeakerSegment objects, sorted by time.

        Returns:
            A formatted string representing the full conversation.
        """
        if not speaker_segments:
            return ""
        
        full_transcript = []
        for segment in speaker_segments:
            # Format: Speaker ID: [text]
            full_transcript.append(f"{segment.speaker_id}: {segment.text}")
            
        return "\n".join(full_transcript)