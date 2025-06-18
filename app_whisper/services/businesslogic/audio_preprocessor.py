"""
Audio Preprocessor for channel-based speaker diarization.
Handles stereo channel splitting and saving audio as MP3 files using pydub.
"""
import os
import tempfile
from pydub import AudioSegment
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
        Preprocess stereo audio file by splitting channels and saving as MP3.
        
        Args:
            audio_file_path: Path to the input stereo audio file.
            original_audio_info: Information about the original audio file.
            
        Returns:
            Tuple[bool, List[ChannelInfo], str]: (success, channel_info_list, error_message)
        """
        try:
            logger.info(f"Starting audio preprocessing for: {audio_file_path}")
            
            # Load the audio file using pydub
            logger.info("Step 2a: Loading audio file and splitting into channels")
            audio_segment = self._load_audio_file(audio_file_path)
            if audio_segment is None:
                return False, [], "Failed to load audio file"
            
            sample_rate = audio_segment.frame_rate
            logger.info(f"Loaded audio: {audio_segment.duration_seconds:.2f}s, {sample_rate}Hz")
            
            # Split into left and right channels (Speaker 1 & Speaker 2)
            channels = self._split_stereo_channels(audio_segment)
            
            # Process each channel separately
            channel_info_list = []
            
            speaker_map = {0: "left", 1: "right"}

            for i, channel_data in enumerate(channels):
                channel_id = speaker_map.get(i, f"channel_{i}")
                speaker_id = f"Speaker_{i+1}"
                
                logger.info(f"Step 2b: Processing {channel_id} channel ({speaker_id})")
                
                # Process each channel (save as MP3)
                success, processed_file_path, duration, file_size_mb = await self._process_channel(
                    channel_data,
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
    
    def _load_audio_file(self, audio_file_path: str) -> AudioSegment:
        """
        Load audio file using pydub.
        
        Args:
            audio_file_path: Path to audio file.
            
        Returns:
            AudioSegment object or None on error.
        """
        try:
            audio = AudioSegment.from_file(audio_file_path)
            return audio
        except Exception as e:
            logger.error(f"Error loading audio file {audio_file_path} with pydub: {str(e)}")
            return None
    
    def _split_stereo_channels(self, audio_data: AudioSegment) -> List[AudioSegment]:
        """
        Split stereo audio into a list of mono channels.
        
        Args:
            audio_data: Stereo audio data as an AudioSegment.
            
        Returns:
            List of mono AudioSegment objects for each channel.
        """
        if audio_data.channels > 1:
            logger.info(f"Splitting {audio_data.channels} channels.")
            return audio_data.split_to_mono()
        else:
            # If mono, duplicate it to maintain stereo structure for the pipeline
            logger.warning("Audio is mono, duplicating channel to create a stereo effect.")
            return [audio_data, audio_data]
    
    async def _process_channel(self, 
                             channel_data: AudioSegment, 
                             channel_id: str,
                             speaker_id: str) -> Tuple[bool, str, float, float]:
        """
        Process an individual audio channel by saving it as an MP3 file.
        
        Args:
            channel_data: Audio data for the channel as an AudioSegment.
            channel_id: Identifier for the channel (e.g., 'left' or 'right').
            speaker_id: Identifier for the speaker.
            
        Returns:
            A tuple containing success status, file path, duration, and file size.
        """
        try:
            duration = channel_data.duration_seconds
            
            # Save as MP3 file
            output_filename = f"{speaker_id}_{channel_id}.mp3"
            output_path = os.path.join(self.temp_dir, output_filename)
            
            success, file_size_mb = self._save_as_mp3(channel_data, output_path)
            if not success:
                return False, "", 0.0, 0.0
            
            return True, output_path, duration, file_size_mb
            
        except Exception as e:
            logger.error(f"Error processing {channel_id} channel: {str(e)}")
            return False, "", 0.0, 0.0

    def _save_as_mp3(self, audio_data: AudioSegment, output_path: str) -> Tuple[bool, float]:
        """
        Save AudioSegment as an MP3 file.
        
        Args:
            audio_data: AudioSegment to save.
            output_path: Output file path.
            
        Returns:
            Tuple[bool, float]: (success, file_size_mb)
        """
        try:
            # Export as MP3
            audio_data.export(output_path, format='mp3')
            
            # Calculate file size
            file_size_bytes = os.path.getsize(output_path)
            file_size_mb = file_size_bytes / (1024 * 1024)
            
            logger.info(f"Saved MP3 file: {output_path} ({file_size_mb:.2f}MB)")
            return True, file_size_mb
            
        except Exception as e:
            logger.error(f"Error saving MP3 file {output_path}: {str(e)}")
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
