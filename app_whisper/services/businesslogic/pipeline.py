"""
Main audio processing pipeline for Azure OpenAI Whisper with channel-based speaker diarization.
Orchestrates the complete pipeline from audio download to final transcribed output.
"""
import time
from typing import Tuple
from app_whisper.models.schemas import InternalWhisperResult, ProcessingMetadata
from app_whisper.services.businesslogic.audio_downloader import AudioFileDownloader
from app_whisper.services.businesslogic.audio_converter import AudioConverter
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
    
    1.  Download Audio File: The original audio file is downloaded from Azure Blob Storage.
    2.  Convert and Resample: The downloaded audio is converted to MP3 format and resampled to 32,000 Hz 
        to standardize the input for subsequent processing. This step improves consistency and reduces file size.
    3.  Verify Stereo Format: The converted MP3 file is checked to confirm it has two (stereo) channels. 
        If the audio is mono, it is duplicated to create a stereo effect, ensuring compatibility with the
        channel-based diarization process.
    4.  Preprocess Audio: The stereo MP3 audio is split into two separate single-channel (mono) MP3 files, 
        one for each speaker. This is a crucial step for channel-based speaker diarization.
    5.  Audio Chunking: Each channel's MP3 file is analyzed, and if it exceeds the size limit for the
        transcription service, it is split into smaller, manageable MP3 chunks.
    6.  Parallel Transcription: All audio chunks from both channels are transcribed in parallel using the 
        Azure OpenAI Whisper service. This step includes rate limiting to prevent API errors.
    7.  Speaker Segment Creation: The transcription results from each channel are processed to create
        speaker-labeled text segments with accurate timestamps. Overlapping speech is detected and resolved.
    8.  Post-Processing and Assembly: The individual speaker segments are merged, sorted, and formatted into a 
        final, human-readable transcript with speaker labels.
    9.  Cleanup: All temporary files created during the process (downloads, MP3s, chunks) are deleted.
    
    Args:
        filename: Name of the audio file to process (blob name in Azure Storage)
        
    Returns:
        Tuple[bool, InternalWhisperResult]: (success, result)
    """
    start_time = time.time()
    downloader = None
    preprocessor = None
    chunker = None
    transcriber = None
    postprocessor = None
    converter = None
    
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
        
        # Step 1.5: Convert to MP3
        logger.info("=" * 60)
        logger.info("STEP 1.5: Converting audio to MP3 and resampling")
        logger.info("=" * 60)
        converter = AudioConverter()
        convert_success, converted_file_path, convert_error = converter.convert_to_mp3(
            local_file_path,
            downloader.temp_dir,
            target_sample_rate=32000
        )

        if not convert_success:
            logger.error(f"Audio conversion to MP3 failed: {convert_error}")
            # This is not a fatal error, so we can proceed with the original file
            logger.warning("Proceeding with the original audio file.")
            converted_file_path = local_file_path
        
        # Step 1b: Verify stereo format (optional)
        logger.info("=" * 60)
        logger.info("STEP 1b: Verifying audio format")
        logger.info("=" * 60)
        is_stereo, original_audio_info = downloader.verify_stereo_format(converted_file_path)
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
        logger.info("STEP 2: Preprocessing audio (splitting channels)")
        logger.info("=" * 60)
        preprocessor = AudioPreprocessor()
        
        preprocess_success, channel_info_list, preprocess_error = await preprocessor.preprocess_stereo_audio(
            converted_file_path, 
            original_audio_info
        )
        
        if not preprocess_success:
            logger.error(f"Audio preprocessing failed: {preprocess_error}")
            return False, InternalWhisperResult(
                text=f"Audio preprocessing failed: {preprocess_error}",
                diarization=False,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=time.time() - start_time,
                    transcription_method="failed",
                    chunk_method="none",
                    original_audio_info=original_audio_info
                )
            )
        
        # Step 3: Channel-Specific Audio Chunking
        logger.info("=" * 60)
        logger.info("STEP 3: Performing channel-specific audio chunking")
        logger.info("=" * 60)
        chunker = AudioChunker()
        
        chunking_success, audio_chunks, chunking_error = await chunker.create_channel_chunks(channel_info_list)
        
        if not chunking_success:
            logger.error(f"Audio chunking failed: {chunking_error}")
            return False, InternalWhisperResult(
                text=f"Audio chunking failed: {chunking_error}",
                diarization=False,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=time.time() - start_time,
                    transcription_method="failed",
                    chunk_method="failed",
                    original_audio_info=original_audio_info
                )
            )
        
        # Step 4: Parallel Whisper Transcription
        logger.info("=" * 60)
        logger.info("STEP 4: Performing parallel Whisper transcription")
        logger.info("=" * 60)
        transcriber = WhisperTranscriber()
        
        # Add timeout handling for long transcription operations
        import asyncio
        try:
            # Set a reasonable timeout for transcription (20 minutes)
            transcription_task = asyncio.create_task(
                transcriber.transcribe_channel_chunks(audio_chunks)
            )
            transcription_success, whisper_results, transcription_error = await asyncio.wait_for(
                transcription_task, 
                timeout=1200  # 20 minutes timeout
            )
        except asyncio.TimeoutError:
            logger.error("Whisper transcription timed out after 20 minutes")
            transcription_task.cancel()  # Cancel the task to free resources
            return False, InternalWhisperResult(
                text="Whisper transcription timed out after 20 minutes",
                diarization=False,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=time.time() - start_time,
                    transcription_method="timeout",
                    chunk_method="chunked" if len(audio_chunks) > 2 else "direct",
                    total_chunks=len(audio_chunks),
                    original_audio_info=original_audio_info
                )
            )
        
        if not transcription_success:
            logger.error(f"Whisper transcription failed: {transcription_error}")
            return False, InternalWhisperResult(
                text=f"Whisper transcription failed: {transcription_error}",
                diarization=False,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=time.time() - start_time,
                    transcription_method="failed",
                    chunk_method="chunked" if len(audio_chunks) > 2 else "direct",
                    total_chunks=len(audio_chunks),
                    original_audio_info=original_audio_info
                )
            )
        
        # Step 5: Speaker Segment Creation & Alignment
        logger.info("=" * 60)
        logger.info("STEP 5: Creating speaker segments and alignment")
        logger.info("=" * 60)
        diarizer = SpeakerDiarizer()
        
        diarization_success, speaker_segments, diarization_error = await diarizer.create_speaker_segments(
            whisper_results, 
            channel_info_list,
            audio_chunks
        )
        
        if not diarization_success:
            logger.error(f"Speaker diarization failed: {diarization_error}")
            return False, InternalWhisperResult(
                text=f"Speaker diarization failed: {diarization_error}",
                diarization=False,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=time.time() - start_time,
                    transcription_method="whisper",
                    chunk_method="chunked" if len(audio_chunks) > 2 else "direct",
                    total_chunks=len(audio_chunks),
                    original_audio_info=original_audio_info
                )
            )
        
        # Step 6: Post-Processing & Final Assembly
        logger.info("=" * 60)
        logger.info("STEP 6: Post-processing and final assembly")
        logger.info("=" * 60)
        postprocessor = TranscriptionPostProcessor()
        
        final_success, final_result, postprocess_error = await postprocessor.create_final_transcript(
            speaker_segments,
            whisper_results,
            channel_info_list
        )
        
        if not final_success:
            logger.error(f"Post-processing failed: {postprocess_error}")
            return False, InternalWhisperResult(
                text=f"Post-processing failed: {postprocess_error}",
                diarization=False,
                processing_metadata=ProcessingMetadata(
                    filename=filename,
                    processing_time_seconds=time.time() - start_time,
                    transcription_method="whisper",
                    chunk_method="chunked" if len(audio_chunks) > 2 else "direct",
                    total_chunks=len(audio_chunks),
                    original_audio_info=original_audio_info
                )
            )
        
        # Create comprehensive processing metadata
        processing_time = time.time() - start_time
        
        preprocessed_info = {}
        if channel_info_list:
            preprocessed_info = {
                'channels': len(channel_info_list),
                'duration': max(ch.duration for ch in channel_info_list),
                'sample_rate': original_audio_info.get('samplerate'),
                'format': 'MP3'
            }
        
        diarization_summary = {
            'num_speakers': len(set(seg.speaker_id for seg in speaker_segments)),
            'num_segments': len(speaker_segments),
            'total_duration': sum(seg.end_time - seg.start_time for seg in speaker_segments)
        }
        
        metadata = ProcessingMetadata(
            filename=filename,
            processing_time_seconds=processing_time,
            transcription_method="whisper",
            chunk_method="chunked" if len(audio_chunks) > 2 else "direct",
            total_chunks=len(audio_chunks),
            has_speaker_alignment=True,
            diarization_summary=diarization_summary,
            original_audio_info=original_audio_info,
            preprocessed_audio_info=preprocessed_info
        )
        
        result = InternalWhisperResult(
            text=final_result['text'],
            consolidated_text=final_result.get('consolidated_text'),
            diarization=len(speaker_segments) > 0,
            confidence=final_result.get('confidence', 0.0),
            speaker_segments=speaker_segments,
            processing_metadata=metadata
        )
        
        logger.info(f"Pipeline completed successfully in {processing_time:.2f} seconds")
        logger.info(f"Final stats: {len(speaker_segments)} segments, {diarization_summary['num_speakers']} speakers")
        
        return True, result
        
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Pipeline crashed: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        return False, InternalWhisperResult(
            text=f"Pipeline error: {str(e)}",
            diarization=False,
            processing_metadata=ProcessingMetadata(
                filename=filename,
                processing_time_seconds=processing_time,
                transcription_method="failed",
                chunk_method="none"
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
            
        try:
            if transcriber:
                logger.debug("Cleaning up transcriber resources")
                transcriber.cleanup()
        except Exception as cleanup_error:
            cleanup_errors.append(f"Transcriber cleanup: {cleanup_error}")
            logger.error(f"Error during transcriber cleanup: {cleanup_error}")
            
        try:
            if postprocessor:
                logger.debug("Cleaning up postprocessor resources")
                postprocessor.cleanup()
        except Exception as cleanup_error:
            cleanup_errors.append(f"Postprocessor cleanup: {cleanup_error}")
            logger.error(f"Error during postprocessor cleanup: {cleanup_error}")
            
        # Log summary of cleanup
        if cleanup_errors:
            logger.warning(f"Cleanup completed with {len(cleanup_errors)} errors: {'; '.join(cleanup_errors)}")
        else:
            logger.info("Cleanup completed successfully")
            
        # Force garbage collection for long-running operations
        import gc
        gc.collect()
        logger.debug("Forced garbage collection after cleanup")