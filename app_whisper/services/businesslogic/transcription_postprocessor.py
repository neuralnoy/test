"""
Transcription Post-processing Service for handling overlap deduplication and speaker alignment.
Merges chunk transcriptions into final results with proper speaker attribution.
"""
import re
from typing import List, Dict, Any, Optional, Tuple
from difflib import SequenceMatcher

from common_new.logger import get_logger
from app_whisper.models.schemas import (
    ChunkTranscription, 
    InternalWhisperResult, 
    SpeakerSegment
)

logger = get_logger("transcription_postprocessor")


class TranscriptionPostProcessor:
    """
    Service for post-processing transcribed audio chunks.
    Handles overlap deduplication, speaker alignment, and final assembly.
    """
    
    def __init__(self, similarity_threshold: float = 0.7):
        """
        Initialize the post-processor.
        
        Args:
            similarity_threshold: Minimum similarity for overlap detection (0.0 to 1.0)
        """
        self.similarity_threshold = similarity_threshold
        logger.info(f"Initialized TranscriptionPostProcessor with similarity_threshold={similarity_threshold}")
    
    async def process_chunk_transcriptions(
        self,
        transcriptions: List[ChunkTranscription],
        speaker_segments: Optional[List[SpeakerSegment]] = None
    ) -> InternalWhisperResult:
        """
        Process chunk transcriptions into final result with deduplication and speaker alignment.
        
        Args:
            transcriptions: List of chunk transcriptions to process
            speaker_segments: Optional speaker segments for alignment
            
        Returns:
            InternalWhisperResult with processed transcription
        """
        if not transcriptions:
            logger.warning("No transcriptions provided for processing")
            return InternalWhisperResult(
                text="",
                confidence=0.0,
                processing_metadata={"error": "No transcriptions provided"}
            )
        
        logger.info(f"Processing {len(transcriptions)} chunk transcriptions")
        
        # Filter out failed transcriptions
        valid_transcriptions = [t for t in transcriptions if t.text and not t.error]
        failed_count = len(transcriptions) - len(valid_transcriptions)
        
        if failed_count > 0:
            logger.warning(f"Filtered out {failed_count} failed transcriptions")
        
        if not valid_transcriptions:
            logger.error("No valid transcriptions to process")
            return InternalWhisperResult(
                text="",
                confidence=0.0,
                processing_metadata={"error": "All transcriptions failed"}
            )
        
        # Sort transcriptions by start time
        valid_transcriptions.sort(key=lambda t: t.start_time)
        
        # Deduplicate overlapping content
        deduplicated_transcriptions = self._deduplicate_overlaps(valid_transcriptions)
        
        # Merge transcriptions into final text
        final_text, average_confidence = self._merge_transcriptions(deduplicated_transcriptions)
        
        # Align with speaker segments if provided
        if speaker_segments:
            final_text = self._align_with_speakers(final_text, deduplicated_transcriptions, speaker_segments)
        
        # Create processing metadata
        processing_metadata = {
            "transcription_method": "chunked_with_deduplication",
            "total_chunks": len(transcriptions),
            "valid_chunks": len(valid_transcriptions),
            "failed_chunks": failed_count,
            "deduplicated_chunks": len(deduplicated_transcriptions),
            "similarity_threshold": self.similarity_threshold,
            "has_speaker_alignment": speaker_segments is not None
        }
        
        result = InternalWhisperResult(
            text=final_text.strip(),
            confidence=average_confidence,
            processing_metadata=processing_metadata
        )
        
        logger.info(f"Post-processing completed: {len(final_text)} characters, confidence={average_confidence:.3f}")
        return result
    
    def _deduplicate_overlaps(self, transcriptions: List[ChunkTranscription]) -> List[ChunkTranscription]:
        """
        Remove overlapping content between consecutive transcriptions.
        
        Args:
            transcriptions: Sorted list of transcriptions
            
        Returns:
            List of transcriptions with overlaps removed
        """
        if len(transcriptions) <= 1:
            return transcriptions
        
        logger.debug(f"Deduplicating overlaps in {len(transcriptions)} transcriptions")
        
        deduplicated = [transcriptions[0]]  # Keep first transcription as-is
        
        for i in range(1, len(transcriptions)):
            current = transcriptions[i]
            previous = deduplicated[-1]
            
            # Check if there's temporal overlap
            if current.start_time < previous.end_time:
                # Find and remove overlapping text
                deduplicated_text = self._remove_text_overlap(previous.text, current.text)
                
                # Create new transcription with deduplicated text
                deduplicated_current = ChunkTranscription(
                    chunk_id=current.chunk_id,
                    start_time=current.start_time,
                    end_time=current.end_time,
                    text=deduplicated_text,
                    confidence=current.confidence,
                    whisper_result=current.whisper_result,
                    file_path=current.file_path
                )
                
                deduplicated.append(deduplicated_current)
                
                logger.debug(f"Deduplicated chunk {current.chunk_id}: {len(current.text)} -> {len(deduplicated_text)} chars")
            else:
                # No overlap, keep as-is
                deduplicated.append(current)
        
        logger.info(f"Deduplication completed: {len(transcriptions)} -> {len(deduplicated)} chunks")
        return deduplicated
    
    def _remove_text_overlap(self, previous_text: str, current_text: str) -> str:
        """
        Remove overlapping text between two transcriptions.
        
        Args:
            previous_text: Text from previous chunk
            current_text: Text from current chunk
            
        Returns:
            Current text with overlap removed
        """
        if not previous_text or not current_text:
            return current_text
        
        # Split into words for better matching
        prev_words = previous_text.split()
        curr_words = current_text.split()
        
        if not prev_words or not curr_words:
            return current_text
        
        # Find the best overlap using sliding window
        best_overlap_length = 0
        best_similarity = 0.0
        
        # Check different overlap lengths (up to half of each text)
        max_overlap = min(len(prev_words) // 2, len(curr_words) // 2, 20)  # Limit to 20 words
        
        for overlap_length in range(1, max_overlap + 1):
            # Get suffix from previous text and prefix from current text
            prev_suffix = " ".join(prev_words[-overlap_length:])
            curr_prefix = " ".join(curr_words[:overlap_length])
            
            # Calculate similarity
            similarity = SequenceMatcher(None, prev_suffix.lower(), curr_prefix.lower()).ratio()
            
            if similarity > self.similarity_threshold and similarity > best_similarity:
                best_similarity = similarity
                best_overlap_length = overlap_length
        
        # Remove the overlapping prefix from current text
        if best_overlap_length > 0:
            remaining_words = curr_words[best_overlap_length:]
            result = " ".join(remaining_words)
            
            logger.debug(f"Removed {best_overlap_length} overlapping words (similarity={best_similarity:.3f})")
            return result
        
        return current_text
    
    def _merge_transcriptions(self, transcriptions: List[ChunkTranscription]) -> Tuple[str, float]:
        """
        Merge transcriptions into final text with confidence calculation.
        
        Args:
            transcriptions: List of deduplicated transcriptions
            
        Returns:
            Tuple of (merged_text, average_confidence)
        """
        if not transcriptions:
            return "", 0.0
        
        # Merge texts with proper spacing
        text_parts = []
        total_confidence = 0.0
        total_duration = 0.0
        
        for transcription in transcriptions:
            if transcription.text.strip():
                text_parts.append(transcription.text.strip())
                
                # Weight confidence by duration
                duration = transcription.end_time - transcription.start_time
                total_confidence += transcription.confidence * duration
                total_duration += duration
        
        # Join texts with spaces
        merged_text = " ".join(text_parts)
        
        # Calculate weighted average confidence
        average_confidence = total_confidence / total_duration if total_duration > 0 else 0.0
        
        # Clean up the merged text
        merged_text = self._clean_text(merged_text)
        
        logger.debug(f"Merged {len(transcriptions)} transcriptions: {len(merged_text)} characters")
        return merged_text, average_confidence
    
    def _clean_text(self, text: str) -> str:
        """
        Clean up merged text by removing extra spaces and formatting issues.
        
        Args:
            text: Raw merged text
            
        Returns:
            Cleaned text
        """
        if not text:
            return text
        
        # Remove multiple spaces
        text = re.sub(r'\s+', ' ', text)
        
        # Fix punctuation spacing
        text = re.sub(r'\s+([,.!?;:])', r'\1', text)
        text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        return text
    
    def _align_with_speakers(
        self,
        text: str,
        transcriptions: List[ChunkTranscription],
        speaker_segments: List[SpeakerSegment]
    ) -> str:
        """
        Align transcription with speaker segments to add speaker labels.
        
        Args:
            text: Merged transcription text
            transcriptions: List of chunk transcriptions
            speaker_segments: List of speaker segments
            
        Returns:
            Text with speaker labels
        """
        if not speaker_segments or not transcriptions:
            return text
        
        logger.debug(f"Aligning transcription with {len(speaker_segments)} speaker segments")
        
        # Create time-based mapping of transcriptions
        time_segments = []
        for transcription in transcriptions:
            if transcription.text.strip():
                time_segments.append({
                    'start': transcription.start_time,
                    'end': transcription.end_time,
                    'text': transcription.text.strip()
                })
        
        if not time_segments:
            return text
        
        # Align with speaker segments
        aligned_parts = []
        current_speaker = None
        
        for segment in time_segments:
            # Find the dominant speaker for this segment
            segment_speaker = self._find_dominant_speaker(
                segment['start'], segment['end'], speaker_segments
            )
            
            # Add speaker label if speaker changed
            if segment_speaker != current_speaker:
                if aligned_parts:  # Add newline before new speaker (except first)
                    aligned_parts.append("\n")
                aligned_parts.append(f"Speaker {segment_speaker}: ")
                current_speaker = segment_speaker
            
            aligned_parts.append(segment['text'])
            aligned_parts.append(" ")
        
        aligned_text = "".join(aligned_parts).strip()
        
        logger.debug(f"Speaker alignment completed: {len(aligned_text)} characters")
        return aligned_text
    
    def _find_dominant_speaker(
        self,
        start_time: float,
        end_time: float,
        speaker_segments: List[SpeakerSegment]
    ) -> str:
        """
        Find the dominant speaker for a given time range.
        
        Args:
            start_time: Start time of the segment
            end_time: End time of the segment
            speaker_segments: List of speaker segments
            
        Returns:
            Speaker ID of the dominant speaker
        """
        speaker_durations = {}
        
        for speaker_seg in speaker_segments:
            # Calculate overlap between transcription segment and speaker segment
            overlap_start = max(start_time, speaker_seg.start_time)
            overlap_end = min(end_time, speaker_seg.end_time)
            
            if overlap_start < overlap_end:
                overlap_duration = overlap_end - overlap_start
                speaker_id = speaker_seg.speaker_id
                
                if speaker_id not in speaker_durations:
                    speaker_durations[speaker_id] = 0.0
                speaker_durations[speaker_id] += overlap_duration
        
        if speaker_durations:
            # Return speaker with longest overlap
            dominant_speaker = max(speaker_durations.items(), key=lambda x: x[1])[0]
            return dominant_speaker
        
        # Default to Speaker 1 if no overlap found
        return "1" 