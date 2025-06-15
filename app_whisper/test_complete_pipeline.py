"""
Test script for the complete audio processing pipeline (Steps 1-6).
Tests the full pipeline from audio download to final transcription with speaker diarization.
"""
import asyncio
import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_whisper.services.businesslogic.audio_processor import process_audio
from common_new.logger import get_logger

logger = get_logger("test_complete_pipeline")


async def test_complete_pipeline():
    """Test the complete audio processing pipeline."""
    
    # Test filename - replace with an actual .wav file in your blob storage
    test_filename = "test_audio.wav"  # Replace with your test file
    
    logger.info("=" * 60)
    logger.info("TESTING COMPLETE AUDIO PROCESSING PIPELINE")
    logger.info("=" * 60)
    logger.info(f"Test file: {test_filename}")
    logger.info("")
    
    try:
        # Run the complete pipeline
        success, result = await process_audio(test_filename)
        
        if success:
            logger.info("✅ PIPELINE COMPLETED SUCCESSFULLY!")
            logger.info("")
            logger.info("=== FINAL TRANSCRIPTION RESULT ===")
            logger.info(f"Text length: {len(result.text)} characters")
            logger.info(f"Confidence: {result.confidence:.3f}")
            logger.info("")
            logger.info("Text preview (first 500 characters):")
            logger.info("-" * 50)
            logger.info(result.text[:500] + ("..." if len(result.text) > 500 else ""))
            logger.info("-" * 50)
            logger.info("")
            
            # Show processing metadata
            if hasattr(result, 'processing_metadata') and result.processing_metadata:
                logger.info("=== PROCESSING METADATA ===")
                metadata = result.processing_metadata
                
                logger.info(f"Filename: {metadata.get('filename', 'N/A')}")
                logger.info(f"Processing time: {metadata.get('processing_time_seconds', 0):.2f} seconds")
                logger.info(f"Transcription method: {metadata.get('transcription_method', 'N/A')}")
                logger.info(f"Chunk method: {metadata.get('chunk_method', 'N/A')}")
                logger.info(f"Total chunks: {metadata.get('total_chunks', 0)}")
                logger.info(f"Has speaker alignment: {metadata.get('has_speaker_alignment', False)}")
                
                # Diarization info
                diarization = metadata.get('diarization_summary', {})
                if diarization:
                    logger.info(f"Speakers detected: {diarization.get('num_speakers', 0)}")
                    logger.info(f"Total segments: {diarization.get('num_segments', 0)}")
                
                # Audio info
                original_info = metadata.get('original_audio_info', {})
                preprocessed_info = metadata.get('preprocessed_audio_info', {})
                if original_info and preprocessed_info:
                    logger.info(f"Duration: {original_info.get('duration', 'N/A')}s → {preprocessed_info.get('duration', 'N/A')}s")
                    logger.info(f"Sample rate: {original_info.get('sample_rate', 'N/A')}Hz → {preprocessed_info.get('sample_rate', 'N/A')}Hz")
                
                logger.info("")
            
            logger.info("🎉 All steps completed successfully!")
            
        else:
            logger.error("❌ PIPELINE FAILED!")
            logger.error(f"Error result: {result.text if hasattr(result, 'text') else str(result)}")
            
    except Exception as e:
        logger.error(f"❌ PIPELINE CRASHED: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())


async def test_pipeline_with_sample_files():
    """Test with multiple sample files if available."""
    
    # List of test files to try (replace with your actual test files)
    test_files = [
        "sample_conversation.wav",
        "meeting_recording.wav", 
        "interview.wav",
        "test_audio.wav"
    ]
    
    logger.info("Testing pipeline with multiple sample files...")
    
    for filename in test_files:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing with: {filename}")
        logger.info('='*60)
        
        try:
            success, result = await process_audio(filename)
            
            if success:
                logger.info(f"✅ {filename}: SUCCESS")
                logger.info(f"   Text length: {len(result.text)} characters")
                logger.info(f"   Confidence: {result.confidence:.3f}")
                
                if hasattr(result, 'processing_metadata'):
                    metadata = result.processing_metadata
                    logger.info(f"   Processing time: {metadata.get('processing_time_seconds', 0):.2f}s")
                    logger.info(f"   Method: {metadata.get('chunk_method', 'N/A')}")
                    logger.info(f"   Speakers: {metadata.get('diarization_summary', {}).get('num_speakers', 0)}")
            else:
                logger.warning(f"⚠️  {filename}: FAILED")
                logger.warning(f"   Error: {result.text if hasattr(result, 'text') else str(result)}")
                
        except Exception as e:
            logger.error(f"❌ {filename}: CRASHED - {str(e)}")


if __name__ == "__main__":
    print("🎵 Audio Processing Pipeline Test")
    print("=" * 50)
    
    # Choose test mode
    test_mode = input("Test mode? (1) Single file, (2) Multiple files, (3) Both: ").strip()
    
    if test_mode == "1":
        asyncio.run(test_complete_pipeline())
    elif test_mode == "2":
        asyncio.run(test_pipeline_with_sample_files())
    else:
        asyncio.run(test_complete_pipeline())
        print("\n" + "="*60 + "\n")
        asyncio.run(test_pipeline_with_sample_files())
    
    print("\n🏁 Testing completed!") 