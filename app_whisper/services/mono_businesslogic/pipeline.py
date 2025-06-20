"""
Main audio processing pipeline for Azure OpenAI Whisper with channel-based speaker diarization.
Orchestrates the complete pipeline from audio download to final transcribed output.
"""
import time
import psutil
import os
from typing import Tuple
from app_whisper.models.schemas import InternalWhisperResult, ProcessingMetadata
from app_whisper.services.businesslogic.audio_downloader import AudioFileDownloader
from app_whisper.services.businesslogic.audio_preprocessor import AudioPreprocessor
from app_whisper.services.businesslogic.audio_diarizer import SpeakerDiarizer
from app_whisper.services.businesslogic.audio_chunker import AudioChunker
from app_whisper.services.businesslogic.audio_transcriber import WhisperTranscriber
from app_whisper.services.businesslogic.audio_postprocessor import TranscriptionPostProcessor
from common_new.logger import get_logger
from common_new.retry_helpers import with_token_limit_retry
from common_new.token_client import TokenClient

logger = get_logger("businesslogic")

async def process_audio(filename: str) -> Tuple[bool, InternalWhisperResult]:
    """
    Main entry point for audio processing pipeline with retry logic.
    This function is called by data_processor.py
    
    Args:
        filename: Name of the audio file to process (blob name in Azure Storage)
        
    Returns:
        Tuple[bool, InternalWhisperResult]: (success, result)
    """
    # Create a token client for pipeline-level retry logic
    token_client = TokenClient(app_id="whisper_app")
    
    # Wrapper function for retry logic
    async def _do_pipeline_processing():
        return await run_pipeline(filename)
    
    try:
        # Use retry logic for the entire pipeline to handle rate limits and transient failures
        return await with_token_limit_retry(
            _do_pipeline_processing,
            token_client,
            max_retries=3
        )
    except Exception as e:
        # If retry logic fails, still return a proper result
        logger.error(f"Pipeline processing failed after retries for {filename}: {str(e)}")
        return False, InternalWhisperResult(
            text=f"Pipeline failed after retries: {str(e)}",
            diarization=False,
            processing_metadata=ProcessingMetadata(
                filename=filename,
                processing_time_seconds=0,
                transcription_method="failed_with_retries",
                chunk_method="none"
            )
        )

async def run_pipeline(filename: str) -> Tuple[bool, InternalWhisperResult]:
    """
    Main audio processing pipeline that orchestrates all steps:
    
    1. Download Audio File from Azure Blob Storage and verify stereo format. If not stereo, proceed without diarization logic.
    2. Remove silence from audio where both channels are silent.
    3. Do the diarization according to the energy of the channels and inertia.
    4. Upsample the audio to 16kHz (if not already 16kHz) and convert to mono. Then convert to .flac.
    5. Do the chunking of the audio if needed (larger than 24MB)
    6. Send to whisper concurrently all the chunks and receive the transcription with segment-level timestamps
    7. Combine the transcription results into a single transcription and use the diarization result to apply to the transcription.
    8. Post process the transcription to remove the repetitions of the same word or phrases and return the final combined transcription.
    9. Cleanup temporary files
    
    Args:
        filename: Name of the audio file to process (blob name in Azure Storage)
        
    Returns:
        Tuple[bool, InternalWhisperResult]: (success, result)
    """
    pass