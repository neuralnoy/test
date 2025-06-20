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

    def diarize_and_filter(self, transcribed_chunks: List[TranscribedChunk]) -> List[SpeakerSegment]:
        """
        Processes transcribed chunks to create a time-ordered, merged transcript.

        Args:
            transcribed_chunks: A list of transcribed chunks with segment-level timestamps.

        Returns:
            A list of merged SpeakerSegment objects.
        """
        logger.info("Starting simple timestamp-based diarization.")
        
        # 1. Aggregate all speaker segments from all chunks, sorted by time.
        all_segments = self._get_all_segments(transcribed_chunks)
        if not all_segments:
            logger.warning("No segments found in transcribed chunks to perform diarization.")
            return []

        # 2. Merge consecutive segments from the same speaker
        merged_segments = self._merge_consecutive_segments(all_segments)
        
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