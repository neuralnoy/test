from pydantic import BaseModel
from typing import List, Optional

class InputWhisper(BaseModel):
    id: str
    language: Optional[str] = None
    filename: str
    client_manager: Optional[str] = None

class OutputWhisper(BaseModel):
    id: str
    filename: str
    transcription: str
    diarization: bool
    message: str

class InternalWhisperResult(BaseModel):
    transcription: str
    diarization: bool
