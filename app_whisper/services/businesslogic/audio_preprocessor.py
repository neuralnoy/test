"""
Audio preprocessor for Step 2 of the whisper pipeline.
Handles audio optimization, resampling, mono conversion, and silence trimming.
"""
import os
import tempfile
from typing import Optional, Tuple
from pydub import AudioSegment
from pydub.silence import split_on_silence
from common_new.logger import get_logger

logger = get_logger("whisper")

class AudioPreprocessor:
    """
    Handles audio preprocessing for optimal Whisper transcription.
    
    This class implements Step 2 of the whisper pipeline:
    - Audio optimization (.wav input → optimized .wav output)
    - Resampling to 16kHz (optimal for Whisper)
    - Mono conversion (reduces file size)
    - Silence trimming (removes dead air)
    """
    
    def __init__(self, target_sample_rate: int = 16000):
        """
        Initialize the preprocessor.
        
        Args:
            target_sample_rate: Target sample rate for audio (default: 16kHz for Whisper)
        """
        self.target_sample_rate = target_sample_rate
        self.temp_dir = tempfile.mkdtemp(prefix="whisper_preprocessed_")
        logger.info(f"Created temporary directory for preprocessed audio: {self.temp_dir}")
    
    def preprocess_audio(self, input_path: str) -> Optional[str]:
        """
        Preprocess audio file for optimal Whisper transcription.
        
        Args:
            input_path: Path to the input audio file
            
        Returns:
            str: Path to the preprocessed audio file, or None if preprocessing failed
        """
        try:
            logger.info(f"Starting audio preprocessing for: {input_path}")
            
            # Step 1: Load audio file
            logger.info("Loading audio file...")
            audio = AudioSegment.from_file(input_path)
            
            original_info = {
                "duration": len(audio) / 1000.0,
                "sample_rate": audio.frame_rate,
                "channels": audio.channels,
                "format": os.path.splitext(input_path)[1].lower()
            }
            logger.info(f"Original audio: {original_info}")
            
            # Step 2: Convert to mono if stereo
            if audio.channels > 1:
                logger.info("Converting stereo to mono...")
                audio = audio.set_channels(1)
            
            # Step 3: Resample to target sample rate (16kHz for Whisper)
            if audio.frame_rate != self.target_sample_rate:
                logger.info(f"Resampling from {audio.frame_rate}Hz to {self.target_sample_rate}Hz...")
                audio = audio.set_frame_rate(self.target_sample_rate)
            
            # Step 4: Trim silence from beginning and end
            logger.info("Trimming silence...")
            audio = self._trim_silence(audio)
            
            # Step 5: Save preprocessed audio as WAV
            output_filename = f"preprocessed_{os.path.basename(input_path)}.wav"
            output_path = os.path.join(self.temp_dir, output_filename)
            
            logger.info(f"Saving preprocessed audio to: {output_path}")
            audio.export(output_path, format="wav")
            
            # Log final info
            final_info = {
                "duration": len(audio) / 1000.0,
                "sample_rate": audio.frame_rate,
                "channels": audio.channels,
                "file_size": os.path.getsize(output_path)
            }
            logger.info(f"Preprocessed audio: {final_info}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error preprocessing audio {input_path}: {str(e)}")
            return None
    
    def _trim_silence(self, audio: AudioSegment, silence_thresh: int = -40, min_silence_len: int = 500) -> AudioSegment:
        """
        Trim silence from the beginning and end of audio.
        
        Args:
            audio: AudioSegment to trim
            silence_thresh: Silence threshold in dBFS (default: -40dB)
            min_silence_len: Minimum silence length in ms to consider (default: 500ms)
            
        Returns:
            AudioSegment: Trimmed audio
        """
        try:
            # Split on silence to find non-silent chunks
            chunks = split_on_silence(
                audio,
                min_silence_len=min_silence_len,
                silence_thresh=silence_thresh,
                keep_silence=100  # Keep 100ms of silence at edges
            )
            
            if not chunks:
                logger.warning("No non-silent chunks found, returning original audio")
                return audio
            
            # Concatenate all non-silent chunks
            trimmed_audio = AudioSegment.empty()
            for chunk in chunks:
                trimmed_audio += chunk
            
            original_duration = len(audio) / 1000.0
            trimmed_duration = len(trimmed_audio) / 1000.0
            logger.info(f"Trimmed silence: {original_duration:.2f}s → {trimmed_duration:.2f}s")
            
            return trimmed_audio
            
        except Exception as e:
            logger.warning(f"Error trimming silence: {str(e)}, returning original audio")
            return audio
    
    def get_audio_info(self, audio_path: str) -> dict:
        """
        Get information about preprocessed audio file.
        
        Args:
            audio_path: Path to the audio file
            
        Returns:
            dict: Audio information
        """
        try:
            audio = AudioSegment.from_file(audio_path)
            return {
                "file_path": audio_path,
                "file_size": os.path.getsize(audio_path),
                "duration": len(audio) / 1000.0,
                "sample_rate": audio.frame_rate,
                "channels": audio.channels,
                "format": ".wav"
            }
        except Exception as e:
            logger.error(f"Error getting audio info: {str(e)}")
            return {
                "file_path": audio_path,
                "file_size": os.path.getsize(audio_path) if os.path.exists(audio_path) else 0,
                "duration": None,
                "sample_rate": None,
                "channels": None,
                "format": ".wav"
            }
    
    def cleanup_temp_files(self):
        """Clean up temporary preprocessed files."""
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up preprocessed audio directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up preprocessed files: {str(e)}") 