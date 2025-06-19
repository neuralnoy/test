"""
Whisper Transcriber for parallel channel-based transcription.
Handles concurrent transcription with rate limiting to avoid API blocks.
"""
import asyncio
from typing import Dict, List
from app_whisper.models.schemas import AudioChunk, TranscribedChunk, WhisperTranscriptionResult
from common_new.azure_openai_service import AzureOpenAIServiceWhisper
from common_new.logger import get_logger

logger = get_logger("businesslogic")

class WhisperTranscriber:
    """Handles parallel Whisper transcription with rate limiting."""

    def __init__(self):
        """Initialize the Whisper transcriber."""
        self.whisper_service = AzureOpenAIServiceWhisper(app_id="whisper_app")
        logger.info("Initialized WhisperTranscriber with AzureOpenAIServiceWhisper.")

    async def transcribe_chunks(self, all_audio_chunks: Dict[str, List[AudioChunk]]) -> List[TranscribedChunk]:
        """
        Transcribes all audio chunks from all speakers concurrently.

        Args:
            all_audio_chunks: A dictionary mapping speaker_id to a list of AudioChunk objects.

        Returns:
            A list of TranscribedChunk objects containing the original chunk info and transcription result.
        """
        # 1. Flatten the list of chunks to prepare for concurrent processing
        flat_chunk_list = [chunk for chunks in all_audio_chunks.values() for chunk in chunks]
        
        if not flat_chunk_list:
            logger.info("No audio chunks to transcribe.")
            return []

        file_paths = [chunk.file_path for chunk in flat_chunk_list]
        logger.info(f"Starting transcription for {len(file_paths)} chunks.")

        # 2. Transcribe all chunks concurrently. The service handles rate limiting.
        # We need segment-level and word-level timestamps for later processing.
        transcription_results = await self.whisper_service.transcribe_audio_chunks(
            file_paths,
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"]
        )

        # 3. Map results back to the original chunks
        transcribed_chunks: List[TranscribedChunk] = []
        for i, chunk in enumerate(flat_chunk_list):
            result_dict = transcription_results[i]

            if result_dict.get("error"):
                logger.error(f"Transcription failed for chunk {chunk.file_path}: {result_dict['error']}")
                transcribed_chunks.append(TranscribedChunk(chunk=chunk, error=result_dict["error"]))
            else:
                try:
                    # The result from a successful verbose_json call will be parsed
                    # by the robust WhisperTranscriptionResult model.
                    transcription_result = WhisperTranscriptionResult(**result_dict)
                    
                    transcribed_chunks.append(
                        TranscribedChunk(chunk=chunk, transcription_result=transcription_result)
                    )
                    logger.debug(f"Successfully transcribed chunk {chunk.file_path}")
                except Exception as e:
                    logger.error(f"Failed to parse transcription result for chunk {chunk.file_path}: {e}")
                    transcribed_chunks.append(TranscribedChunk(chunk=chunk, error=str(e)))
        
        logger.info(f"Finished transcription for {len(file_paths)} chunks.")
        return transcribed_chunks