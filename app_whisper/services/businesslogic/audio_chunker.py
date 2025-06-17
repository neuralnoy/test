"""
Audio Chunker for channel-based speaker diarization.
Handles size-based chunking while maintaining timestamp alignment between channels.
"""
import os
import tempfile
import soundfile as sf
from typing import Tuple, List, Dict, Any
from app_whisper.models.schemas import ChannelInfo, AudioChunk
from common_new.logger import get_logger

logger = get_logger("audio_chunker")

class AudioChunker:
    """Simple size-based audio chunker for channel processing."""
    
    def __init__(self, max_file_size_mb: float = 24.0):
        """
        Initialize the chunker.
        
        Args:
            max_file_size_mb: Maximum file size in MB for Whisper processing
        """
        self.max_file_size_mb = max_file_size_mb
        self.temp_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
        logger.info(f"Initialized AudioChunker with max size: {max_file_size_mb}MB")
        logger.info(f"Using temp directory: {self.temp_dir}")
    
    async def create_channel_chunks(self, channel_info_list: List[ChannelInfo]) -> Tuple[bool, List[AudioChunk], str]:
        """
        Create chunks for each channel while maintaining timestamp alignment.
        
        Args:
            channel_info_list: List of ChannelInfo objects for each channel
            
        Returns:
            Tuple[bool, List[AudioChunk], str]: (success, audio_chunks, error_message)
        """
        try:
            logger.info(f"Starting chunking process for {len(channel_info_list)} channels")
            
            # Check if any channel needs chunking
            needs_chunking = any(ch.file_size_mb > self.max_file_size_mb for ch in channel_info_list)
            
            if not needs_chunking:
                logger.info("All channels are under size limit, creating single chunks")
                return await self._create_single_chunks(channel_info_list)
            else:
                logger.info("Some channels exceed size limit, creating multiple chunks")
                return await self._create_multiple_chunks(channel_info_list)
                
        except Exception as e:
            error_msg = f"Error in audio chunking: {str(e)}"
            logger.error(error_msg)
            return False, [], error_msg
    
    async def _create_single_chunks(self, channel_info_list: List[ChannelInfo]) -> Tuple[bool, List[AudioChunk], str]:
        """
        Create single chunks (no splitting needed).
        
        Args:
            channel_info_list: List of ChannelInfo objects
            
        Returns:
            Tuple[bool, List[AudioChunk], str]: (success, audio_chunks, error_message)
        """
        try:
            audio_chunks = []
            
            for i, channel_info in enumerate(channel_info_list):
                chunk_id = f"{channel_info.speaker_id}_chunk_0"
                
                # Create AudioChunk with full file
                audio_chunk = AudioChunk(
                    chunk_id=chunk_id,
                    channel_info=channel_info,
                    start_time=0.0,
                    end_time=channel_info.duration,
                    file_path=channel_info.file_path,
                    file_size_mb=channel_info.file_size_mb
                )
                
                audio_chunks.append(audio_chunk)
                logger.info(f"Created single chunk for {channel_info.speaker_id}: {channel_info.duration:.2f}s")
            
            return True, audio_chunks, ""
            
        except Exception as e:
            error_msg = f"Error creating single chunks: {str(e)}"
            logger.error(error_msg)
            return False, [], error_msg
    
    async def _create_multiple_chunks(self, channel_info_list: List[ChannelInfo]) -> Tuple[bool, List[AudioChunk], str]:
        """
        Create multiple chunks by dividing duration equally.
        
        Args:
            channel_info_list: List of ChannelInfo objects
            
        Returns:
            Tuple[bool, List[AudioChunk], str]: (success, audio_chunks, error_message)
        """
        try:
            # Calculate number of chunks needed based on largest file
            max_file_size = max(ch.file_size_mb for ch in channel_info_list)
            num_chunks = int(max_file_size / self.max_file_size_mb) + 1
            
            logger.info(f"Creating {num_chunks} chunks per channel (max file size: {max_file_size:.2f}MB)")
            
            # Use the longest duration as reference for alignment
            max_duration = max(ch.duration for ch in channel_info_list)
            chunk_duration = max_duration / num_chunks
            
            logger.info(f"Chunk duration: {chunk_duration:.2f}s per chunk")
            
            audio_chunks = []
            
            # Process each channel
            for channel_info in channel_info_list:
                success, channel_chunks, error = await self._split_channel_into_chunks(
                    channel_info, 
                    num_chunks, 
                    chunk_duration
                )
                
                if not success:
                    return False, [], f"Failed to chunk {channel_info.speaker_id}: {error}"
                
                audio_chunks.extend(channel_chunks)
                logger.info(f"Created {len(channel_chunks)} chunks for {channel_info.speaker_id}")
            
            # Sort chunks by start time for proper processing order
            audio_chunks.sort(key=lambda x: (x.start_time, x.channel_info.speaker_id))
            
            logger.info(f"Total chunks created: {len(audio_chunks)}")
            return True, audio_chunks, ""
            
        except Exception as e:
            error_msg = f"Error creating multiple chunks: {str(e)}"
            logger.error(error_msg)
            return False, [], error_msg
    
    async def _split_channel_into_chunks(self, 
                                       channel_info: ChannelInfo, 
                                       num_chunks: int, 
                                       chunk_duration: float) -> Tuple[bool, List[AudioChunk], str]:
        """
        Split a single channel into multiple chunks.
        
        Args:
            channel_info: Channel information
            num_chunks: Number of chunks to create
            chunk_duration: Duration of each chunk in seconds
            
        Returns:
            Tuple[bool, List[AudioChunk], str]: (success, chunk_list, error_message)
        """
        try:
            # Load the audio file
            audio_data, sample_rate = sf.read(channel_info.file_path)
            
            chunks = []
            
            for chunk_idx in range(num_chunks):
                start_time = chunk_idx * chunk_duration
                end_time = min(start_time + chunk_duration, channel_info.duration)
                
                # Skip if this chunk would be too short
                if end_time - start_time < 1.0:  # Minimum 1 second
                    logger.warning(f"Skipping chunk {chunk_idx} for {channel_info.speaker_id} (too short: {end_time - start_time:.2f}s)")
                    continue
                
                # Calculate sample indices
                start_sample = int(start_time * sample_rate)
                end_sample = int(end_time * sample_rate)
                
                # Extract chunk audio data
                chunk_audio = audio_data[start_sample:end_sample]
                
                # Create chunk file
                chunk_filename = f"{channel_info.speaker_id}_chunk_{chunk_idx}.wav"
                chunk_path = os.path.join(self.temp_dir, chunk_filename)
                
                # Save chunk as WAV
                sf.write(chunk_path, chunk_audio, sample_rate, format='WAV', subtype='PCM_16')
                
                # Calculate chunk file size
                chunk_size_bytes = os.path.getsize(chunk_path)
                chunk_size_mb = chunk_size_bytes / (1024 * 1024)
                
                # Create AudioChunk object
                chunk_id = f"{channel_info.speaker_id}_chunk_{chunk_idx}"
                audio_chunk = AudioChunk(
                    chunk_id=chunk_id,
                    channel_info=channel_info,
                    start_time=start_time,
                    end_time=end_time,
                    file_path=chunk_path,
                    file_size_mb=chunk_size_mb
                )
                
                chunks.append(audio_chunk)
                logger.info(f"Created chunk {chunk_idx}: {start_time:.2f}s-{end_time:.2f}s ({chunk_size_mb:.2f}MB)")
            
            return True, chunks, ""
            
        except Exception as e:
            error_msg = f"Error splitting channel {channel_info.speaker_id}: {str(e)}"
            logger.error(error_msg)
            return False, [], error_msg
    
    def get_chunk_info_summary(self, audio_chunks: List[AudioChunk]) -> Dict[str, Any]:
        """
        Get summary information about the chunks created.
        
        Args:
            audio_chunks: List of AudioChunk objects
            
        Returns:
            Dict with summary information
        """
        if not audio_chunks:
            return {}
        
        # Group by speaker
        speaker_chunks = {}
        for chunk in audio_chunks:
            speaker_id = chunk.channel_info.speaker_id
            if speaker_id not in speaker_chunks:
                speaker_chunks[speaker_id] = []
            speaker_chunks[speaker_id].append(chunk)
        
        # Calculate totals
        total_chunks = len(audio_chunks)
        total_duration = sum(chunk.end_time - chunk.start_time for chunk in audio_chunks)
        total_size_mb = sum(chunk.file_size_mb for chunk in audio_chunks)
        
        summary = {
            'total_chunks': total_chunks,
            'total_duration': total_duration,
            'total_size_mb': total_size_mb,
            'speakers': {}
        }
        
        for speaker_id, chunks in speaker_chunks.items():
            summary['speakers'][speaker_id] = {
                'chunk_count': len(chunks),
                'duration': sum(chunk.end_time - chunk.start_time for chunk in chunks),
                'size_mb': sum(chunk.file_size_mb for chunk in chunks)
            }
        
        return summary
    
    def cleanup(self):
        """Clean up temporary chunk files."""
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up chunker temp directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up chunker temp directory {self.temp_dir}: {str(e)}")
    
    def __del__(self):
        """Cleanup on object destruction."""
        self.cleanup()
