"""
Whisper Transcription Service for concurrent audio transcription.
Handles transcription of audio chunks with proper error handling and result processing.
"""
import asyncio
import os
import tempfile
from typing import List, Dict, Any, Optional
from pathlib import Path

from common_new.azure_openai_service import AzureOpenAIServiceWhisper
from common_new.logger import get_logger
from app_whisper.models.schemas import AudioChunk, ChunkTranscription, InternalWhisperResult

logger = get_logger("whisper_transcriber")


class WhisperTranscriber:
    """
    Service for transcribing audio chunks using Azure OpenAI Whisper.
    Handles concurrent transcription with proper error handling and result processing.
    """
    
    def __init__(self, app_id: str = "app_whisper"):
        """
        Initialize the Whisper transcription service.
        
        Args:
            app_id: Application ID for rate limiting and tracking
        """
        self.whisper_service = AzureOpenAIServiceWhisper(app_id=app_id)
        self.app_id = app_id
        logger.info(f"Initialized WhisperTranscriber with app_id: {app_id}")
    
    async def transcribe_chunks(
        self,
        chunks: List[AudioChunk],
        language: Optional[str] = None,
        temperature: float = 0.0,
        max_concurrent: int = 5
    ) -> List[ChunkTranscription]:
        """
        Transcribe multiple audio chunks concurrently.
        
        Args:
            chunks: List of audio chunks to transcribe
            language: Language code for transcription (e.g., 'en', 'es')
            temperature: Sampling temperature for transcription
            max_concurrent: Maximum number of concurrent transcriptions
            
        Returns:
            List of chunk transcriptions with results
        """
        if not chunks:
            logger.warning("No chunks provided for transcription")
            return []
        
        logger.info(f"Starting transcription of {len(chunks)} chunks with max_concurrent={max_concurrent}")
        
        # Create semaphore to limit concurrent transcriptions
        semaphore = asyncio.Semaphore(max_concurrent)
        
        # Create transcription tasks
        tasks = []
        for chunk in chunks:
            task = self._transcribe_chunk_with_semaphore(
                chunk, semaphore, language, temperature
            )
            tasks.append(task)
        
        try:
            # Execute all transcriptions concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results and create ChunkTranscription objects
            transcriptions = []
            successful_count = 0
            failed_count = 0
            
            for i, result in enumerate(results):
                chunk = chunks[i]
                
                if isinstance(result, Exception):
                    logger.error(f"Failed to transcribe chunk {chunk.chunk_id}: {str(result)}")
                    transcription = ChunkTranscription(
                        chunk_id=chunk.chunk_id,
                        start_time=chunk.start_time,
                        end_time=chunk.end_time,
                        text="",
                        confidence=0.0,
                        error=str(result),
                        file_path=chunk.file_path
                    )
                    failed_count += 1
                else:
                    transcription = result
                    successful_count += 1
                
                transcriptions.append(transcription)
            
            logger.info(f"Transcription completed: {successful_count} successful, {failed_count} failed")
            return transcriptions
            
        except Exception as e:
            logger.error(f"Error in concurrent chunk transcription: {str(e)}")
            raise
    
    async def _transcribe_chunk_with_semaphore(
        self,
        chunk: AudioChunk,
        semaphore: asyncio.Semaphore,
        language: Optional[str],
        temperature: float
    ) -> ChunkTranscription:
        """
        Transcribe a single chunk with semaphore-based concurrency control.
        
        Args:
            chunk: Audio chunk to transcribe
            semaphore: Semaphore for concurrency control
            language: Language code for transcription
            temperature: Sampling temperature
            
        Returns:
            ChunkTranscription with results
        """
        async with semaphore:
            return await self._transcribe_single_chunk(chunk, language, temperature)
    
    async def _transcribe_single_chunk(
        self,
        chunk: AudioChunk,
        language: Optional[str],
        temperature: float
    ) -> ChunkTranscription:
        """
        Transcribe a single audio chunk.
        
        Args:
            chunk: Audio chunk to transcribe
            language: Language code for transcription
            temperature: Sampling temperature
            
        Returns:
            ChunkTranscription with results
        """
        logger.debug(f"Transcribing chunk {chunk.chunk_id}: {chunk.file_path}")
        
        try:
            # Prepare transcription parameters
            transcription_params = {
                "response_format": "verbose_json",  # Get detailed results with timestamps
                "temperature": temperature
            }
            
            if language:
                transcription_params["language"] = language
            
            # Add speaker context as prompt if available
            if chunk.speaker_segments:
                speaker_info = f"Audio contains {len(chunk.speaker_segments)} speaker segments."
                transcription_params["prompt"] = speaker_info
            
            # Transcribe the chunk
            result = await self.whisper_service.transcribe_audio_with_retry(
                chunk.file_path,
                max_retries=3,
                retry_delay=2.0,
                **transcription_params
            )
            
            # Extract transcription text and confidence
            text = result.get("text", "").strip()
            
            # Calculate confidence from segments if available
            confidence = self._calculate_confidence(result)
            
            # Create transcription result
            transcription = ChunkTranscription(
                chunk_id=chunk.chunk_id,
                start_time=chunk.start_time,
                end_time=chunk.end_time,
                text=text,
                confidence=confidence,
                whisper_result=result,  # Store full Whisper result
                file_path=chunk.file_path
            )
            
            logger.debug(f"Successfully transcribed chunk {chunk.chunk_id}: {len(text)} characters")
            return transcription
            
        except Exception as e:
            logger.error(f"Error transcribing chunk {chunk.chunk_id}: {str(e)}")
            
            # Return error transcription
            return ChunkTranscription(
                chunk_id=chunk.chunk_id,
                start_time=chunk.start_time,
                end_time=chunk.end_time,
                text="",
                confidence=0.0,
                error=str(e),
                file_path=chunk.file_path
            )
    
    def _calculate_confidence(self, whisper_result: Dict[str, Any]) -> float:
        """
        Calculate average confidence from Whisper result segments.
        
        Args:
            whisper_result: Full Whisper transcription result
            
        Returns:
            Average confidence score (0.0 to 1.0)
        """
        try:
            segments = whisper_result.get("segments", [])
            if not segments:
                return 0.8  # Default confidence if no segments
            
            # Calculate average confidence from segments
            total_confidence = 0.0
            total_duration = 0.0
            
            for segment in segments:
                # Weight confidence by segment duration
                start = segment.get("start", 0.0)
                end = segment.get("end", 0.0)
                duration = max(end - start, 0.1)  # Minimum duration
                
                # Whisper doesn't always provide confidence, estimate from other factors
                confidence = segment.get("avg_logprob", -0.5)  # Default log prob
                
                # Convert log probability to confidence (rough approximation)
                if confidence < -1.0:
                    segment_confidence = 0.3
                elif confidence < -0.5:
                    segment_confidence = 0.6
                else:
                    segment_confidence = 0.9
                
                total_confidence += segment_confidence * duration
                total_duration += duration
            
            if total_duration > 0:
                return min(total_confidence / total_duration, 1.0)
            else:
                return 0.8
                
        except Exception as e:
            logger.warning(f"Error calculating confidence: {str(e)}")
            return 0.8  # Default confidence
    
    async def transcribe_whole_file(
        self,
        file_path: str,
        language: Optional[str] = None,
        temperature: float = 0.0
    ) -> InternalWhisperResult:
        """
        Transcribe a whole audio file (for files under 24MB).
        
        Args:
            file_path: Path to the audio file
            language: Language code for transcription
            temperature: Sampling temperature
            
        Returns:
            InternalWhisperResult with transcription
        """
        logger.info(f"Transcribing whole file: {file_path}")
        
        try:
            # Prepare transcription parameters
            transcription_params = {
                "response_format": "verbose_json",
                "temperature": temperature
            }
            
            if language:
                transcription_params["language"] = language
            
            # Transcribe the file
            result = await self.whisper_service.transcribe_audio_with_retry(
                file_path,
                max_retries=3,
                retry_delay=2.0,
                **transcription_params
            )
            
            # Extract text and calculate confidence
            text = result.get("text", "").strip()
            confidence = self._calculate_confidence(result)
            
            # Create result
            whisper_result = InternalWhisperResult(
                text=text,
                confidence=confidence,
                processing_metadata={
                    "transcription_method": "whole_file",
                    "file_path": file_path,
                    "language": language,
                    "temperature": temperature,
                    "whisper_result": result
                }
            )
            
            logger.info(f"Successfully transcribed whole file: {len(text)} characters")
            return whisper_result
            
        except Exception as e:
            logger.error(f"Error transcribing whole file {file_path}: {str(e)}")
            raise
    
    def cleanup_chunk_files(self, chunks: List[AudioChunk]) -> None:
        """
        Clean up temporary chunk files.
        
        Args:
            chunks: List of audio chunks with file paths to clean up
        """
        cleaned_count = 0
        
        for chunk in chunks:
            try:
                if os.path.exists(chunk.file_path):
                    os.remove(chunk.file_path)
                    cleaned_count += 1
                    logger.debug(f"Cleaned up chunk file: {chunk.file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up chunk file {chunk.file_path}: {str(e)}")
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} chunk files") 