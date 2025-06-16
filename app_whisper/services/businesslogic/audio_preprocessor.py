"""
Audio Preprocessor for channel-based speaker diarization.
Handles stereo channel splitting, resampling, silence trimming, and FLAC conversion.
"""
import os
import tempfile
import numpy as np
from typing import Tuple, List, Dict, Any
from app_whisper.models.schemas import ChannelInfo
from common_new.logger import get_logger

logger = get_logger("audio_preprocessor")

class AudioPreprocessor:
    """Preprocesses stereo audio for channel-based speaker diarization."""
    
    def __init__(self):
        """Initialize the preprocessor."""
        # Create temp directory for processed files
        self.temp_dir = tempfile.mkdtemp(prefix="whisper_preprocessed_")
        logger.info(f"Initialized AudioPreprocessor with temp directory: {self.temp_dir}")
    
    async def preprocess_stereo_audio(self, 
                                    audio_file_path: str, 
                                    original_audio_info: Dict[str, Any]) -> Tuple[bool, List[ChannelInfo], str]:
        """
        Preprocess stereo audio file by converting to FLAC first, then splitting channels and optimizing for Whisper.
        
        Args:
            audio_file_path: Path to the input stereo audio file
            original_audio_info: Information about the original audio file
            
        Returns:
            Tuple[bool, List[ChannelInfo], str]: (success, channel_info_list, error_message)
        """
        try:
            logger.info(f"Starting audio preprocessing for: {audio_file_path}")
            
            # Step 2a: Convert entire file to FLAC first
            logger.info("Step 2a: Converting entire file to FLAC format")
            flac_file_path = await self._convert_to_flac(audio_file_path, original_audio_info)
            if not flac_file_path:
                return False, [], "Failed to convert audio file to FLAC"
            
            # Step 2b: Load the FLAC file and split into channels
            logger.info("Step 2b: Loading FLAC file and splitting into channels")
            audio_data, sample_rate = self._load_audio_file(flac_file_path)
            if audio_data is None:
                return False, [], "Failed to load FLAC audio file"
            
            logger.info(f"Loaded FLAC audio: shape={audio_data.shape}, sr={sample_rate}Hz")
            
            # Split into left and right channels (Speaker 1 & Speaker 2)
            left_channel, right_channel = self._split_stereo_channels(audio_data)
            
            # Process each channel separately
            channel_info_list = []
            
            for channel_id, channel_data in [("left", left_channel), ("right", right_channel)]:
                speaker_id = "Speaker_1" if channel_id == "left" else "Speaker_2"
                
                logger.info(f"Step 2c: Processing {channel_id} channel ({speaker_id})")
                
                # Process each channel (resample, trim, save as FLAC)
                success, processed_file_path, duration, file_size_mb = await self._process_channel(
                    channel_data, 
                    sample_rate, 
                    channel_id,
                    speaker_id
                )
                
                if not success:
                    return False, [], f"Failed to process {channel_id} channel"
                
                # Create ChannelInfo object
                channel_info = ChannelInfo(
                    channel_id=channel_id,
                    speaker_id=speaker_id,
                    file_path=processed_file_path,
                    duration=duration,
                    file_size_mb=file_size_mb
                )
                
                channel_info_list.append(channel_info)
                
                logger.info(f"{channel_id} channel processed: {duration:.2f}s, {file_size_mb:.2f}MB")
            
            logger.info(f"Audio preprocessing completed for both channels")
            return True, channel_info_list, ""
            
        except Exception as e:
            error_msg = f"Error in audio preprocessing: {str(e)}"
            logger.error(error_msg)
            return False, [], error_msg
    
    async def _convert_to_flac(self, audio_file_path: str, original_audio_info: Dict[str, Any]) -> str:
        """
        Convert the entire audio file to FLAC format first.
        
        Args:
            audio_file_path: Path to the input audio file
            original_audio_info: Information about the original audio file
            
        Returns:
            str: Path to the converted FLAC file, or empty string on error
        """
        try:
            import soundfile as sf
            
            # Create output FLAC file path
            base_name = os.path.splitext(os.path.basename(audio_file_path))[0]
            flac_file_path = os.path.join(self.temp_dir, f"{base_name}_converted.flac")
            
            # Load original audio
            audio_data, sample_rate = sf.read(audio_file_path)
            
            # Ensure we have at least mono audio
            if audio_data.ndim == 1:
                # Convert mono to stereo by duplicating the channel
                audio_data = np.column_stack([audio_data, audio_data])
                logger.warning("Converted mono audio to stereo by duplicating channel")
            
            # Normalize audio to prevent clipping
            if np.max(np.abs(audio_data)) > 1.0:
                audio_data = audio_data / np.max(np.abs(audio_data))
                logger.info("Normalized audio to prevent clipping")
            
            # Save as FLAC with good compression
            sf.write(flac_file_path, audio_data, sample_rate, format='FLAC', subtype='PCM_16')
            
            # Calculate compression ratio
            original_size_mb = os.path.getsize(audio_file_path) / (1024 * 1024)
            flac_size_mb = os.path.getsize(flac_file_path) / (1024 * 1024)
            compression_ratio = flac_size_mb / original_size_mb if original_size_mb > 0 else 0
            
            logger.info(f"Converted to FLAC: {original_size_mb:.2f}MB -> {flac_size_mb:.2f}MB (compression: {compression_ratio:.2f})")
            
            return flac_file_path
            
        except Exception as e:
            logger.error(f"Error converting audio file to FLAC: {str(e)}")
            return ""
    
    def _load_audio_file(self, audio_file_path: str) -> Tuple[np.ndarray, int]:
        """
        Load audio file using soundfile.
        
        Args:
            audio_file_path: Path to audio file
            
        Returns:
            Tuple[np.ndarray, int]: (audio_data, sample_rate) or (None, 0) on error
        """
        try:
            import soundfile as sf
            
            # Load audio file
            audio_data, sample_rate = sf.read(audio_file_path)
            
            # Ensure we have at least mono audio
            if audio_data.ndim == 1:
                # Convert mono to stereo by duplicating the channel
                audio_data = np.column_stack([audio_data, audio_data])
                logger.warning("Converted mono audio to stereo by duplicating channel")
            
            return audio_data, sample_rate
            
        except Exception as e:
            logger.error(f"Error loading audio file {audio_file_path}: {str(e)}")
            return None, 0
    
    def _split_stereo_channels(self, audio_data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Split stereo audio into left and right channels.
        
        Args:
            audio_data: Stereo audio data array
            
        Returns:
            Tuple[np.ndarray, np.ndarray]: (left_channel, right_channel)
        """
        if audio_data.ndim == 2:
            left_channel = audio_data[:, 0]
            right_channel = audio_data[:, 1]
        else:
            # If somehow mono, duplicate it
            left_channel = audio_data
            right_channel = audio_data.copy()
        
        logger.info(f"Split channels: left={left_channel.shape}, right={right_channel.shape}")
        return left_channel, right_channel
    
    async def _process_channel(self, 
                             channel_data: np.ndarray, 
                             original_sample_rate: int,
                             channel_id: str,
                             speaker_id: str) -> Tuple[bool, str, float, float]:
        """
        Process individual audio channel: resample, trim silence, save as FLAC.
        
        Args:
            channel_data: Audio data for the channel
            original_sample_rate: Original sample rate
            channel_id: Channel identifier (left/right)
            speaker_id: Speaker identifier
            
        Returns:
            Tuple[bool, str, float, float]: (success, file_path, duration, file_size_mb)
        """
        try:
            # Resample to 16kHz (optimal for Whisper)
            target_sample_rate = 16000
            if original_sample_rate != target_sample_rate:
                resampled_data = self._resample_audio(channel_data, original_sample_rate, target_sample_rate)
                logger.info(f"Resampled {channel_id} from {original_sample_rate}Hz to {target_sample_rate}Hz")
            else:
                resampled_data = channel_data
                logger.info(f"No resampling needed for {channel_id} (already {target_sample_rate}Hz)")
            
            # Trim silence from beginning/end
            trimmed_data = self._trim_silence(resampled_data, target_sample_rate)
            original_duration = len(resampled_data) / target_sample_rate
            trimmed_duration = len(trimmed_data) / target_sample_rate
            
            logger.info(f"Trimmed silence from {channel_id}: {original_duration:.2f}s → {trimmed_duration:.2f}s")
            
            # Save processed channel as FLAC
            output_filename = f"{speaker_id}_{channel_id}_processed.flac"
            output_path = os.path.join(self.temp_dir, output_filename)
            
            success, file_size_mb = self._save_as_flac(trimmed_data, target_sample_rate, output_path)
            
            if not success:
                return False, "", 0.0, 0.0
            
            return True, output_path, trimmed_duration, file_size_mb
            
        except Exception as e:
            logger.error(f"Error processing {channel_id} channel: {str(e)}")
            return False, "", 0.0, 0.0
    
    def _resample_audio(self, audio_data: np.ndarray, original_sr: int, target_sr: int) -> np.ndarray:
        """
        Resample audio to target sample rate using librosa.
        
        Args:
            audio_data: Input audio data
            original_sr: Original sample rate
            target_sr: Target sample rate
            
        Returns:
            np.ndarray: Resampled audio data
        """
        try:
            import librosa
            
            # Use librosa for high-quality resampling
            resampled = librosa.resample(audio_data, orig_sr=original_sr, target_sr=target_sr)
            return resampled
            
        except Exception as e:
            logger.error(f"Error resampling audio: {str(e)}")
            # Fallback to simple resampling
            ratio = target_sr / original_sr
            new_length = int(len(audio_data) * ratio)
            return np.interp(np.linspace(0, len(audio_data), new_length), 
                           np.arange(len(audio_data)), audio_data)
    
    def _trim_silence(self, audio_data: np.ndarray, sample_rate: int, 
                     silence_threshold: float = 0.01, min_silence_duration: float = 0.5) -> np.ndarray:
        """
        Trim silence from beginning and end of audio.
        
        Args:
            audio_data: Input audio data
            sample_rate: Sample rate
            silence_threshold: Threshold for silence detection (amplitude)
            min_silence_duration: Minimum silence duration to trim (seconds)
            
        Returns:
            np.ndarray: Trimmed audio data
        """
        try:
            # Calculate absolute values for silence detection
            abs_audio = np.abs(audio_data)
            
            # Find silence regions
            silence_samples = int(min_silence_duration * sample_rate)
            
            # Find start of audio (first non-silent region)
            start_idx = 0
            for i in range(0, len(abs_audio) - silence_samples, silence_samples // 4):
                window = abs_audio[i:i + silence_samples]
                if np.mean(window) > silence_threshold:
                    start_idx = max(0, i - silence_samples // 2)
                    break
            
            # Find end of audio (last non-silent region)
            end_idx = len(abs_audio)
            for i in range(len(abs_audio) - silence_samples, 0, -(silence_samples // 4)):
                window = abs_audio[i:i + silence_samples]
                if np.mean(window) > silence_threshold:
                    end_idx = min(len(abs_audio), i + silence_samples + silence_samples // 2)
                    break
            
            # Ensure we don't trim too much
            if end_idx <= start_idx:
                logger.warning("Silence trimming would remove entire audio, keeping original")
                return audio_data
            
            trimmed = audio_data[start_idx:end_idx]
            
            # Ensure minimum duration (at least 1 second)
            min_samples = sample_rate  # 1 second
            if len(trimmed) < min_samples:
                logger.warning("Trimmed audio too short, keeping original")
                return audio_data
            
            return trimmed
            
        except Exception as e:
            logger.error(f"Error trimming silence: {str(e)}")
            return audio_data
    
    def _save_as_flac(self, audio_data: np.ndarray, sample_rate: int, output_path: str) -> Tuple[bool, float]:
        """
        Save audio data as FLAC file.
        
        Args:
            audio_data: Audio data to save
            sample_rate: Sample rate
            output_path: Output file path
            
        Returns:
            Tuple[bool, float]: (success, file_size_mb)
        """
        try:
            import soundfile as sf
            
            # Ensure audio data is in correct format
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)
            
            # Normalize audio to prevent clipping
            if np.max(np.abs(audio_data)) > 1.0:
                audio_data = audio_data / np.max(np.abs(audio_data))
            
            # Save as FLAC
            sf.write(output_path, audio_data, sample_rate, format='FLAC', subtype='PCM_16')
            
            # Calculate file size
            file_size_bytes = os.path.getsize(output_path)
            file_size_mb = file_size_bytes / (1024 * 1024)
            
            logger.info(f"Saved FLAC file: {output_path} ({file_size_mb:.2f} MB)")
            return True, file_size_mb
            
        except Exception as e:
            logger.error(f"Error saving FLAC file {output_path}: {str(e)}")
            return False, 0.0
    
    def cleanup(self):
        """Clean up temporary preprocessed files."""
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up preprocessor temp directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up preprocessor temp directory {self.temp_dir}: {str(e)}")
    
    def __del__(self):
        """Cleanup on object destruction."""
        self.cleanup()
