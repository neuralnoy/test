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
        Finds and condenses phrases that are repeated more than three times consecutively,
        ignoring case and punctuation.
        Example: "go, go. go go!" becomes "go..."
        """
        while True:
            words = text.split()
            # Need at least 4 words to have a 1-word pattern repeated > 3 times
            if len(words) < 4:
                return text

            found_repetition_in_pass = False
            # Iterate from the longest possible pattern length down to 1.
            # A pattern must repeat at least 4 times to be condensed (i.e., > 3).
            for pattern_len in range(len(words) // 4, 0, -1):
                # Iterate through the words to find a starting point for a pattern.
                # The loop range is optimized to not check where a 4x repetition is impossible.
                for i in range(len(words) - (pattern_len * 4) + 1):
                    original_pattern = words[i : i + pattern_len]
                    normalized_pattern = [w.strip('.,!?').lower() for w in original_pattern]
                    
                    repetition_count = 1
                    next_pos = i + pattern_len
                    while next_pos + pattern_len <= len(words):
                        next_segment = words[next_pos : next_pos + pattern_len]
                        normalized_segment = [w.strip('.,!?').lower() for w in next_segment]
                        if normalized_segment == normalized_pattern:
                            repetition_count += 1
                            next_pos += pattern_len
                        else:
                            break
                    
                    if repetition_count > 3:
                        # Found a qualifying repetition. Replace it and restart the process.
                        start_index = i
                        end_index = next_pos
                        
                        # Use the original capitalization from the first occurrence of the pattern.
                        condensed_phrase = " ".join(original_pattern) + "..."
                        
                        new_words = words[:start_index] + [condensed_phrase] + words[end_index:]
                        text = " ".join(new_words)
                        found_repetition_in_pass = True
                        break  # Restart outer `while` loop with modified text
                
                if found_repetition_in_pass:
                    break
            
            # If a full pass over all pattern lengths finds no repetitions, we are done.
            if not found_repetition_in_pass:
                return text

    def assemble_transcript(self, speaker_segments: List[SpeakerSegment]) -> str:
        """
        Assembles a final transcript string from a list of speaker segments,
        with additional cleaning for repetitive hallucinations.
        """
        if not speaker_segments:
            return ""
        
        full_transcript = []
        for segment in speaker_segments:
            # First, normalize whitespace for all segments
            normalized_text = " ".join(segment.text.split())
            
            # Clean for repeated word-sequence hallucinations
            cleaned_text = self._clean_repetition(normalized_text)
            
            # Format speaker ID
            formatted_speaker_id = segment.speaker_id.replace('_', ' ')
            formatted_speaker_id = f"*{formatted_speaker_id}*"
            
            full_transcript.append(f"{formatted_speaker_id}: {cleaned_text}")
            
        return "\n".join(full_transcript)