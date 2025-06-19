"""
Transcription Post-Processor for final assembly and formatting.
Creates diarized transcripts with proper speaker labels and conversation flow.
"""

from app_whisper.models.schemas import SpeakerSegment
from common_new.logger import get_logger
from typing import List

logger = get_logger("businesslogic")

class TranscriptionPostProcessor:
    
    def _clean_repetitive_phrases(self, text: str) -> str:
        """
        Cleans up repetitive phrases in a text.
        If a phrase is repeated more than 3 times, it's replaced with 1 occurrence and '...'.
        It prioritizes cleaning the longest possible repeating phrase first.
        """
        words = text.split()
        n = len(words)
        if n < 4:
            return text

        result_words = []
        i = 0
        while i < n:
            found_repetition = False
            # Search for the longest possible repeating phrase starting at `i`
            # We iterate from longest possible length down to 1
            max_len = (n - i) // 4  # Phrase must repeat > 3 times
            for length in range(max_len, 0, -1):
                phrase = words[i : i + length]
                
                # Count how many times this phrase repeats
                reps = 1
                k = i + length
                while k + length <= n and words[k : k + length] == phrase:
                    reps += 1
                    k += length
                
                if reps > 3:
                    # We found our longest repeating phrase, process it
                    result_words.extend(phrase)
                    result_words.append("...")
                    i += length * reps  # Move index past the entire block
                    found_repetition = True
                    break # Stop searching for shorter phrases
            
            if not found_repetition:
                # No repetition found at this position, just add the word
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
            # First, attempt to fix potential double-encoding issues
            try:
                # This pattern repairs text that was incorrectly decoded as latin-1
                # when it should have been utf-8.
                text_to_process = segment.text.encode('latin-1').decode('utf-8')
            except (UnicodeEncodeError, UnicodeDecodeError) as e:
                # This can happen if the string is already correct, so we fall back
                logger.debug(f"Could not apply encoding fix for segment, using original text. Error: {e}")
                text_to_process = segment.text

            # Next, normalize whitespace
            normalized_text = " ".join(text_to_process.split())
            
            # Then, clean for repetitive phrases
            cleaned_text = self._clean_repetitive_phrases(normalized_text)
            full_transcript.append(f"{segment.speaker_id}: {cleaned_text}")
            
        return "\n".join(full_transcript)