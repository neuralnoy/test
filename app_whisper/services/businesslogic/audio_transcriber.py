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

        # 2. Create a list of transcription tasks to be run concurrently.
        tasks = []
        for file_path in file_paths:
            task = self.whisper_service.transcribe_audio(
                file_path,
                response_format="verbose_json",
                timestamp_granularities=["segment"] # Only segment is supported
            )
            tasks.append(task)
        
        # 3. Run all transcription tasks concurrently. asyncio.gather will run them in parallel.
        # The underlying service will handle rate-limiting with the app_counter.
        transcription_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 4. Map results back to the original chunks
        transcribed_chunks: List[TranscribedChunk] = []
        for i, chunk in enumerate(flat_chunk_list):
            result_or_exc = transcription_results[i]

            if isinstance(result_or_exc, Exception):
                error_msg = str(result_or_exc)
                logger.error(f"Transcription failed for chunk {chunk.file_path}: {error_msg}")
                transcribed_chunks.append(TranscribedChunk(chunk=chunk, error=error_msg))
            elif result_or_exc.get("error"):
                logger.error(f"Transcription failed for chunk {chunk.file_path}: {result_or_exc['error']}")
                transcribed_chunks.append(TranscribedChunk(chunk=chunk, error=result_or_exc["error"]))
            else:
                try:
                    # The result from a successful verbose_json call will be parsed
                    # by the robust WhisperTranscriptionResult model.
                    transcription_result = WhisperTranscriptionResult(**result_or_exc)
                    
                    # --- Start of new logging ---
                    num_segments = len(transcription_result.segments)
                    logger.info(f"Successfully transcribed chunk {chunk.file_path}:")
                    logger.info(f"  - Text: '{transcription_result.text[:100]}...'")
                    logger.info(f"  - Metadata: {num_segments} segments found.")
                    # --- End of new logging ---
                    
                    transcribed_chunks.append(
                        TranscribedChunk(chunk=chunk, transcription_result=transcription_result)
                    )
                except Exception as e:
                    logger.error(f"Failed to parse transcription result for chunk {chunk.file_path}: {e}")
                    transcribed_chunks.append(TranscribedChunk(chunk=chunk, error=str(e)))
        
        logger.info(f"Finished transcription for {len(file_paths)} chunks.")
        return transcribed_chunks