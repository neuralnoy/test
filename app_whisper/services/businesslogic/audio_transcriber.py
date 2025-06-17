"""
Whisper Transcriber for parallel channel-based transcription.
Handles concurrent transcription with rate limiting to avoid API blocks.
"""
import asyncio
import time
from typing import Tuple, List, Dict, Any
from app_whisper.models.schemas import AudioChunk, WhisperTranscriptionResult
from common_new.azure_openai_service import AzureOpenAIServiceWhisper
from common_new.logger import get_logger

logger = get_logger("audio_transcriber")

class WhisperTranscriber:
    """Handles parallel Whisper transcription using the service's built-in concurrency management."""
    
    def __init__(self):
        """
        Initialize the transcriber using the service's built-in concurrency management.
        """
        self.whisper_service = AzureOpenAIServiceWhisper(app_id="whisper_app")
        
        logger.info(f"Initialized WhisperTranscriber using service's built-in concurrent transcription")
    
    async def transcribe_channel_chunks(self, audio_chunks: List[AudioChunk]) -> Tuple[bool, Dict[str, Any], str]:
        """
        Transcribe all audio chunks using the service's built-in concurrent transcription.
        
        Args:
            audio_chunks: List of AudioChunk objects to transcribe
            
        Returns:
            Tuple[bool, Dict[str, Any], str]: (success, results_dict, error_message)
        """
        try:
            logger.info(f"Starting transcription of {len(audio_chunks)} audio chunks using transcribe_audio_chunks")
            
            if not audio_chunks:
                return False, {}, "No audio chunks provided for transcription"
            
            # Group chunks by speaker for organized processing
            speaker_chunks = self._group_chunks_by_speaker(audio_chunks)
            
            # Extract file paths for the transcribe_audio_chunks method
            file_paths = [chunk.file_path for chunk in audio_chunks]
            
            # Use the service's built-in concurrent transcription method
            logger.info(f"Calling transcribe_audio_chunks with {len(file_paths)} files")
            raw_results = await self.whisper_service.transcribe_audio_chunks(
                audio_file_paths=file_paths,
                response_format="verbose_json",
                timestamp_granularities=["segment", "word"],
                temperature=0.0
            )
            
            # Process and enhance results with chunk metadata
            enhanced_results = self._enhance_results_with_chunk_metadata(audio_chunks, raw_results)
            
            # Process results and check for errors
            success, processed_results, error_msg = self._process_transcription_results(
                audio_chunks, enhanced_results, speaker_chunks
            )
            
            if success:
                logger.info(f"Successfully transcribed all {len(audio_chunks)} chunks")
                return True, processed_results, ""
            else:
                logger.error(f"Transcription failed: {error_msg}")
                return False, {}, error_msg
                
        except Exception as e:
            error_msg = f"Error in parallel transcription: {str(e)}"
            logger.error(error_msg)
            return False, {}, error_msg
    
    def _enhance_results_with_chunk_metadata(self, audio_chunks: List[AudioChunk], raw_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enhance raw transcription results with chunk metadata.
        
        Args:
            audio_chunks: Original audio chunks (in same order as raw_results)
            raw_results: Raw results from transcribe_audio_chunks
            
        Returns:
            List of enhanced results with chunk metadata
        """
        enhanced_results = []
        
        for i, (chunk, raw_result) in enumerate(zip(audio_chunks, raw_results)):
            try:
                # Check if this result contains an error
                if 'error' in raw_result:
                    logger.warning(f"Chunk {chunk.chunk_id} had transcription error: {raw_result.get('error')}")
                    enhanced_result = {
                        'chunk_id': chunk.chunk_id,
                        'speaker_id': chunk.channel_info.speaker_id,
                        'start_time_offset': chunk.start_time,
                        'end_time_offset': chunk.end_time,
                        'success': False,
                        'error': raw_result.get('error', 'Unknown error'),
                        'text': raw_result.get('text', ""),
                        'segments': []
                    }
                else:
                    # Successful transcription - enhance with chunk metadata
                    enhanced_result = raw_result.copy()
                    enhanced_result.update({
                        'chunk_id': chunk.chunk_id,
                        'speaker_id': chunk.channel_info.speaker_id,
                        'start_time_offset': chunk.start_time,
                        'end_time_offset': chunk.end_time,
                        'success': True
                    })
                    
                    logger.info(f"Successfully enhanced chunk {chunk.chunk_id}: {len(enhanced_result.get('text', ''))} characters")
                
                enhanced_results.append(enhanced_result)
                
            except Exception as e:
                error_msg = f"Error enhancing results for chunk {chunk.chunk_id}: {str(e)}"
                logger.error(error_msg)
                
                # Create fallback result
                fallback_result = {
                    'chunk_id': chunk.chunk_id,
                    'speaker_id': chunk.channel_info.speaker_id,
                    'start_time_offset': chunk.start_time,
                    'end_time_offset': chunk.end_time,
                    'success': False,
                    'error': error_msg,
                    'text': "",
                    'segments': []
                }
                enhanced_results.append(fallback_result)
        
        logger.info(f"Enhanced {len(enhanced_results)} transcription results with chunk metadata")
        return enhanced_results
    
    def _group_chunks_by_speaker(self, audio_chunks: List[AudioChunk]) -> Dict[str, List[AudioChunk]]:
        """
        Group audio chunks by speaker ID.
        
        Args:
            audio_chunks: List of AudioChunk objects
            
        Returns:
            Dict mapping speaker_id to list of chunks
        """
        speaker_chunks = {}
        for chunk in audio_chunks:
            speaker_id = chunk.channel_info.speaker_id
            if speaker_id not in speaker_chunks:
                speaker_chunks[speaker_id] = []
            speaker_chunks[speaker_id].append(chunk)
        
        # Sort chunks within each speaker by start time
        for speaker_id in speaker_chunks:
            speaker_chunks[speaker_id].sort(key=lambda x: x.start_time)
        
        logger.info(f"Grouped chunks: {[(k, len(v)) for k, v in speaker_chunks.items()]}")
        return speaker_chunks
    
    def _process_transcription_results(self, 
                                     audio_chunks: List[AudioChunk], 
                                     results: List[Dict[str, Any]],
                                     speaker_chunks: Dict[str, List[AudioChunk]]) -> Tuple[bool, Dict[str, Any], str]:
        """
        Process and validate transcription results.
        
        Args:
            audio_chunks: Original audio chunks
            results: Enhanced results with chunk metadata
            speaker_chunks: Chunks grouped by speaker
            
        Returns:
            Tuple[bool, Dict[str, Any], str]: (success, processed_results, error_message)
        """
        try:
            # Check for failed transcriptions
            failed_chunks = []
            successful_results = []
            
            for result in results:
                if not result.get('success', False):
                    failed_chunks.append(f"Chunk {result.get('chunk_id', 'unknown')}: {result.get('error', 'Unknown error')}")
                
                # Add all results to successful_results for processing (including failed ones for completeness)
                successful_results.append(result)
            
            # Log any failures but continue processing
            if failed_chunks:
                logger.warning(f"Some chunks failed transcription: {failed_chunks}")
            
            # Organize results by speaker
            speaker_results = {}
            for result in successful_results:
                speaker_id = result['speaker_id']
                if speaker_id not in speaker_results:
                    speaker_results[speaker_id] = []
                speaker_results[speaker_id].append(result)
            
            # Sort results within each speaker by start time
            for speaker_id in speaker_results:
                speaker_results[speaker_id].sort(key=lambda x: x['start_time_offset'])
            
            # Create consolidated transcription results
            processed_results = {}
            for speaker_id, results_list in speaker_results.items():
                speaker_transcription = self._create_speaker_transcription_result(
                    speaker_id, results_list
                )
                processed_results[speaker_id] = speaker_transcription
            
            # Calculate overall statistics
            total_successful = sum(1 for r in successful_results if r.get('success', False))
            total_chunks = len(audio_chunks)
            
            success_rate = total_successful / total_chunks if total_chunks > 0 else 0
            
            processed_results['_metadata'] = {
                'total_chunks': total_chunks,
                'successful_chunks': total_successful,
                'failed_chunks': len(failed_chunks),
                'success_rate': success_rate,
                'speakers': list(speaker_results.keys())
            }
            
            # Consider successful if at least 80% of chunks succeeded
            overall_success = success_rate >= 0.8
            
            if overall_success:
                return True, processed_results, ""
            else:
                error_msg = f"Too many transcription failures: {len(failed_chunks)}/{total_chunks} chunks failed"
                return False, processed_results, error_msg
                
        except Exception as e:
            error_msg = f"Error processing transcription results: {str(e)}"
            logger.error(error_msg)
            return False, {}, error_msg
    
    def _create_speaker_transcription_result(self, 
                                           speaker_id: str, 
                                           results_list: List[Dict[str, Any]]) -> WhisperTranscriptionResult:
        """
        Create a consolidated WhisperTranscriptionResult for a speaker.
        
        Args:
            speaker_id: Speaker identifier
            results_list: List of transcription results for this speaker
            
        Returns:
            WhisperTranscriptionResult object
        """
        # Combine all text from successful chunks
        all_text_parts = []
        all_segments = []
        total_confidence = 0.0
        confidence_count = 0
        
        for result in results_list:
            if result.get('success', False) and result.get('text'):
                all_text_parts.append(result['text'].strip())
                
                # Adjust segment timestamps with chunk offsets
                if 'segments' in result:
                    offset = result['start_time_offset']
                    for segment in result['segments']:
                        adjusted_segment = segment.copy()
                        if 'start' in adjusted_segment:
                            adjusted_segment['start'] += offset
                        if 'end' in adjusted_segment:
                            adjusted_segment['end'] += offset
                        adjusted_segment['speaker_id'] = speaker_id
                        all_segments.append(adjusted_segment)
                
                # Track confidence if available
                if 'confidence' in result:
                    total_confidence += result['confidence']
                    confidence_count += 1
        
        # Combine text with proper spacing
        combined_text = " ".join(all_text_parts)
        
        # Calculate average confidence
        avg_confidence = total_confidence / confidence_count if confidence_count > 0 else 0.0
        
        # Detect language from first successful result
        detected_language = None
        for result in results_list:
            if result.get('success', False) and 'language' in result:
                detected_language = result['language']
                break
        
        transcription_result = WhisperTranscriptionResult(
            text=combined_text,
            segments=all_segments,
            language=detected_language,
            confidence=avg_confidence
        )
        
        logger.info(f"Created transcription result for {speaker_id}: {len(combined_text)} characters, {len(all_segments)} segments")
        
        return transcription_result
    
    def cleanup(self):
        """Clean up resources (placeholder for future use)."""
        logger.info("WhisperTranscriber cleanup completed")
    
    def __del__(self):
        """Cleanup on object destruction."""
        self.cleanup()
