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
    """Handles parallel Whisper transcription with rate limiting."""
    
    def __init__(self, max_concurrent_requests: int = 3, request_delay: float = 0.1):
        """
        Initialize the transcriber.
        
        Args:
            max_concurrent_requests: Maximum number of concurrent API requests
            request_delay: Delay in seconds between API requests
        """
        self.max_concurrent_requests = max_concurrent_requests
        self.request_delay = request_delay
        self.whisper_service = AzureOpenAIServiceWhisper(app_id="whisper_app")
        
        # Semaphore to limit concurrent requests
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        
        logger.info(f"Initialized WhisperTranscriber with max_concurrent: {max_concurrent_requests}, delay: {request_delay}s")
    
    async def transcribe_channel_chunks(self, audio_chunks: List[AudioChunk]) -> Tuple[bool, Dict[str, Any], str]:
        """
        Transcribe all audio chunks with proper rate limiting and concurrency.
        
        Args:
            audio_chunks: List of AudioChunk objects to transcribe
            
        Returns:
            Tuple[bool, Dict[str, Any], str]: (success, results_dict, error_message)
        """
        try:
            logger.info(f"Starting transcription of {len(audio_chunks)} audio chunks")
            
            if not audio_chunks:
                return False, {}, "No audio chunks provided for transcription"
            
            # Group chunks by speaker for organized processing
            speaker_chunks = self._group_chunks_by_speaker(audio_chunks)
            
            # Create transcription tasks with rate limiting
            transcription_tasks = []
            for chunk in audio_chunks:
                task = self._transcribe_single_chunk_with_rate_limit(chunk)
                transcription_tasks.append(task)
            
            # Execute all transcriptions with controlled concurrency
            logger.info(f"Executing {len(transcription_tasks)} transcription tasks with max {self.max_concurrent_requests} concurrent")
            results = await asyncio.gather(*transcription_tasks, return_exceptions=True)
            
            # Process results and check for errors
            success, processed_results, error_msg = self._process_transcription_results(
                audio_chunks, results, speaker_chunks
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
    
    async def _transcribe_single_chunk_with_rate_limit(self, chunk: AudioChunk) -> Dict[str, Any]:
        """
        Transcribe a single chunk with rate limiting.
        
        Args:
            chunk: AudioChunk to transcribe
            
        Returns:
            Dict containing transcription result or error information
        """
        async with self.semaphore:
            try:
                # Add delay to prevent API rate limiting
                if self.request_delay > 0:
                    await asyncio.sleep(self.request_delay)
                
                logger.info(f"Transcribing chunk: {chunk.chunk_id} ({chunk.start_time:.2f}s-{chunk.end_time:.2f}s)")
                
                # Call Whisper API with verbose JSON and timestamp granularities
                result = await self.whisper_service.transcribe_audio(
                    audio_file_path=chunk.file_path,
                    response_format="verbose_json",
                    timestamp_granularities=["segment", "word"],
                    temperature=0.0
                )
                
                # Add chunk metadata to result
                result['chunk_id'] = chunk.chunk_id
                result['speaker_id'] = chunk.channel_info.speaker_id
                result['start_time_offset'] = chunk.start_time
                result['end_time_offset'] = chunk.end_time
                result['success'] = True
                
                logger.info(f"Successfully transcribed chunk {chunk.chunk_id}: {len(result.get('text', ''))} characters")
                return result
                
            except Exception as e:
                error_msg = f"Error transcribing chunk {chunk.chunk_id}: {str(e)}"
                logger.error(error_msg)
                
                return {
                    'chunk_id': chunk.chunk_id,
                    'speaker_id': chunk.channel_info.speaker_id,
                    'start_time_offset': chunk.start_time,
                    'end_time_offset': chunk.end_time,
                    'success': False,
                    'error': error_msg,
                    'text': "",
                    'segments': []
                }
    
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
                                     results: List[Any],
                                     speaker_chunks: Dict[str, List[AudioChunk]]) -> Tuple[bool, Dict[str, Any], str]:
        """
        Process and validate transcription results.
        
        Args:
            audio_chunks: Original audio chunks
            results: Results from asyncio.gather
            speaker_chunks: Chunks grouped by speaker
            
        Returns:
            Tuple[bool, Dict[str, Any], str]: (success, processed_results, error_message)
        """
        try:
            # Check for exceptions in results
            failed_chunks = []
            successful_results = []
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    failed_chunks.append(f"Chunk {i}: {str(result)}")
                    # Create fallback result
                    chunk = audio_chunks[i]
                    fallback_result = {
                        'chunk_id': chunk.chunk_id,
                        'speaker_id': chunk.channel_info.speaker_id,
                        'start_time_offset': chunk.start_time,
                        'end_time_offset': chunk.end_time,
                        'success': False,
                        'error': str(result),
                        'text': "",
                        'segments': []
                    }
                    successful_results.append(fallback_result)
                elif not result.get('success', False):
                    failed_chunks.append(f"Chunk {result.get('chunk_id', i)}: {result.get('error', 'Unknown error')}")
                    successful_results.append(result)
                else:
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
