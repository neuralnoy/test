"""
Whisper Transcriber for parallel channel-based transcription.
Handles concurrent transcription with rate limiting to avoid API blocks.
"""
import asyncio
from typing import List, Optional
from app_whisper.models.schemas import AudioChunk, TranscribedChunk, WhisperTranscriptionResult
from common_new.azure_openai_service import AzureOpenAIServiceWhisper
from common_new.token_client import TokenClient
from common_new.logger import get_logger

logger = get_logger("mono_businesslogic_transcriber")

class WhisperTranscriber:
    """Handles parallel Whisper transcription for a list of audio chunks."""
    
    def __init__(self, app_id: str = "whisper_app"):
        """
        Initializes the WhisperTranscriber.

        Args:
            app_id: The application ID for the token client, used for rate limiting.
        """
        self.token_client = TokenClient(app_id=app_id)
        self.whisper_service = AzureOpenAIServiceWhisper(token_client=self.token_client)
        logger.info("Initialized WhisperTranscriber.")

    async def _transcribe_one_chunk(self, chunk: AudioChunk, language: Optional[str]) -> TranscribedChunk:
        """
        Transcribes a single audio chunk using the Whisper service.

        Args:
            chunk: The AudioChunk to transcribe.
            language: The language of the audio.

        Returns:
            A TranscribedChunk object containing the result.
        """
        logger.info(f"Starting transcription for chunk: {chunk.file_path} ({chunk.start_time:.2f}s - {chunk.end_time:.2f}s)")
        try:
            # Request verbose JSON with segment-level timestamps for diarization mapping.
            transcription_result_dict = await self.whisper_service.transcribe_audio(
                audio_file_path=chunk.file_path,
                language=language,
                prompt=None,
                temperature=0.0,
                response_format="verbose_json",
                timestamp_granularities=["segment"]
            )

            if transcription_result_dict and "text" in transcription_result_dict:
                # The result is already a dict, so we can validate it directly.
                transcription_result = WhisperTranscriptionResult.model_validate(transcription_result_dict)
                logger.info(f"Successfully transcribed chunk: {chunk.file_path}")
                return TranscribedChunk(chunk=chunk, transcription_result=transcription_result)
            else:
                error_msg = f"Transcription returned an invalid or empty result: {transcription_result_dict}"
                logger.error(f"Failed to transcribe chunk {chunk.file_path}: {error_msg}")
                return TranscribedChunk(chunk=chunk, error=error_msg)

        except Exception as e:
            error_msg = f"An unexpected error occurred during transcription of {chunk.file_path}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return TranscribedChunk(chunk=chunk, error=error_msg)

    async def transcribe_chunks(self, chunks: List[AudioChunk], language: Optional[str] = None) -> List[TranscribedChunk]:
        """
        Transcribes a list of audio chunks concurrently.

        Args:
            chunks: A list of AudioChunk objects to be transcribed.
            language: The language of the audio. If None, Whisper will detect it.

        Returns:
            A list of TranscribedChunk objects with the results.
        """
        if not chunks:
            logger.warning("No chunks provided to transcribe.")
            return []
        
        logger.info(f"Starting concurrent transcription for {len(chunks)} chunks.")
        
        tasks = [self._transcribe_one_chunk(chunk, language) for chunk in chunks]
        
        transcribed_chunks = await asyncio.gather(*tasks)
        
        logger.info(f"Finished transcription for all {len(chunks)} chunks.")
        
        return transcribed_chunks