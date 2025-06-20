"""
Audio Preprocessor for channel-based speaker diarization.
Handles stereo channel splitting, resampling, and FLAC format conversion.
"""
import os
import tempfile
import numpy as np
from typing import Tuple, List, Dict, Any
from app_whisper.models.schemas import ChannelInfo
from common_new.logger import get_logger

logger = get_logger("businesslogic")

class AudioPreprocessor:
    """Preprocesses stereo audio for channel-based speaker diarization."""
    
    pass