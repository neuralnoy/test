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
    
    1. Download Audio File from Azure Blob Storage
    2. Verify stereo format (optional)
    3. Preprocess Audio (split channels, resample, trim silence, save as WAV)
    4. Channel-Specific Audio Chunking (if needed)
    5. Parallel Whisper Transcription for both channels
    6. Speaker Segment Creation & Alignment
    7. Post-Processing & Final Assembly
    8. Cleanup temporary files
    
    Args:
        filename: Name of the audio file to process (blob name in Azure Storage)
        
    Returns:
        Tuple[bool, InternalWhisperResult]: (success, result)
    """
    process = psutil.Process(os.getpid())
    start_mem = process.memory_info().rss / (1024 * 1024)
    logger.info(f"Pipeline start memory: {start_mem:.2f} MB")
    
    start_time = time.time()
    downloader = None
    preprocessor = None
    chunker = None
    transcriber = None
    postprocessor = None
    
    try:
        logger.info(f"Starting audio processing pipeline for: {filename}")
        
        # Step 1: Download Audio File
        logger.info("=" * 60)
        logger.info("STEP 1: Downloading audio file from blob storage")
        logger.info("=" * 60)
        downloader = AudioFileDownloader()
        
        success, local_file_path, error_msg = await downloader.download_audio_file(filename)
        if not success:
            logger.error(f"Failed to download audio file: {error_msg}")
            return False, InternalWhisperResult(
                text=f"Failed to download audio file: {error_msg}",
                diarization=False,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=time.time() - start_time,
                    transcription_method="failed",
                    chunk_method="none"
                )
            )
        
        # Step 1b: Verify stereo format (optional)
        logger.info("=" * 60)
        logger.info("STEP 1b: Verifying audio format")
        logger.info("=" * 60)
        is_stereo, original_audio_info = downloader.verify_stereo_format(local_file_path)
        if not is_stereo:
            logger.warning(f"Audio file is not stereo format, but continuing with processing")
        
        # Step 1c: Check audio duration (skip files shorter than 5 seconds)
        logger.info("=" * 60)
        logger.info("STEP 1c: Checking audio duration")
        logger.info("=" * 60)
        audio_duration = original_audio_info.get('duration', 0.0)
        min_duration = 5.0  # Minimum 5 seconds
        
        if audio_duration < min_duration:
            error_msg = f"Audio file too short for processing: {audio_duration:.2f}s (minimum: {min_duration}s)"
            logger.warning(error_msg)
            return False, InternalWhisperResult(
                text=f"Audio file rejected: {error_msg}",
                diarization=False,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=time.time() - start_time,
                    transcription_method="rejected_duration",
                    chunk_method="none",
                    original_audio_info=original_audio_info
                )
            )
        
        logger.info(f"Audio duration check passed: {audio_duration:.2f}s")
        
        # Step 2: Preprocess Audio
        logger.info("=" * 60)
        logger.info("STEP 2: Preprocessing audio (split channels, resample, trim, convert)")
        logger.info("=" * 60)
        preprocessor = AudioPreprocessor()
        
        success, channel_info_list, error_msg = await preprocessor.preprocess_stereo_audio(
            local_file_path,
            original_audio_info
        )
        if not success:
            logger.error(f"Failed to preprocess audio: {error_msg}")
            return False, InternalWhisperResult(
                text=f"Failed to preprocess audio: {error_msg}",
                diarization=False,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=time.time() - start_time,
                    transcription_method="failed_preprocessing",
                    chunk_method="none",
                    original_audio_info=original_audio_info
                )
            )

        logger.info("Audio preprocessing successful. Channel info:")
        for info in channel_info_list:
            logger.info(f"  - Channel: {info.channel_id} ({info.speaker_id}), Path: {info.file_path}, Size: {info.file_size_mb:.2f}MB")

        # Step 3: Channel-Specific Audio Chunking (if needed)
        logger.info("=" * 60)
        logger.info("STEP 3: Creating audio chunks for each channel")
        logger.info("=" * 60)
        chunker = AudioChunker()
        
        try:
            all_audio_chunks = chunker.chunk_audio(channel_info_list)
            
            logger.info("Audio chunking successful. Generated chunks:")
            for speaker_id, chunks in all_audio_chunks.items():
                logger.info(f"  - Speaker: {speaker_id}, Chunks: {len(chunks)}")
                for i, chunk in enumerate(chunks):
                    logger.info(f"    - Chunk {i+1}: {chunk.file_path} ({chunk.start_time:.2f}s - {chunk.end_time:.2f}s)")

            # Step 4: Parallel Whisper Transcription for both channels
            logger.info("=" * 60)
            logger.info("STEP 4: Transcribing audio chunks in parallel")
            logger.info("=" * 60)
            transcriber = WhisperTranscriber()
            
            transcribed_chunks = await transcriber.transcribe_chunks(all_audio_chunks)
            
            # Check for any failed chunks
            failed_chunks = [c for c in transcribed_chunks if c.error]
            if failed_chunks:
                logger.warning(f"{len(failed_chunks)} out of {len(transcribed_chunks)} chunks failed to transcribe.")
            
            logger.info("Transcription step completed.")

            # Step 5: Speaker Segment Creation & Alignment
            logger.info("=" * 60)
            logger.info("STEP 5: Creating and aligning speaker segments")
            logger.info("=" * 60)
            diarizer = SpeakerDiarizer()
            final_speaker_segments = diarizer.diarize_and_filter(transcribed_chunks)

            # Step 6: Post-Processing & Final Assembly
            logger.info("=" * 60)
            logger.info("STEP 6: Post-processing and assembling final transcript")
            logger.info("=" * 60)
            postprocessor = TranscriptionPostProcessor()
            final_text = postprocessor.assemble_transcript(final_speaker_segments)

            # Create the final result object
            processing_time = time.time() - start_time
            result = InternalWhisperResult(
                text=final_text,
                diarization=True,
                speaker_segments=final_speaker_segments,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=processing_time,
                    transcription_method="chunked_diarized",
                    chunk_method="size_based",
                    total_chunks=len(transcribed_chunks),
                    original_audio_info=original_audio_info
                )
            )
            
            logger.info(f"Total pipeline processing time for {filename}: {processing_time:.2f} seconds.")
            logger.info("Pipeline completed successfully.")
            return True, result

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Pipeline failed for {filename} after {processing_time:.2f} seconds: {e}")
            return False, InternalWhisperResult(
                text=f"Failed during chunking/transcription: {e}",
                diarization=False,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=processing_time,
                    transcription_method="failed_chunking_or_transcribing",
                    chunk_method="size_based",
                    original_audio_info=original_audio_info
                )
            )
        
    finally:
        # Step 7: Cleanup temporary files
        logger.info("=" * 60)
        logger.info("STEP 7: Cleaning up temporary files")
        logger.info("=" * 60)
        
        cleanup_errors = []
        
        try:
            if downloader:
                logger.debug("Cleaning up downloader resources")
                downloader.cleanup()
        except Exception as cleanup_error:
            cleanup_errors.append(f"Downloader cleanup: {cleanup_error}")
            logger.error(f"Error during downloader cleanup: {cleanup_error}")
            
        try:
            if preprocessor:
                logger.debug("Cleaning up preprocessor resources")
                preprocessor.cleanup()
        except Exception as cleanup_error:
            cleanup_errors.append(f"Preprocessor cleanup: {cleanup_error}")
            logger.error(f"Error during preprocessor cleanup: {cleanup_error}")
            
        try:
            if chunker:
                logger.debug("Cleaning up chunker resources")
                chunker.cleanup()
        except Exception as cleanup_error:
            cleanup_errors.append(f"Chunker cleanup: {cleanup_error}")
            logger.error(f"Error during chunker cleanup: {cleanup_error}")
            
        # Log summary of cleanup
        if cleanup_errors:
            logger.warning(f"Cleanup completed with {len(cleanup_errors)} errors: {'; '.join(cleanup_errors)}")
        else:
            logger.info("Cleanup completed successfully")
            
        # Force garbage collection for long-running operations
        import gc
        gc.collect()
        logger.debug("Forced garbage collection after cleanup")
        
        end_mem = process.memory_info().rss / (1024 * 1024)
        logger.info(f"Pipeline end memory: {end_mem:.2f} MB. Usage delta: {end_mem - start_mem:.2f} MB")