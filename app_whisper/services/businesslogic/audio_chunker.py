"""
Audio Chunker for channel-based speaker diarization.
Handles size-based chunking while maintaining timestamp alignment between channels.
"""
import math
import os
import tempfile
import soundfile as sf
from typing import List, Dict
from app_whisper.models.schemas import ChannelInfo, AudioChunk
from common_new.logger import get_logger

logger = get_logger("businesslogic")

class AudioChunker:
    """Chunks audio files based on size while maintaining channel alignment."""

    def __init__(self, max_chunk_size_mb: float = 24.0):
        """
        Initialize the audio chunker.
        
        Args:
            max_chunk_size_mb: The maximum size for each chunk in megabytes.
        """
        self.max_chunk_size_mb = max_chunk_size_mb
        self.temp_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
        logger.info(f"Initialized AudioChunker with temp directory: {self.temp_dir}")
        logger.info(f"Max chunk size set to: {self.max_chunk_size_mb} MB")

    def chunk_audio(self, channel_info_list: List[ChannelInfo]) -> Dict[str, List[AudioChunk]]:
        """
        Chunks audio files for each channel if they exceed the size limit.
        
        Args:
            channel_info_list: A list of ChannelInfo objects from the preprocessor.
            
        Returns:
            A dictionary where keys are speaker_ids and values are lists of AudioChunk objects.
        """
        logger.info("Starting audio chunking process...")

        # Check if any channel exceeds the max size
        needs_chunking = any(info.file_size_mb > self.max_chunk_size_mb for info in channel_info_list)

        if not needs_chunking:
            logger.info("No chunking needed. All channel files are within size limits.")
            # Create a single chunk for each channel covering the full duration
            all_chunks = {}
            for info in channel_info_list:
                chunk = AudioChunk(
                    file_path=info.file_path,
                    speaker_id=info.speaker_id,
                    start_time=0.0,
                    end_time=info.duration
                )
                all_chunks[info.speaker_id] = [chunk]
            return all_chunks

        logger.info("Chunking required. At least one channel exceeds size limit.")

        # --- Chunking Logic ---
        # 1. Determine the number of chunks needed based on the largest file
        max_file_size = max(info.file_size_mb for info in channel_info_list)
        num_chunks = math.ceil(max_file_size / self.max_chunk_size_mb)
        logger.info(f"Largest channel file size is {max_file_size:.2f}MB. Will create {num_chunks} chunks.")

        # 2. Get total duration (should be the same for all channels)
        total_duration = channel_info_list[0].duration
        chunk_duration = total_duration / num_chunks
        logger.info(f"Total duration is {total_duration:.2f}s. Each chunk will be ~{chunk_duration:.2f}s.")

        all_chunks = {info.speaker_id: [] for info in channel_info_list}

        # 3. Process each channel
        for info in channel_info_list:
            logger.info(f"Chunking channel for {info.speaker_id} from file: {info.file_path}")
            
            try:
                audio_data, sample_rate = sf.read(info.file_path)
            except Exception as e:
                logger.error(f"Failed to read audio file {info.file_path}: {e}")
                raise

            # 4. Create chunks for this channel
            for i in range(num_chunks):
                start_time = i * chunk_duration
                end_time = (i + 1) * chunk_duration
                if end_time > total_duration:
                    end_time = total_duration
                
                start_sample = int(start_time * sample_rate)
                end_sample = int(end_time * sample_rate)

                chunk_audio_data = audio_data[start_sample:end_sample]

                chunk_filename = f"{info.speaker_id.replace('*', '')}_chunk_{i+1}.flac"
                chunk_filepath = os.path.join(self.temp_dir, chunk_filename)

                try:
                    sf.write(chunk_filepath, chunk_audio_data, sample_rate, format='FLAC', subtype='PCM_16')
                    logger.info(f"Saved chunk {i+1} for {info.speaker_id} to {chunk_filepath}")
                except Exception as e:
                    logger.error(f"Failed to write chunk file {chunk_filepath}: {e}")
                    raise

                chunk = AudioChunk(
                    file_path=chunk_filepath,
                    speaker_id=info.speaker_id,
                    start_time=start_time,
                    end_time=end_time
                )
                all_chunks[info.speaker_id].append(chunk)

        logger.info("Audio chunking process completed successfully.")
        return all_chunks

    def cleanup(self):
        """Clean up the temporary directory used for chunks."""
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temporary chunk directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up temp directory {self.temp_dir}: {str(e)}")

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()