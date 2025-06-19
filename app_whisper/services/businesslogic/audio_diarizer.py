"""
Speaker Diarizer for channel-based speaker identification.
Converts Whisper transcription results into speaker-labeled segments.
"""
from typing import List, Dict, Optional, Tuple
from app_whisper.models.schemas import SpeakerSegment, TranscribedChunk
from common_new.logger import get_logger
import math

logger = get_logger("businesslogic")

class SpeakerDiarizer:
    """
    Performs speaker diarization by resolving overlapping speech segments
    based on a dominance score (text density and time coverage).
    """

    def diarize_and_filter(self, transcribed_chunks: List[TranscribedChunk]) -> List[SpeakerSegment]:
        """
        Processes transcribed chunks to identify the dominant speaker in overlapping segments
        and filters out the non-dominant speaker's segments.

        Args:
            transcribed_chunks: A list of transcribed chunks with segment-level timestamps.

        Returns:
            A list of SpeakerSegment objects containing only the text from the dominant speakers.
        """
        logger.info("Starting speaker diarization and overlap filtering.")
        
        # 1. Aggregate all speaker segments from all chunks
        all_segments = self._get_all_segments(transcribed_chunks)
        if not all_segments:
            logger.warning("No segments found in transcribed chunks to perform diarization.")
            return []

        # 2. Identify and resolve overlapping segments
        final_segments = self._resolve_overlaps(all_segments)

        # 3. Merge consecutive segments from the same speaker
        merged_segments = self._merge_consecutive_segments(final_segments)
        
        logger.info(f"Diarization complete. Generated {len(merged_segments)} final speaker segments.")
        return merged_segments

    def _get_all_segments(self, transcribed_chunks: List[TranscribedChunk]) -> List[SpeakerSegment]:
        """Extracts and flattens all speaker segments from transcribed chunks."""
        all_segments = []
        for t_chunk in transcribed_chunks:
            if t_chunk.error or not t_chunk.transcription_result:
                continue
            
            chunk_start_time = t_chunk.chunk.start_time
            speaker_id = t_chunk.chunk.speaker_id

            for segment_data in t_chunk.transcription_result.segments:
                all_segments.append(SpeakerSegment(
                    start_time=segment_data.start + chunk_start_time,
                    end_time=segment_data.end + chunk_start_time,
                    speaker_id=speaker_id,
                    text=segment_data.text.strip()
                ))
        
        all_segments.sort(key=lambda s: s.start_time)
        return all_segments

    def _resolve_overlaps(self, segments: List[SpeakerSegment]) -> List[SpeakerSegment]:
        """Identifies overlaps and removes segments from the non-dominant speaker."""
        if not segments:
            return []

        # This list will hold the segments we decide to keep
        kept_segments = []
        
        i = 0
        while i < len(segments):
            current_segment = segments[i]
            
            # Find all segments that overlap with the current one
            overlapping_segments = [current_segment]
            j = i + 1
            while j < len(segments) and segments[j].start_time < current_segment.end_time:
                # Check for actual time overlap
                if segments[j].speaker_id != current_segment.speaker_id:
                    overlapping_segments.append(segments[j])
                j += 1
            
            if len(overlapping_segments) > 1:
                # We have an overlap to resolve
                dominant_speaker = self._get_dominant_speaker_in_overlap(overlapping_segments)
                
                # Keep only the segments from the dominant speaker in this overlap group
                for seg in overlapping_segments:
                    if seg.speaker_id == dominant_speaker:
                        kept_segments.append(seg)
                
                # Move the main index past all processed overlapping segments
                i = j
            else:
                # No overlap, just keep the current segment
                kept_segments.append(current_segment)
                i += 1
                
        return kept_segments

    def _get_dominant_speaker_in_overlap(self, overlapping_segments: List[SpeakerSegment]) -> str:
        """
        Calculates a dominance score for each speaker in an overlap and returns the winner.
        Score is 70% based on time coverage and 30% on word density.
        """
        scores = {'*Speaker 1*': 0.0, '*Speaker 2*': 0.0}
        
        # Determine the total time range of the overlap
        min_start = min(s.start_time for s in overlapping_segments)
        max_end = max(s.end_time for s in overlapping_segments)
        overlap_duration = max_end - min_start

        if overlap_duration == 0:
            # Fallback for zero-duration overlaps, prefer Speaker 1
            return '*Speaker 1*'

        for speaker_id in scores.keys():
            segments_for_speaker = [s for s in overlapping_segments if s.speaker_id == speaker_id]
            if not segments_for_speaker:
                continue

            # 1. Calculate time coverage score (70% weight)
            total_time_for_speaker = sum(s.end_time - s.start_time for s in segments_for_speaker)
            time_coverage_score = total_time_for_speaker / overlap_duration
            
            # 2. Calculate text density score (30% weight)
            total_words = sum(len(s.text.split()) for s in segments_for_speaker)
            density = total_words / total_time_for_speaker if total_time_for_speaker > 0 else 0
            # Normalize density to a 0-1 scale (simple normalization, assumes max 10 words/sec)
            density_score = min(density / 10.0, 1.0)

            # 3. Combine scores
            scores[speaker_id] = (0.7 * time_coverage_score) + (0.3 * density_score)
        
        # Return the speaker with the highest score
        return max(scores, key=scores.get)

    def _merge_consecutive_segments(self, segments: List[SpeakerSegment]) -> List[SpeakerSegment]:
        """Merges consecutive segments from the same speaker."""
        if not segments:
            return []
            
        merged = []
        current_segment = segments[0]

        for i in range(1, len(segments)):
            next_segment = segments[i]
            if next_segment.speaker_id == current_segment.speaker_id:
                # Merge segments
                current_segment.text += " " + next_segment.text
                current_segment.end_time = next_segment.end_time
            else:
                # Speaker has changed, finalize the current segment
                merged.append(current_segment)
                current_segment = next_segment
        
        merged.append(current_segment)
        return merged