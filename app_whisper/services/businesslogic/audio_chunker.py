"""
Audio chunker for Step 4 of the whisper pipeline.
Handles intelligent audio chunking with overlaps for optimal Whisper transcription.
"""
import os
import tempfile
import uuid
from typing import List, Optional, Tuple
from pydub import AudioSegment
from app_whisper.models.schemas import AudioChunk
from app_whisper.services.businesslogic.speaker_diarizer import SpeakerSegment
from common_new.logger import get_logger

logger = get_logger("whisper")

class AudioChunker:
    """
    Handles intelligent audio chunking for Whisper transcription.
    
    This class implements Step 4 of the whisper pipeline:
    - Check file size constraints (< 24MB = whole file)
    - Create overlapping chunks based on speaker boundaries
    - Optimize chunk sizes for Whisper processing
    - Maintain overlap metadata for deduplication
    """
    
    def __init__(self, 
                 max_file_size_mb: float = 24.0,
                 target_chunk_duration: float = 30.0,
                 max_chunk_duration: float = 60.0,
                 overlap_duration: float = 3.0,
                 min_chunk_duration: float = 5.0):
        """
        Initialize the audio chunker.
        
        Args:
            max_file_size_mb: Maximum file size in MB to process as whole file
            target_chunk_duration: Target duration for each chunk (seconds)
            max_chunk_duration: Maximum duration for each chunk (seconds)
            overlap_duration: Overlap duration between chunks (seconds)
            min_chunk_duration: Minimum duration for a chunk (seconds)
        """
        self.max_file_size_mb = max_file_size_mb
        self.target_chunk_duration = target_chunk_duration
        self.max_chunk_duration = max_chunk_duration
        self.overlap_duration = overlap_duration
        self.min_chunk_duration = min_chunk_duration
        self.temp_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
        
        logger.info(f"Initialized AudioChunker: max_size={max_file_size_mb}MB, "
                   f"target_duration={target_chunk_duration}s, overlap={overlap_duration}s")
    
    def chunk_audio(self, audio_path: str, speaker_segments: List[SpeakerSegment]) -> List[AudioChunk]:
        """
        Create audio chunks for Whisper transcription.
        
        Args:
            audio_path: Path to the preprocessed audio file
            speaker_segments: List of speaker segments from diarization
            
        Returns:
            List[AudioChunk]: List of audio chunks ready for transcription
        """
        try:
            logger.info(f"Starting audio chunking for: {audio_path}")
            
            # Load audio file
            audio = AudioSegment.from_file(audio_path)
            file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
            duration = len(audio) / 1000.0
            
            logger.info(f"Audio info: duration={duration:.2f}s, size={file_size_mb:.2f}MB")
            
            # Check if we should process as whole file
            if file_size_mb <= self.max_file_size_mb:
                logger.info(f"File size ({file_size_mb:.2f}MB) <= {self.max_file_size_mb}MB, processing as whole file")
                return self._create_whole_file_chunk(audio_path, audio, speaker_segments)
            
            # Create overlapping chunks
            logger.info(f"File size ({file_size_mb:.2f}MB) > {self.max_file_size_mb}MB, creating chunks")
            return self._create_overlapping_chunks(audio_path, audio, speaker_segments)
            
        except Exception as e:
            logger.error(f"Error chunking audio {audio_path}: {str(e)}")
            # Fallback: create single chunk
            return self._create_fallback_chunk(audio_path)
    
    def _create_whole_file_chunk(self, audio_path: str, audio: AudioSegment, speaker_segments: List[SpeakerSegment]) -> List[AudioChunk]:
        """Create a single chunk for the whole file."""
        chunk_id = f"chunk_whole_{uuid.uuid4().hex[:8]}"
        
        # Copy file to chunks directory
        chunk_path = os.path.join(self.temp_dir, f"{chunk_id}.wav")
        audio.export(chunk_path, format="wav")
        
        # Get all speakers in the file
        speakers = list(set(seg.speaker_id for seg in speaker_segments))
        
        chunk = AudioChunk(
            chunk_id=chunk_id,
            file_path=chunk_path,
            start_time=0.0,
            end_time=len(audio) / 1000.0,
            duration=len(audio) / 1000.0,
            file_size=os.path.getsize(chunk_path),
            overlap_start=0.0,
            overlap_end=0.0,
            speaker_segments=speakers,
            is_whole_file=True
        )
        
        logger.info(f"Created whole file chunk: {chunk.chunk_id} ({chunk.duration:.2f}s)")
        return [chunk]
    
    def _create_overlapping_chunks(self, audio_path: str, audio: AudioSegment, speaker_segments: List[SpeakerSegment]) -> List[AudioChunk]:
        """Create overlapping chunks based on speaker boundaries and duration."""
        chunks = []
        total_duration = len(audio) / 1000.0
        
        # Create chunk boundaries based on speaker segments and target duration
        chunk_boundaries = self._calculate_chunk_boundaries(speaker_segments, total_duration)
        
        logger.info(f"Calculated {len(chunk_boundaries)} chunk boundaries: {chunk_boundaries}")
        
        for i, (start_time, end_time) in enumerate(chunk_boundaries):
            # Add overlap to previous and next chunks
            overlap_start = self.overlap_duration if i > 0 else 0.0
            overlap_end = self.overlap_duration if i < len(chunk_boundaries) - 1 else 0.0
            
            # Calculate actual chunk boundaries with overlap
            chunk_start = max(0.0, start_time - overlap_start)
            chunk_end = min(total_duration, end_time + overlap_end)
            
            # Skip chunks that are too short
            if chunk_end - chunk_start < self.min_chunk_duration:
                logger.warning(f"Skipping chunk {i+1}: too short ({chunk_end - chunk_start:.2f}s)")
                continue
            
            # Extract audio chunk
            start_ms = int(chunk_start * 1000)
            end_ms = int(chunk_end * 1000)
            chunk_audio = audio[start_ms:end_ms]
            
            # Save chunk to file
            chunk_id = f"chunk_{i+1:03d}_{uuid.uuid4().hex[:8]}"
            chunk_path = os.path.join(self.temp_dir, f"{chunk_id}.wav")
            chunk_audio.export(chunk_path, format="wav")
            
            # Find speakers in this chunk
            chunk_speakers = self._get_speakers_in_range(speaker_segments, start_time, end_time)
            
            chunk = AudioChunk(
                chunk_id=chunk_id,
                file_path=chunk_path,
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                file_size=os.path.getsize(chunk_path),
                overlap_start=overlap_start,
                overlap_end=overlap_end,
                speaker_segments=chunk_speakers,
                is_whole_file=False
            )
            
            chunks.append(chunk)
            logger.info(f"Created chunk {i+1}: {chunk.chunk_id} ({chunk.start_time:.2f}s-{chunk.end_time:.2f}s, "
                       f"overlap: {overlap_start:.1f}s/{overlap_end:.1f}s, speakers: {chunk_speakers})")
        
        logger.info(f"Created {len(chunks)} overlapping chunks")
        return chunks
    
    def _calculate_chunk_boundaries(self, speaker_segments: List[SpeakerSegment], total_duration: float) -> List[Tuple[float, float]]:
        """
        Calculate optimal chunk boundaries based on speaker segments and target duration.
        
        Args:
            speaker_segments: List of speaker segments
            total_duration: Total audio duration
            
        Returns:
            List[Tuple[float, float]]: List of (start_time, end_time) boundaries
        """
        if not speaker_segments:
            # Fallback: create chunks based on target duration only
            boundaries = []
            current_time = 0.0
            while current_time < total_duration:
                end_time = min(current_time + self.target_chunk_duration, total_duration)
                boundaries.append((current_time, end_time))
                current_time = end_time
            return boundaries
        
        boundaries = []
        current_start = 0.0
        current_duration = 0.0
        
        # Sort segments by start time
        sorted_segments = sorted(speaker_segments, key=lambda x: x.start_time)
        
        for i, segment in enumerate(sorted_segments):
            segment_duration = segment.end_time - segment.start_time
            
            # Check if adding this segment would exceed max duration
            if current_duration + segment_duration > self.max_chunk_duration:
                # Close current chunk
                if current_duration >= self.min_chunk_duration:
                    boundaries.append((current_start, segment.start_time))
                    current_start = segment.start_time
                    current_duration = segment_duration
                else:
                    # Current chunk too short, extend it
                    current_duration += segment_duration
            
            # Check if we've reached target duration and can find a good break point
            elif current_duration + segment_duration >= self.target_chunk_duration:
                # Look for speaker change as natural break point
                if i < len(sorted_segments) - 1:
                    next_segment = sorted_segments[i + 1]
                    if segment.speaker_id != next_segment.speaker_id:
                        # Good break point: speaker change
                        boundaries.append((current_start, segment.end_time))
                        current_start = segment.end_time
                        current_duration = 0.0
                        continue
                
                current_duration += segment_duration
            else:
                current_duration += segment_duration
        
        # Add final chunk
        if current_duration >= self.min_chunk_duration:
            boundaries.append((current_start, total_duration))
        elif boundaries:
            # Extend last chunk to include remaining audio
            boundaries[-1] = (boundaries[-1][0], total_duration)
        else:
            # Single chunk for entire audio
            boundaries.append((0.0, total_duration))
        
        return boundaries
    
    def _get_speakers_in_range(self, speaker_segments: List[SpeakerSegment], start_time: float, end_time: float) -> List[str]:
        """Get list of speakers present in the given time range."""
        speakers = set()
        for segment in speaker_segments:
            # Check if segment overlaps with chunk
            if segment.start_time < end_time and segment.end_time > start_time:
                speakers.add(segment.speaker_id)
        return sorted(list(speakers))
    
    def _create_fallback_chunk(self, audio_path: str) -> List[AudioChunk]:
        """Create a fallback single chunk in case of errors."""
        try:
            audio = AudioSegment.from_file(audio_path)
            chunk_id = f"chunk_fallback_{uuid.uuid4().hex[:8]}"
            chunk_path = os.path.join(self.temp_dir, f"{chunk_id}.wav")
            audio.export(chunk_path, format="wav")
            
            return [AudioChunk(
                chunk_id=chunk_id,
                file_path=chunk_path,
                start_time=0.0,
                end_time=len(audio) / 1000.0,
                duration=len(audio) / 1000.0,
                file_size=os.path.getsize(chunk_path),
                overlap_start=0.0,
                overlap_end=0.0,
                speaker_segments=["Speaker_1"],
                is_whole_file=True
            )]
        except Exception as e:
            logger.error(f"Failed to create fallback chunk: {str(e)}")
            return []
    
    def cleanup_temp_files(self):
        """Clean up temporary chunk files."""
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up chunk directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up chunk files: {str(e)}")

class OverlapDeduplicator:
    """
    Handles deduplication of overlapped text from chunk transcriptions.
    """
    
    def __init__(self, similarity_threshold: float = 0.8):
        """
        Initialize the overlap deduplicator.
        
        Args:
            similarity_threshold: Threshold for text similarity to consider as duplicate
        """
        self.similarity_threshold = similarity_threshold
        logger.info(f"Initialized OverlapDeduplicator with threshold: {similarity_threshold}")
    
    def deduplicate_transcriptions(self, chunk_transcriptions: List) -> str:
        """
        Remove overlapped text from chunk transcriptions and merge into final transcript.
        
        Args:
            chunk_transcriptions: List of ChunkTranscription objects
            
        Returns:
            str: Final deduplicated transcription
        """
        if not chunk_transcriptions:
            return ""
        
        if len(chunk_transcriptions) == 1:
            return chunk_transcriptions[0].transcription
        
        logger.info(f"Deduplicating {len(chunk_transcriptions)} chunk transcriptions")
        
        # Sort chunks by start time
        sorted_chunks = sorted(chunk_transcriptions, key=lambda x: x.start_time)
        
        final_text = ""
        
        for i, chunk in enumerate(sorted_chunks):
            chunk_text = chunk.transcription.strip()
            
            if i == 0:
                # First chunk: use full text
                final_text = chunk_text
                logger.info(f"Chunk 1: Added full text ({len(chunk_text)} chars)")
            else:
                # Remove overlap from beginning of current chunk
                deduplicated_text = self._remove_overlap_start(
                    chunk_text, 
                    final_text, 
                    chunk.overlap_start
                )
                
                final_text += " " + deduplicated_text
                logger.info(f"Chunk {i+1}: Added deduplicated text ({len(deduplicated_text)} chars)")
        
        logger.info(f"Final transcription length: {len(final_text)} characters")
        return final_text.strip()
    
    def _remove_overlap_start(self, current_text: str, previous_text: str, overlap_duration: float) -> str:
        """
        Remove overlapped text from the beginning of current chunk.
        
        Args:
            current_text: Text from current chunk
            previous_text: Accumulated text from previous chunks
            overlap_duration: Duration of overlap in seconds
            
        Returns:
            str: Text with overlap removed
        """
        if overlap_duration <= 0:
            return current_text
        
        # Estimate overlap text length (rough approximation: 3 words per second)
        estimated_overlap_words = int(overlap_duration * 3)
        
        current_words = current_text.split()
        if len(current_words) <= estimated_overlap_words:
            # If current text is shorter than estimated overlap, use similarity check
            return self._similarity_based_deduplication(current_text, previous_text)
        
        # Try different overlap lengths around the estimate
        best_text = current_text
        best_similarity = 0.0
        
        for overlap_words in range(max(1, estimated_overlap_words - 2), 
                                 min(len(current_words), estimated_overlap_words + 3)):
            
            overlap_text = " ".join(current_words[:overlap_words])
            remaining_text = " ".join(current_words[overlap_words:])
            
            # Check if overlap text appears in previous text
            similarity = self._calculate_text_similarity(overlap_text, previous_text[-len(overlap_text)*2:])
            
            if similarity > best_similarity and similarity > self.similarity_threshold:
                best_text = remaining_text
                best_similarity = similarity
        
        if best_similarity > self.similarity_threshold:
            logger.debug(f"Removed overlap with similarity {best_similarity:.3f}")
            return best_text
        else:
            logger.debug(f"No significant overlap found (best similarity: {best_similarity:.3f})")
            return current_text
    
    def _similarity_based_deduplication(self, current_text: str, previous_text: str) -> str:
        """Fallback deduplication based on text similarity."""
        # Simple approach: if current text is very similar to end of previous text, skip it
        prev_end = previous_text[-len(current_text):] if len(previous_text) > len(current_text) else previous_text
        similarity = self._calculate_text_similarity(current_text, prev_end)
        
        if similarity > self.similarity_threshold:
            logger.debug(f"Skipping similar text (similarity: {similarity:.3f})")
            return ""
        return current_text
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two text strings.
        
        Args:
            text1: First text string
            text2: Second text string
            
        Returns:
            float: Similarity score between 0 and 1
        """
        if not text1 or not text2:
            return 0.0
        
        # Simple word-based similarity
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0 