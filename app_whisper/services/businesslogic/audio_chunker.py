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
                 target_chunk_size_mb: float = 23.0,  # Target chunk size (slightly under limit)
                 overlap_duration: float = 3.0,
                 min_chunk_duration: float = 30.0):  # Minimum chunk duration (increased)
        """
        Initialize the audio chunker.
        
        Args:
            max_file_size_mb: Maximum file size in MB to process as whole file
            target_chunk_size_mb: Target size for each chunk in MB (should be < max_file_size_mb)
            overlap_duration: Overlap duration between chunks (seconds)
            min_chunk_duration: Minimum duration for a chunk (seconds)
        """
        self.max_file_size_mb = max_file_size_mb
        self.target_chunk_size_mb = target_chunk_size_mb
        self.overlap_duration = overlap_duration
        self.min_chunk_duration = min_chunk_duration
        self.temp_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
        
        logger.info(f"Initialized AudioChunker: max_size={max_file_size_mb}MB, "
                   f"target_size={target_chunk_size_mb}MB, overlap={overlap_duration}s")
    
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
        """Create size-based chunks with smart speaker boundaries."""
        chunks = []
        total_duration = len(audio) / 1000.0
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        
        # Calculate optimal number of chunks based on file size
        num_chunks_needed = max(1, int(file_size_mb / self.target_chunk_size_mb))
        target_chunk_duration = total_duration / num_chunks_needed
        
        logger.info(f"File: {file_size_mb:.1f}MB, {total_duration:.1f}s")
        logger.info(f"Target: {num_chunks_needed} chunks of ~{target_chunk_duration:.1f}s each (~{self.target_chunk_size_mb}MB)")
        
        # Create chunk boundaries based on size and speaker segments
        chunk_boundaries = self._calculate_size_based_boundaries(
            speaker_segments, total_duration, target_chunk_duration, num_chunks_needed
        )
        
        logger.info(f"Calculated {len(chunk_boundaries)} chunk boundaries")
        
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
            
            # Get actual file size
            actual_size_mb = os.path.getsize(chunk_path) / (1024 * 1024)
            
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
            logger.info(f"Created chunk {i+1}: {chunk.chunk_id} ({chunk.start_time:.1f}s-{chunk.end_time:.1f}s, "
                       f"{actual_size_mb:.1f}MB, speakers: {len(chunk_speakers)})")
        
        total_chunks_size = sum(os.path.getsize(chunk.file_path) for chunk in chunks) / (1024 * 1024)
        logger.info(f"Created {len(chunks)} chunks, total size: {total_chunks_size:.1f}MB")
        return chunks
    
    def _calculate_size_based_boundaries(self, speaker_segments: List[SpeakerSegment], total_duration: float, 
                                        target_chunk_duration: float, num_chunks_needed: int) -> List[Tuple[float, float]]:
        """
        Calculate optimal chunk boundaries based on file size and speaker segments.
        
        Args:
            speaker_segments: List of speaker segments
            total_duration: Total audio duration
            target_chunk_duration: Target duration for each chunk
            num_chunks_needed: Number of chunks needed based on file size
            
        Returns:
            List[Tuple[float, float]]: List of (start_time, end_time) boundaries
        """
        if not speaker_segments or num_chunks_needed == 1:
            # Fallback: create chunks based on target duration only
            boundaries = []
            current_time = 0.0
            for i in range(num_chunks_needed):
                end_time = min(current_time + target_chunk_duration, total_duration)
                boundaries.append((current_time, end_time))
                current_time = end_time
            return boundaries
        
        boundaries = []
        
        # Sort segments by start time
        sorted_segments = sorted(speaker_segments, key=lambda x: x.start_time)
        
        # Calculate ideal chunk break points
        ideal_break_points = []
        for i in range(1, num_chunks_needed):
            ideal_time = i * target_chunk_duration
            ideal_break_points.append(ideal_time)
        
        logger.info(f"Ideal break points: {[f'{t:.1f}s' for t in ideal_break_points]}")
        
        # Find actual break points near ideal points, preferring speaker boundaries
        actual_break_points = []
        
        for ideal_time in ideal_break_points:
            best_break_time = ideal_time
            min_penalty = float('inf')
            
            # Look for speaker boundaries within a reasonable window around ideal time
            search_window = min(target_chunk_duration * 0.3, 60.0)  # 30% of target duration or 60s max
            
            for segment in sorted_segments:
                # Check segment end as potential break point
                segment_end = segment.end_time
                if abs(segment_end - ideal_time) <= search_window:
                    # Calculate penalty: distance from ideal + speaker continuity penalty
                    time_penalty = abs(segment_end - ideal_time)
                    
                    # Check if this creates a speaker boundary (good) or cuts mid-speaker (bad)
                    next_segments = [s for s in sorted_segments if s.start_time >= segment_end]
                    if next_segments and next_segments[0].speaker_id != segment.speaker_id:
                        speaker_penalty = 0  # Good: natural speaker boundary
                    else:
                        speaker_penalty = 10  # Bad: cutting mid-speaker
                    
                    total_penalty = time_penalty + speaker_penalty
                    
                    if total_penalty < min_penalty:
                        min_penalty = total_penalty
                        best_break_time = segment_end
            
            actual_break_points.append(best_break_time)
        
        logger.info(f"Actual break points: {[f'{t:.1f}s' for t in actual_break_points]}")
        
        # Create boundaries
        current_start = 0.0
        for break_point in actual_break_points:
            boundaries.append((current_start, break_point))
            current_start = break_point
        
        # Add final chunk
        boundaries.append((current_start, total_duration))
        
        # Validate and adjust boundaries
        validated_boundaries = []
        for start, end in boundaries:
            duration = end - start
            if duration >= self.min_chunk_duration:
                validated_boundaries.append((start, end))
            else:
                logger.warning(f"Chunk too short ({duration:.1f}s), merging with previous")
                if validated_boundaries:
                    # Merge with previous chunk
                    prev_start, _ = validated_boundaries[-1]
                    validated_boundaries[-1] = (prev_start, end)
                else:
                    # First chunk, keep it anyway
                    validated_boundaries.append((start, end))
        
        return validated_boundaries
    
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