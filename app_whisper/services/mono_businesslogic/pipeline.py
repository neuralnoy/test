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
from app_whisper.services.mono_businesslogic.audio_preprocessor import AudioPreprocessor
from app_whisper.services.mono_businesslogic.audio_diarizer import AudioDiarizer
from app_whisper.services.mono_businesslogic.audio_chunker import AudioChunker
from app_whisper.services.mono_businesslogic.audio_transcriber import WhisperTranscriber
from app_whisper.services.mono_businesslogic.audio_postprocessor import TranscriptionPostProcessor
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
    6. Parallel Whisper Transcription for mono audio chunks
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
    preprocessor = None
    chunker = None
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
            logger.error(f"Audio file {filename} is not in stereo format, which is required for this pipeline.")
            return False, InternalWhisperResult(
                text="Audio file is not stereo.",
                diarization=False,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=time.time() - start_time,
                    transcription_method="failed_preprocess",
                    chunk_method="none",
                    original_audio_info=audio_info
                )
            )

        # 2. Remove silence from audio where both channels are silent
        logger.info("Starting silence removal step.")
        preprocessor = AudioPreprocessor()
        success, silence_trimmed_path, error_msg = preprocessor.remove_silence_from_stereo(local_file_path)

        if not success:
            logger.error(f"Failed to remove silence from {filename}: {error_msg}")
            return False, InternalWhisperResult(
                text=f"Failed during silence removal: {error_msg}",
                diarization=False,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=time.time() - start_time,
                    transcription_method="failed_preprocess",
                    chunk_method="none",
                    original_audio_info=audio_info
                )
            )
        
        logger.info(f"Successfully removed silence. New audio at: {silence_trimmed_path}")

        # 3. Perform diarization according to the energy of the channels and inertia
        logger.info("Starting diarization step.")
        diarizer = AudioDiarizer()
        success, speaker_segments, error_msg = diarizer.diarize(silence_trimmed_path)

        if not success:
            logger.error(f"Failed to diarize {filename}: {error_msg}")
            return False, InternalWhisperResult(
                text=f"Failed during diarization: {error_msg}",
                diarization=False,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=time.time() - start_time,
                    transcription_method="failed_diarization",
                    chunk_method="none",
                    original_audio_info=audio_info
                )
            )
        
        logger.info(f"Successfully diarized audio. Found {len(speaker_segments)} segments.")

        # 4. Preprocess the audio to 16kHz mono FLAC
        logger.info("Starting mono conversion, resampling, and FLAC encoding.")
        success, mono_flac_path, error_msg, preprocessed_audio_info = preprocessor.process_to_mono_flac(silence_trimmed_path)

        if not success:
            logger.error(f"Failed to preprocess audio for {filename}: {error_msg}")
            return False, InternalWhisperResult(
                text=f"Failed during preprocessing (mono/flac): {error_msg}",
                diarization=True,
                speaker_segments=speaker_segments,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=time.time() - start_time,
                    transcription_method="failed_preprocess",
                    chunk_method="none",
                    original_audio_info=audio_info,
                    has_speaker_alignment=True
                )
            )

        logger.info(f"Successfully preprocessed audio to mono FLAC: {mono_flac_path}")

        # 5. Chunk the audio into smaller chunks
        logger.info("Starting audio chunking step.")
        chunker = AudioChunker()
        audio_chunks = chunker.chunk_audio(mono_flac_path, preprocessed_audio_info)

        if not audio_chunks:
            logger.error(f"Audio chunking failed for {filename}. No chunks were produced.")
            # This is a critical failure, but let's create a specific error message
            return False, InternalWhisperResult(
                text="Failed during audio chunking: no chunks created.",
                diarization=True,
                speaker_segments=speaker_segments,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=time.time() - start_time,
                    transcription_method="failed_chunking",
                    chunk_method="size_based",
                    original_audio_info=audio_info,
                    preprocessed_audio_info=preprocessed_audio_info,
                    has_speaker_alignment=True
                )
            )
            
        chunk_method = "size_based" if len(audio_chunks) > 1 else "direct"
        logger.info(f"Audio chunking complete. Created {len(audio_chunks)} chunk(s) using '{chunk_method}' method.")

        # 6. Parallel Whisper Transcription for mono audio chunks
        logger.info("Starting parallel Whisper transcription step.")
        transcriber = WhisperTranscriber()
        transcribed_chunks = await transcriber.transcribe_chunks(audio_chunks, language=None)

        failed_chunks = [tc for tc in transcribed_chunks if tc.error]
        if len(failed_chunks) == len(audio_chunks):
            logger.error(f"All {len(audio_chunks)} transcription chunks failed for {filename}.")
            first_error = failed_chunks[0].error if failed_chunks else "Unknown transcription failure."
            return False, InternalWhisperResult(
                text=f"Transcription failed for all chunks: {first_error}",
                diarization=True,
                speaker_segments=speaker_segments,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=time.time() - start_time,
                    transcription_method="failed_transcription",
                    chunk_method=chunk_method,
                    total_chunks=len(audio_chunks),
                    original_audio_info=audio_info,
                    preprocessed_audio_info=preprocessed_audio_info,
                    has_speaker_alignment=True
                )
            )

        if failed_chunks:
            logger.warning(f"{len(failed_chunks)} out of {len(audio_chunks)} chunks failed to transcribe, but proceeding with successful ones.")

        logger.info("Successfully transcribed audio chunks.")

        # 7. Apply diarization to the transcription and assemble final transcript
        logger.info("Starting post-processing to assemble final transcript.")
        post_processor = TranscriptionPostProcessor()
        # Filter out chunks that failed to transcribe before passing to post-processor
        successful_chunks = [tc for tc in transcribed_chunks if tc.transcription_result]
        final_transcript = post_processor.assemble_transcript(successful_chunks, speaker_segments)

        if not final_transcript:
            logger.warning(f"Post-processing for {filename} resulted in an empty transcript.")

        processing_time = time.time() - start_time
        logger.info(f"Pipeline completed for {filename} in {processing_time:.2f} seconds.")

    finally:
        if downloader:
            downloader.cleanup()
            logger.info("Temporary download directory cleaned up.")
        if preprocessor:
            preprocessor.cleanup()
            logger.info("Temporary preprocessor directory cleaned up.")
        if chunker:
            chunker.cleanup()
            logger.info("Temporary chunker directory cleaned up.")
    
    return True, InternalWhisperResult(
        text=final_transcript,
        diarization=True,
        speaker_segments=speaker_segments, # Return original diarization for metadata
        processing_metadata=ProcessingMetadata(
            filename=filename,
            processing_time_seconds=processing_time,
            transcription_method="mono",
            chunk_method=chunk_method,
            total_chunks=len(audio_chunks),
            original_audio_info=audio_info,
            preprocessed_audio_info=preprocessed_audio_info,
            has_speaker_alignment=True
        )
    )