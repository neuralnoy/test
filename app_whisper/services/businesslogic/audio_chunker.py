"""
Audio chunker for Step 4 of the whisper pipeline.
Handles simple audio chunking based on file size.
"""
import os
import tempfile
import uuid
from typing import List
from pydub import AudioSegment
from app_whisper.models.schemas import AudioChunk, SpeakerSegment
from common_new.logger import get_logger

logger = get_logger("whisper")

class AudioChunker:
    """
    Handles simple audio chunking for Whisper transcription.
    
    Simple logic:
    - If file is <= 24MB: send whole file
    - If file is > 24MB: create chunks of ~24MB each
    """
    
    def __init__(self, max_file_size_mb: float = 24.0):
        """
        Initialize the audio chunker.
        
        Args:
            max_file_size_mb: Maximum file size in MB to process as whole file
        """
        self.max_file_size_mb = max_file_size_mb
        self.temp_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
        
        logger.info(f"Initialized AudioChunker: max_size={max_file_size_mb}MB")
    
    def chunk_audio(self, audio_path: str, speaker_segments: List[SpeakerSegment]) -> List[AudioChunk]:
        """
        Create audio chunks for Whisper transcription.
        
        Args:
            audio_path: Path to the preprocessed audio file
            speaker_segments: List of speaker segments (used for metadata only)
            
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
            
            # Create size-based chunks
            logger.info(f"File size ({file_size_mb:.2f}MB) > {self.max_file_size_mb}MB, creating chunks")
            return self._create_size_based_chunks(audio_path, audio, speaker_segments)
            
        except Exception as e:
            logger.error(f"Error chunking audio {audio_path}: {str(e)}")
            # Fallback: create single chunk
            return self._create_fallback_chunk(audio_path)
    
    def _create_whole_file_chunk(self, audio_path: str, audio: AudioSegment, speaker_segments: List[SpeakerSegment]) -> List[AudioChunk]:
        """Create a single chunk for the whole file."""
        chunk_id = f"chunk_whole_{uuid.uuid4().hex[:8]}"
        chunk_path = os.path.join(self.temp_dir, f"{chunk_id}.wav")
        audio.export(chunk_path, format="wav")
        
        chunk = AudioChunk(
            chunk_id=chunk_id,
            file_path=chunk_path,
            start_time=0.0,
            end_time=len(audio) / 1000.0,
            duration=len(audio) / 1000.0,
            file_size=os.path.getsize(chunk_path),
            overlap_duration=0.0,
            speaker_segments=speaker_segments if speaker_segments else [],
            is_whole_file=True
        )
        
        logger.info(f"Created whole file chunk: {chunk.chunk_id} ({chunk.duration:.2f}s)")
        return [chunk]
    
    def _create_size_based_chunks(self, audio_path: str, audio: AudioSegment, speaker_segments: List[SpeakerSegment]) -> List[AudioChunk]:
        """Create chunks based on file size - each chunk should be ~24MB."""
        chunks = []
        total_duration = len(audio) / 1000.0
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        
        # Calculate how many chunks we need
        num_chunks_needed = max(1, int(file_size_mb / self.max_file_size_mb))
        if file_size_mb % self.max_file_size_mb > 0:
            num_chunks_needed += 1
            
        chunk_duration = total_duration / num_chunks_needed
        
        logger.info(f"Creating {num_chunks_needed} chunks of ~{chunk_duration:.1f}s each")
        
        for i in range(num_chunks_needed):
            start_time = i * chunk_duration
            end_time = min((i + 1) * chunk_duration, total_duration)
            
            # Extract audio chunk
            start_ms = int(start_time * 1000)
            end_ms = int(end_time * 1000)
            chunk_audio = audio[start_ms:end_ms]
            
            # Save chunk to file
            chunk_id = f"chunk_{i+1:03d}_{uuid.uuid4().hex[:8]}"
            chunk_path = os.path.join(self.temp_dir, f"{chunk_id}.wav")
            chunk_audio.export(chunk_path, format="wav")
            
            # Get actual file size
            actual_size_mb = os.path.getsize(chunk_path) / (1024 * 1024)
            
            # Get speaker segments for this chunk
            chunk_speakers = self._get_speakers_in_chunk(speaker_segments, start_time, end_time)
            
            chunk = AudioChunk(
                chunk_id=chunk_id,
                file_path=chunk_path,
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                file_size=os.path.getsize(chunk_path),
                overlap_duration=0.0,
                speaker_segments=chunk_speakers,
                is_whole_file=False
            )
            
            chunks.append(chunk)
            logger.info(f"Created chunk {i+1}: {chunk.chunk_id} ({start_time:.1f}s-{end_time:.1f}s, "
                       f"{actual_size_mb:.1f}MB, speakers: {len(chunk_speakers)})")
        
        total_chunks_size = sum(os.path.getsize(chunk.file_path) for chunk in chunks) / (1024 * 1024)
        logger.info(f"Created {len(chunks)} chunks, total size: {total_chunks_size:.1f}MB")
        return chunks
    
    def _get_speakers_in_chunk(self, speaker_segments: List[SpeakerSegment], start_time: float, end_time: float) -> List[SpeakerSegment]:
        """Get speaker segments that overlap with the chunk time range."""
        chunk_speakers = []
        for segment in speaker_segments:
            # Check if segment overlaps with chunk
            if segment.start_time < end_time and segment.end_time > start_time:
                # Adjust segment times to be relative to chunk start
                adjusted_segment = SpeakerSegment(
                    speaker_id=segment.speaker_id,
                    start_time=max(segment.start_time - start_time, 0.0),
                    end_time=min(segment.end_time - start_time, end_time - start_time),
                    confidence=segment.confidence
                )
                chunk_speakers.append(adjusted_segment)
        return chunk_speakers
    
    def _create_fallback_chunk(self, audio_path: str) -> List[AudioChunk]:
        """Create a fallback single chunk in case of errors."""
        try:
            audio = AudioSegment.from_file(audio_path)
            chunk_id = f"chunk_fallback_{uuid.uuid4().hex[:8]}"
            chunk_path = os.path.join(self.temp_dir, f"{chunk_id}.wav")
            audio.export(chunk_path, format="wav")
            
            # Create a default speaker segment for the entire chunk
            default_speaker = SpeakerSegment(
                speaker_id="Speaker_1",
                start_time=0.0,
                end_time=len(audio) / 1000.0,
                confidence=0.5
            )
            
            return [AudioChunk(
                chunk_id=chunk_id,
                file_path=chunk_path,
                start_time=0.0,
                end_time=len(audio) / 1000.0,
                duration=len(audio) / 1000.0,
                file_size=os.path.getsize(chunk_path),
                overlap_duration=0.0,
                speaker_segments=[default_speaker],
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
            return chunk_transcriptions[0].text
        
        logger.info(f"Deduplicating {len(chunk_transcriptions)} chunk transcriptions")
        
        # Sort chunks by start time
        sorted_chunks = sorted(chunk_transcriptions, key=lambda x: x.start_time)
        
        # For simplified chunker, just concatenate with spaces since there's no overlap
        final_text_parts = []
        for chunk in sorted_chunks:
            chunk_text = chunk.text.strip()
            if chunk_text:
                final_text_parts.append(chunk_text)
        
        final_text = " ".join(final_text_parts)
        logger.info(f"Final transcription length: {len(final_text)} characters")
        return final_text 