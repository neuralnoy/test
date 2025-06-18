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
    
    def __init__(self):
        """Initialize the preprocessor."""
        # Create temp directory for processed files
        self.temp_dir = tempfile.mkdtemp(prefix="whisper_preprocessed_")
        logger.info(f"Initialized AudioPreprocessor with temp directory: {self.temp_dir}")
    
    async def preprocess_stereo_audio(self, 
                                    audio_file_path: str, 
                                    original_audio_info: Dict[str, Any]) -> Tuple[bool, List[ChannelInfo], str]:
        """
        Preprocess stereo audio file by splitting channels and optimizing for Whisper.
        
        Args:
            audio_file_path: Path to the input stereo audio file
            original_audio_info: Information about the original audio file
            
        Returns:
            Tuple[bool, List[ChannelInfo], str]: (success, channel_info_list, error_message)
        """
        try:
            logger.info(f"Starting audio preprocessing for: {audio_file_path}")
            
            # Load the audio file and split into channels
            logger.info("Step 2a: Loading audio file and splitting into channels")
            audio_data, sample_rate = self._load_audio_file(audio_file_path)
            if audio_data is None:
                return False, [], "Failed to load audio file"
            
            logger.info(f"Loaded audio: shape={audio_data.shape}, sr={sample_rate}Hz")
            
            # Split into left and right channels (Speaker 1 & Speaker 2)
            left_channel, right_channel = self._split_stereo_channels(audio_data)
            
            # Process each channel separately
            channel_info_list = []
            
            for channel_id, channel_data in [("left", left_channel), ("right", right_channel)]:
                speaker_id = "*Speaker 1*" if channel_id == "left" else "*Speaker 2*"
                
                logger.info(f"Step 2b: Processing {channel_id} channel ({speaker_id})")
                
                # Process each channel (resample, trim, save as WAV)
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
        Process individual audio channel: resample and save as FLAC.
        
        Args:
            channel_data: Audio data for the channel
            original_sample_rate: Original sample rate
            channel_id: Channel identifier (left/right)
            speaker_id: Speaker identifier
            
        Returns:
            Tuple[bool, str, float, float]: (success, file_path, duration, file_size_mb)
        """
        try:
            # Target sample rate for Whisper (16kHz is optimal)
            target_sample_rate = 16000
            
            # Resample if needed
            if original_sample_rate != target_sample_rate:
                logger.info(f"Resampling {channel_id} channel: {original_sample_rate}Hz -> {target_sample_rate}Hz")
                resampled_audio = self._resample_audio(channel_data, original_sample_rate, target_sample_rate)
            else:
                resampled_audio = channel_data
            
            # Calculate duration
            duration = len(resampled_audio) / target_sample_rate
            logger.info(f"{channel_id} channel duration after processing: {duration:.2f}s")
            
            # Save as FLAC file
            output_filename = f"{speaker_id}_{channel_id}.flac"
            output_path = os.path.join(self.temp_dir, output_filename)
            
            success, file_size_mb = self._save_as_flac(resampled_audio, target_sample_rate, output_path)
            if not success:
                return False, "", 0.0, 0.0
            
            return True, output_path, duration, file_size_mb
            
        except Exception as e:
            logger.error(f"Error processing {channel_id} channel: {str(e)}")
            return False, "", 0.0, 0.0

    def _resample_audio(self, audio_data: np.ndarray, original_sr: int, target_sr: int) -> np.ndarray:
        """
        Resample audio data to target sample rate.
        
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
            logger.info(f"Resampled audio: {len(audio_data)} -> {len(resampled)} samples")
            return resampled
            
        except Exception as e:
            logger.error(f"Error resampling audio: {str(e)}")
            # Fallback: simple decimation/interpolation
            ratio = target_sr / original_sr
            new_length = int(len(audio_data) * ratio)
            return np.interp(np.linspace(0, len(audio_data), new_length), 
                           np.arange(len(audio_data)), audio_data)

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
            
            # Normalize audio to prevent clipping
            if np.max(np.abs(audio_data)) > 1.0:
                audio_data = audio_data / np.max(np.abs(audio_data))
                logger.info("Normalized audio to prevent clipping")
            
            # Save as FLAC with 16-bit PCM encoding
            sf.write(output_path, audio_data, sample_rate, format='FLAC', subtype='PCM_16')
            
            # Calculate file size
            file_size_bytes = os.path.getsize(output_path)
            file_size_mb = file_size_bytes / (1024 * 1024)
            
            logger.info(f"Saved FLAC file: {output_path} ({file_size_mb:.2f}MB)")
            return True, file_size_mb
            
        except Exception as e:
            logger.error(f"Error saving FLAC file {output_path}: {str(e)}")
            return False, 0.0

    def cleanup(self):
        """Clean up temporary files and directories."""
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temp directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up temp directory: {str(e)}")

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()