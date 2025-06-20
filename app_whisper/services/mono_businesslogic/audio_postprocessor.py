"""
Transcription Post-Processor for final assembly and formatting.
Creates diarized transcripts with proper speaker labels and conversation flow.
"""

from common_new.logger import get_logger
from typing import List
from app_whisper.models.schemas import TranscribedChunk, SpeakerSegment

logger = get_logger("mono_businesslogic_postprocessor")

class TranscriptionPostProcessor:
    """
    Assembles a final, diarized transcript from Whisper segments and speaker
    diarization results.
    """
    
    def _condense_repetitions(self, text: str) -> str:
        """
        Finds and condenses phrases that are repeated more than three times consecutively.
        Example: "go go go go" becomes "go..."
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
                    pattern = words[i : i + pattern_len]
                    
                    repetition_count = 1
                    next_pos = i + pattern_len
                    while next_pos + pattern_len <= len(words) and words[next_pos : next_pos + pattern_len] == pattern:
                        repetition_count += 1
                        next_pos += pattern_len
                    
                    if repetition_count > 3:
                        # Found a qualifying repetition. Replace it and restart the process.
                        start_index = i
                        end_index = next_pos
                        
                        condensed_phrase = " ".join(pattern) + "..."
                        
                        new_words = words[:start_index] + [condensed_phrase] + words[end_index:]
                        text = " ".join(new_words)
                        found_repetition_in_pass = True
                        break  # Restart outer `while` loop with modified text
                
                if found_repetition_in_pass:
                    break
            
            # If a full pass over all pattern lengths finds no repetitions, we are done.
            if not found_repetition_in_pass:
                return text

    def assemble_transcript(
        self,
        transcribed_chunks: List[TranscribedChunk],
        diarization_segments: List[SpeakerSegment]
    ) -> str:
        """
        Maps Whisper transcription segments to speakers and formats the final transcript.

        The process is as follows:
        1.  All Whisper segments from all chunks are collected and their timestamps are
            adjusted to be absolute (relative to the start of the original audio).
        2.  Each Whisper segment is assigned to a speaker by calculating which
            diarized speaker segment it overlaps with the most.
        3.  Consecutive text segments from the same speaker are concatenated.
        4.  The final dialogue is formatted into a readable string.

        Args:
            transcribed_chunks: A list of transcribed audio chunks from Whisper.
            diarization_segments: A list of speaker segments from the AudioDiarizer.

        Returns:
            A formatted string representing the final diarized transcript.
        """
        # 1. Combine all whisper segments with global timestamps
        all_whisper_segments = []
        for tc in transcribed_chunks:
            if tc.transcription_result and tc.transcription_result.segments:
                for seg in tc.transcription_result.segments:
                    # Adjust segment time to be absolute from the start of the original audio
                    global_start = tc.chunk.start_time + seg.start
                    global_end = tc.chunk.start_time + seg.end
                    # Ignore very short or empty segments
                    if seg.text.strip() and (global_end - global_start) > 0.1:
                        all_whisper_segments.append({
                            'start': global_start,
                            'end': global_end,
                            'text': seg.text.strip()
                        })
        
        # Sort all segments by their start time to ensure chronological order
        all_whisper_segments.sort(key=lambda x: x['start'])
        
        if not all_whisper_segments:
            logger.warning("No valid Whisper segments found to process.")
            return ""

        # 2. Assign a speaker to each whisper segment based on overlap
        speaker_assigned_segments = []
        for whisper_seg in all_whisper_segments:
            overlap_scores = {}
            for diar_seg in diarization_segments:
                # Initialize speaker score if not present
                if diar_seg.speaker_id not in overlap_scores:
                    overlap_scores[diar_seg.speaker_id] = 0

                # Calculate the duration of overlap between the whisper segment and the diarization segment
                overlap_start = max(whisper_seg['start'], diar_seg.start_time)
                overlap_end = min(whisper_seg['end'], diar_seg.end_time)
                overlap_duration = max(0, overlap_end - overlap_start)
                
                if overlap_duration > 0:
                    overlap_scores[diar_seg.speaker_id] += overlap_duration
            
            # Find the speaker with the maximum overlap
            if any(score > 0 for score in overlap_scores.values()):
                dominant_speaker = max(overlap_scores, key=overlap_scores.get)
            else:
                dominant_speaker = "Unknown"
                logger.warning(f"Could not assign a speaker to segment: '{whisper_seg['text']}'")

            speaker_assigned_segments.append({
                'speaker': dominant_speaker,
                'text': whisper_seg['text']
            })
            
        # 3. Concatenate and clean consecutive segments from the same speaker
        if not speaker_assigned_segments:
            return ""

        final_dialogue = []
        current_speaker = speaker_assigned_segments[0]['speaker']
        current_text = speaker_assigned_segments[0]['text']

        for i in range(1, len(speaker_assigned_segments)):
            next_speaker = speaker_assigned_segments[i]['speaker']
            next_text = speaker_assigned_segments[i]['text']
            
            if next_speaker == current_speaker:
                current_text += " " + next_text
            else:
                condensed_text = self._condense_repetitions(current_text)
                final_dialogue.append({'speaker': current_speaker, 'text': condensed_text})
                current_speaker = next_speaker
                current_text = next_text
        
        # Add the last assembled segment
        condensed_text = self._condense_repetitions(current_text)
        final_dialogue.append({'speaker': current_speaker, 'text': condensed_text})
        
        # 4. Format the final transcript
        transcript_lines = [f"{segment['speaker']}: {segment['text']}" for segment in final_dialogue]
        final_transcript = "\n".join(transcript_lines)
        
        logger.info(f"Successfully assembled final transcript with {len(final_dialogue)} speaker turns.")
        return final_transcript

