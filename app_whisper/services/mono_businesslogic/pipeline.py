"""
Main audio processing pipeline for Azure OpenAI Whisper with channel-based speaker diarization.
Orchestrates the complete pipeline from audio download to final transcribed output.
"""

from common_new.logger import get_logger
from common_new.retry_helpers import with_token_limit_retry
from common_new.token_client import TokenClient
from typing import Tuple
from app_whisper.models.schemas import InternalWhisperResult, ProcessingMetadata
from app_whisper.services.businesslogic.audio_downloader import AudioFileDownloader
import time

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
    
    1. Download Audio File from Azure Blob Storage and verify stereo format (audio_downloader)
    2. Remove silence from audio where both channels are silent (audio_preprocessor)
    3. Perform diarization according to the energy of the channels and inertia (audio_diarizer)
    4. Preprocess the audio to 16kHz (if not already 16kHz) and convert to mono. Then convert to .flac. (audio_preprocessor)
    5. Chunk the audio into smaller chunks (audio_chunker)
    6. Parallel Whisper Transcription for mono audio chunks(audio_transcriber)
    7. Apply diarization to the transcription (audio_postprocessor)
    8. Post-Processing & Final Assembly (audio_postprocessor)
    9. Cleanup temporary files (audio_postprocessor)
    
    Args:
        filename: Name of the audio file to process (blob name in Azure Storage)
        
    Returns:
        Tuple[bool, InternalWhisperResult]: (success, result)
    """
    start_time = time.time()
    downloader = None
    try:
        # 1. Download Audio File and verify stereo
        logger.info(f"Starting pipeline for file: {filename}")
        downloader = AudioFileDownloader()
        success, local_file_path, error_msg = await downloader.download_audio_file(filename)

        if not success:
            logger.error(f"Failed to download audio file {filename}: {error_msg}")
            return False, InternalWhisperResult(
                text=f"Failed to download audio file: {error_msg}",
                diarization=False,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=time.time() - start_time,
                    transcription_method="failed_download",
                    chunk_method="none"
                )
            )
        
        logger.info(f"Successfully downloaded {filename} to {local_file_path}")

        is_stereo, audio_info = downloader.verify_stereo_format(local_file_path)
        if not is_stereo:
            # This pipeline is designed for stereo files, but we'll log a warning and continue.
            # Subsequent steps might fail if they strictly expect two channels.
            logger.warning(f"Audio file {filename} is not in stereo format. Processing will continue.")

        # Placeholder for subsequent steps
        pass

    finally:
        if downloader:
            downloader.cleanup()
            logger.info("Temporary download directory cleaned up.")
    
    # This is a temporary return value until the full pipeline is implemented
    return True, InternalWhisperResult(
        text="Pipeline step 1 (download) complete. More steps to follow.",
        diarization=False,
        processing_metadata=ProcessingMetadata(
            filename=filename,
            processing_time_seconds=time.time() - start_time,
            transcription_method="mono",
            chunk_method="TBD",
            original_audio_info=audio_info
        )
    )