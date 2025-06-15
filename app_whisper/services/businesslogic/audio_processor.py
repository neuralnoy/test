"""
Main audio processing pipeline for Azure OpenAI Whisper with speaker diarization.
Orchestrates the complete pipeline from audio download to final transcribed output.
"""
import time
from typing import Tuple
from app_whisper.models.schemas import InternalWhisperResult
from app_whisper.services.businesslogic.audio_downloader import AudioFileDownloader
from app_whisper.services.businesslogic.audio_preprocessor import AudioPreprocessor
from app_whisper.services.businesslogic.speaker_diarizer import SpeakerDiarizer
from app_whisper.services.businesslogic.audio_chunker import AudioChunker
from app_whisper.services.businesslogic.whisper_transcriber import WhisperTranscriber
from app_whisper.services.businesslogic.transcription_postprocessor import TranscriptionPostProcessor
from common_new.logger import get_logger

logger = get_logger("whisper")

async def process_audio(filename: str) -> Tuple[bool, InternalWhisperResult]:
    """
    Main audio processing pipeline that orchestrates all steps:
    1. Download audio file from blob storage
    2. Preprocess audio (resample, trim silence)
    3. Perform speaker diarization
    4. Chunk audio for Whisper processing
    5. Transcribe with Azure OpenAI Whisper
    6. Post-process and align speakers with transcript
    
    Args:
        filename: Name of the audio file to process (blob name in Azure Storage)
        
    Returns:
        Tuple[bool, InternalWhisperResult]: (success, result)
    """
    downloader = None
    preprocessor = None
    diarizer = None
    chunker = None
    transcriber = None
    postprocessor = None
    start_time = time.time()
    
    try:
        logger.info(f"Starting audio processing pipeline for: {filename}")
        
        # Step 1: Download audio file from blob storage
        logger.info("=== STEP 1: DOWNLOADING AUDIO FILE ===")
        downloader = AudioFileDownloader()
        local_audio_path = await downloader.download_audio_file(filename)
        
        if not local_audio_path:
            logger.error(f"Failed to download audio file: {filename}")
            return False, InternalWhisperResult(
                transcription="Error: Failed to download audio file",
                diarization=False
            )
        
        # Get original audio file information
        original_audio_info = downloader.get_audio_info(local_audio_path)
        logger.info(f"Original audio info: {original_audio_info}")
        logger.info(f"Step 1 completed: Downloaded {filename} to {local_audio_path}")
        
        # Step 2: Audio preprocessing
        logger.info("=== STEP 2: AUDIO PREPROCESSING ===")
        preprocessor = AudioPreprocessor(target_sample_rate=16000)
        preprocessed_audio_path = preprocessor.preprocess_audio(local_audio_path)
        
        if not preprocessed_audio_path:
            logger.error(f"Failed to preprocess audio file: {filename}")
            return False, InternalWhisperResult(
                transcription="Error: Failed to preprocess audio file",
                diarization=False
            )
        
        # Get preprocessed audio information
        preprocessed_audio_info = preprocessor.get_audio_info(preprocessed_audio_path)
        logger.info(f"Preprocessed audio info: {preprocessed_audio_info}")
        logger.info(f"Step 2 completed: Preprocessed audio saved to {preprocessed_audio_path}")
        
        # Step 3: Speaker diarization
        logger.info("=== STEP 3: SPEAKER DIARIZATION ===")
        diarizer = SpeakerDiarizer(
            model_source="speechbrain/spkrec-ecapa-voxceleb",
            min_segment_duration=1.0,
            similarity_threshold=0.75
        )
        
        speaker_segments = diarizer.diarize_audio(preprocessed_audio_path)
        diarization_summary = diarizer.get_diarization_summary(speaker_segments)
        
        logger.info(f"Diarization summary: {diarization_summary}")
        logger.info(f"Step 3 completed: Identified {diarization_summary['num_speakers']} speakers in {len(speaker_segments)} segments")
        
        # Log speaker segments for debugging
        for i, segment in enumerate(speaker_segments[:5]):  # Show first 5 segments
            logger.info(f"  Segment {i+1}: {segment}")
        if len(speaker_segments) > 5:
            logger.info(f"  ... and {len(speaker_segments) - 5} more segments")
        
        # Step 4: Audio chunking
        logger.info("=== STEP 4: AUDIO CHUNKING ===")
        chunker = AudioChunker(
            max_file_size_mb=24.0,
            target_chunk_duration=30.0,
            max_chunk_duration=60.0,
            overlap_duration=3.0,
            min_chunk_duration=5.0
        )
        
        audio_chunks = chunker.chunk_audio(preprocessed_audio_path, speaker_segments)
        
        if not audio_chunks:
            logger.error(f"Failed to create audio chunks for: {filename}")
            return False, InternalWhisperResult(
                transcription="Error: Failed to create audio chunks",
                diarization=False
            )
        
        logger.info(f"Step 4 completed: Created {len(audio_chunks)} audio chunks")
        
        # Log chunk information
        total_chunk_size = sum(chunk.file_size for chunk in audio_chunks)
        for i, chunk in enumerate(audio_chunks[:3]):  # Show first 3 chunks
            logger.info(f"  Chunk {i+1}: {chunk.chunk_id} ({chunk.duration:.2f}s, "
                       f"{chunk.file_size/1024/1024:.2f}MB, speakers: {chunk.speaker_segments})")
        if len(audio_chunks) > 3:
            logger.info(f"  ... and {len(audio_chunks) - 3} more chunks")
        
        logger.info(f"Total chunks size: {total_chunk_size/1024/1024:.2f}MB")
        
        # Step 5: Whisper transcription
        logger.info("=== STEP 5: WHISPER TRANSCRIPTION ===")
        transcriber = WhisperTranscriber(app_id="app_whisper")
        
        # Determine transcription approach based on chunking
        if len(audio_chunks) == 1 and audio_chunks[0].is_whole_file:
            # Single file transcription
            logger.info("Transcribing whole file (under 24MB)")
            final_result = await transcriber.transcribe_whole_file(
                audio_chunks[0].file_path,
                language=None,  # Auto-detect language
                temperature=0.0
            )
            
            # Add speaker alignment if we have speaker segments
            if speaker_segments:
                postprocessor = TranscriptionPostProcessor(similarity_threshold=0.7)
                # Create dummy chunk transcription for speaker alignment
                from app_whisper.models.schemas import ChunkTranscription
                dummy_transcription = [ChunkTranscription(
                    chunk_id="whole_file",
                    start_time=0.0,
                    end_time=preprocessed_audio_info.get('duration', 0.0),
                    text=final_result.text,
                    confidence=final_result.confidence,
                    file_path=audio_chunks[0].file_path
                )]
                aligned_text = postprocessor._align_with_speakers(
                    final_result.text, dummy_transcription, speaker_segments
                )
                final_result.text = aligned_text
                final_result.processing_metadata["has_speaker_alignment"] = True
            
            logger.info(f"Step 5 completed: Transcribed whole file ({len(final_result.text)} characters)")
        else:
            # Chunked transcription
            logger.info(f"Transcribing {len(audio_chunks)} chunks concurrently")
            chunk_transcriptions = await transcriber.transcribe_chunks(
                audio_chunks,
                language=None,  # Auto-detect language
                temperature=0.0,
                max_concurrent=5
            )
            
            logger.info(f"Step 5 completed: Transcribed {len(chunk_transcriptions)} chunks")
            
            # Step 6: Post-processing and deduplication
            logger.info("=== STEP 6: POST-PROCESSING ===")
            postprocessor = TranscriptionPostProcessor(similarity_threshold=0.7)
            
            final_result = await postprocessor.process_chunk_transcriptions(
                chunk_transcriptions,
                speaker_segments=speaker_segments
            )
            
            logger.info(f"Step 6 completed: Post-processed transcription ({len(final_result.text)} characters)")
        
        processing_time = time.time() - start_time
        logger.info(f"Complete audio processing pipeline completed in {processing_time:.2f} seconds")
        
        # Add processing metadata
        final_result.processing_metadata.update({
            "filename": filename,
            "processing_time_seconds": processing_time,
            "original_audio_info": original_audio_info,
            "preprocessed_audio_info": preprocessed_audio_info,
            "diarization_summary": diarization_summary,
            "total_chunks": len(audio_chunks),
            "chunk_method": "whole_file" if len(audio_chunks) == 1 and audio_chunks[0].is_whole_file else "chunked"
        })
        
        return True, final_result
        
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Error in audio processing pipeline for {filename}: {str(e)} (Processing time: {processing_time:.2f}s)")
        return False, InternalWhisperResult(
            transcription=f"Error: {str(e)}",
            diarization=False
        )
    
    finally:
        # Clean up downloaded, preprocessed, and chunk files
        if downloader:
            downloader.cleanup_temp_files()
            logger.info("Cleaned up downloaded files")
        if preprocessor:
            preprocessor.cleanup_temp_files()
            logger.info("Cleaned up preprocessed files")
        if chunker:
            chunker.cleanup_temp_files()
            logger.info("Cleaned up chunk files")
        if transcriber and chunker and chunker.chunks:
            transcriber.cleanup_chunk_files(chunker.chunks)
            logger.info("Cleaned up transcription chunk files")