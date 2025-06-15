from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Any

class InputWhisper(BaseModel):
    id: str
    language: Optional[str] = None
    filename: str
    client_manager: Optional[str] = None

class SpeakerSegment(BaseModel):
    """Represents a speaker diarization segment."""
    speaker_id: str
    start_time: float
    end_time: float
    confidence: float = 0.0

class AudioChunk(BaseModel):
    """Represents an audio chunk with overlap information for transcription."""
    # Uncomment the line below to disable validation if needed
    # model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=False)
    
    chunk_id: str
    file_path: str
    start_time: float
    end_time: float
    duration: float
    file_size: int
    overlap_duration: float = 0.0  # Overlap duration with next chunk (seconds)
    speaker_segments: List[SpeakerSegment] = []  # Speaker segments in this chunk
    is_whole_file: bool = False  # True if this chunk is the entire file

class ChunkTranscription(BaseModel):
    """Represents transcription result for a single chunk."""
    chunk_id: str
    start_time: float
    end_time: float
    text: str
    confidence: float = 0.0
    whisper_result: Optional[Dict[str, Any]] = None  # Full Whisper API response
    error: Optional[str] = None
    file_path: Optional[str] = None

class InternalWhisperResult(BaseModel):
    """Internal result from whisper processing."""
    text: str
    confidence: float = 0.0
    processing_metadata: Dict[str, Any] = {}

class OutputWhisper(BaseModel):
    id: str
    filename: str
    transcription: str
    diarization: bool
    message: str
