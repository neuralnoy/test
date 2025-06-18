from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any, Literal
from enum import Enum

class InputWhisper(BaseModel):
    id: str
    language: Optional[str] = None
    filename: str
    client_manager: Optional[str] = None

class SpeakerSegment(BaseModel):
    """Individual speaker segment with timestamp and speaker ID."""
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds") 
    speaker_id: str = Field(..., description="Speaker identifier (Speaker_1 or Speaker_2)")
    text: str = Field(default="", description="Transcribed text for this segment")
    confidence: Optional[float] = Field(default=None, description="Confidence score")

class ChannelInfo(BaseModel):
    """Information about audio channel processing."""
    channel_id: str = Field(..., description="Channel identifier (left/right)")
    speaker_id: str = Field(..., description="Associated speaker ID")
    file_path: str = Field(..., description="Path to processed channel file")
    duration: float = Field(..., description="Duration in seconds")
    file_size_mb: float = Field(..., description="File size in megabytes")

class AudioChunk(BaseModel):
    """Audio chunk for processing large files."""
    chunk_id: str = Field(..., description="Unique chunk identifier")
    channel_info: ChannelInfo = Field(..., description="Channel information")
    start_time: float = Field(..., description="Start time in original audio")
    end_time: float = Field(..., description="End time in original audio")
    file_path: str = Field(..., description="Path to chunk file")
    file_size_mb: float = Field(..., description="Chunk file size in MB")

class WhisperTranscriptionResult(BaseModel):
    """Result from Whisper transcription."""
    text: str = Field(..., description="Full transcribed text")
    segments: List[Dict[str, Any]] = Field(default_factory=list, description="Whisper segments with timestamps")
    language: Optional[str] = Field(default=None, description="Detected language")
    confidence: float = Field(default=0.0, description="Overall confidence score")

class ProcessingMetadata(BaseModel):
    """Metadata about the processing pipeline."""
    filename: str
    processing_time_seconds: float
    transcription_method: str = Field(description="Method used (chunked/direct)")
    chunk_method: str = Field(description="Chunking approach used")
    total_chunks: int = Field(default=0, description="Total number of chunks processed")
    has_speaker_alignment: bool = Field(default=False, description="Whether speaker alignment was performed")
    
    # Diarization summary
    diarization_summary: Dict[str, Any] = Field(default_factory=dict, description="Summary of diarization results")
    
    # Audio information
    original_audio_info: Dict[str, Any] = Field(default_factory=dict, description="Original audio file info")
    preprocessed_audio_info: Dict[str, Any] = Field(default_factory=dict, description="Preprocessed audio info")

class InternalWhisperResult(BaseModel):
    """Internal result from whisper processing."""
    text: str
    diarization: bool
    confidence: float = Field(default=0.0, description="Overall confidence score")
    speaker_segments: List[SpeakerSegment] = Field(default_factory=list, description="Speaker-labeled segments")
    processing_metadata: ProcessingMetadata = Field(..., description="Processing metadata and statistics")

class OutputWhisper(BaseModel):
    id: str
    filename: str
    transcription: str
    diarization: bool
    message: str