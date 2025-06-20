"""
Audio Chunker for mono audio files.
Handles size-based chunking for large audio files before transcription.
"""
import math
import os
import tempfile
import soundfile as sf
from typing import List
from app_whisper.models.schemas import AudioChunk
from common_new.logger import get_logger

logger = get_logger("businesslogic")

class AudioChunker:
    """Chunks a single mono audio file based on size."""

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

    def chunk_audio(self, file_path: str, audio_info: dict) -> List[AudioChunk]:
        """
        Chunks a mono audio file if it exceeds the size limit.
        
        Args:
            file_path: The path to the mono audio file.
            audio_info: A dictionary containing 'file_size_mb' and 'duration'.
            
        Returns:
            A list of AudioChunk objects.
        """
        logger.info("Starting audio chunking process...")
        
        file_size_mb = audio_info.get('file_size_mb', 0)
        duration = audio_info.get('duration', 0)

        if file_size_mb <= self.max_chunk_size_mb:
            logger.info("No chunking needed. Audio file is within size limits.")
            return [AudioChunk(
                file_path=file_path,
                speaker_id="mono",
                start_time=0.0,
                end_time=duration
            )]

        logger.info("Chunking required. Audio file exceeds size limit.")

        # --- Chunking Logic ---
        num_chunks = math.ceil(file_size_mb / self.max_chunk_size_mb)
        logger.info(f"File size is {file_size_mb:.2f}MB. Will create {num_chunks} chunks.")
        
        chunk_duration = duration / num_chunks
        logger.info(f"Total duration is {duration:.2f}s. Each chunk will be ~{chunk_duration:.2f}s.")
        
        audio_chunks = []
        try:
            audio_data, sample_rate = sf.read(file_path)
        except Exception as e:
            logger.error(f"Failed to read audio file {file_path}: {e}")
            raise

        for i in range(num_chunks):
            start_time = i * chunk_duration
            end_time = (i + 1) * chunk_duration
            if end_time > duration:
                end_time = duration
            
            start_sample = int(start_time * sample_rate)
            end_sample = int(end_time * sample_rate)

            chunk_audio_data = audio_data[start_sample:end_sample]

            chunk_filename = f"mono_chunk_{i+1}.flac"
            chunk_filepath = os.path.join(self.temp_dir, chunk_filename)

            try:
                sf.write(chunk_filepath, chunk_audio_data, sample_rate, format='FLAC', subtype='PCM_16')
                logger.info(f"Saved chunk {i+1} to {chunk_filepath}")
            except Exception as e:
                logger.error(f"Failed to write chunk file {chunk_filepath}: {e}")
                raise

            chunk = AudioChunk(
                file_path=chunk_filepath,
                speaker_id="mono",
                start_time=start_time,
                end_time=end_time
            )
            audio_chunks.append(chunk)

        logger.info("Audio chunking process completed successfully.")
        return audio_chunks

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