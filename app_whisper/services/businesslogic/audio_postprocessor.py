"""
Transcription Post-Processor for final assembly and formatting.
Creates diarized transcripts with proper speaker labels and conversation flow.
"""

from app_whisper.models.schemas import SpeakerSegment
from common_new.logger import get_logger
from typing import List

logger = get_logger("businesslogic")

class TranscriptionPostProcessor:
    
    def _clean_repetition(self, text: str) -> str:
        """
        Cleans up repetitive words in a text.
        If a word is repeated more than 3 times, it's replaced with 3 occurrences and '...'.
        """
        words = text.split()
        if len(words) < 4:
            return text

        result_words = []
        i = 0
        while i < len(words):
            current_word = words[i]
            
            # Find how many times this word repeats consecutively, ignoring case and some punctuation.
            j = i
            while (j < len(words) and 
                   words[j].strip('.,!?').lower() == current_word.strip('.,!?').lower()):
                j += 1
            
            count = j - i
            
            if count > 3:
                # Add the first three occurrences from the original list and an ellipsis
                result_words.extend(words[i:i+3])
                result_words.append("...")
                i = j  # Skip past the entire repetitive sequence
            else:
                # No excessive repetition, just add the single word and move on
                result_words.append(words[i])
                i += 1
        
        return " ".join(result_words)

    def assemble_transcript(self, speaker_segments: List[SpeakerSegment]) -> str:
        """
        Assembles a final transcript string from a list of speaker segments,
        with additional cleaning for repetitive hallucinations.
        """
        if not speaker_segments:
            return ""
        
        full_transcript = []
        for segment in speaker_segments:
            # Clean the text for repetitions before appending
            cleaned_text = self._clean_repetition(segment.text)
            full_transcript.append(f"{segment.speaker_id}: {cleaned_text}")
            
        return "\n".join(full_transcript)