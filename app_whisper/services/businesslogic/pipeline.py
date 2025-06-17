"""
Main audio processing pipeline for Azure OpenAI Whisper with channel-based speaker diarization.
Orchestrates the complete pipeline from audio download to final transcribed output.
"""
import time
from typing import Tuple
from app_whisper.models.schemas import InternalWhisperResult, ProcessingMetadata
from app_whisper.services.businesslogic.audio_downloader import AudioFileDownloader
from app_whisper.services.businesslogic.audio_preprocessor import AudioPreprocessor
from app_whisper.services.businesslogic.audio_diarizer import SpeakerDiarizer
from app_whisper.services.businesslogic.audio_chunker import AudioChunker
from app_whisper.services.businesslogic.audio_transcriber import WhisperTranscriber
from app_whisper.services.businesslogic.audio_postprocessor import TranscriptionPostProcessor
from common_new.logger import get_logger

logger = get_logger("businesslogic")

async def process_audio(filename: str) -> Tuple[bool, InternalWhisperResult]:
    """
    Main entry point for audio processing pipeline.
    This function is called by data_processor.py
    
    Args:
        filename: Name of the audio file to process (blob name in Azure Storage)
        
    Returns:
        Tuple[bool, InternalWhisperResult]: (success, result)
    """
    return await run_pipeline(filename)

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
        
        # Step 2: Preprocess Audio
        logger.info("=" * 60)
        logger.info("STEP 2: Preprocessing audio (split channels, resample, trim, convert)")
        logger.info("=" * 60)
        preprocessor = AudioPreprocessor()
        
        preprocess_success, channel_info_list, preprocess_error = await preprocessor.preprocess_stereo_audio(
            local_file_path, 
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
        
        transcription_success, whisper_results, transcription_error = await transcriber.transcribe_channel_chunks(audio_chunks)
        
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
                'sample_rate': 16000,  # We resample to 16kHz
                'format': 'WAV'
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
        try:
            if downloader:
                downloader.cleanup()
            if preprocessor:
                preprocessor.cleanup()
            if chunker:
                chunker.cleanup()
            if transcriber:
                transcriber.cleanup()
            if postprocessor:
                postprocessor.cleanup()
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup: {cleanup_error}")