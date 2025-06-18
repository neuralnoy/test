"""
Audio format converter.
Handles converting audio files from one format to another (e.g., WAV to MP3).
"""
import os
from pydub import AudioSegment
from typing import Tuple, Optional
from common_new.logger import get_logger

logger = get_logger("businesslogic")

class AudioConverter:
    """Converts audio files to different formats."""

    def __init__(self):
        """Initialize the audio converter."""
        logger.info("Initialized AudioConverter.")

    def convert_to_mp3(self, input_path: str, output_dir: str, target_sample_rate: Optional[int] = None) -> Tuple[bool, str, str]:
        """
        Convert an audio file to MP3 format.
        It will replace the extension of the input file with .mp3.

        Args:
            input_path: Path to the input audio file.
            output_dir: Directory to save the converted MP3 file.
            target_sample_rate: Optional. The target sample rate in Hz. If provided, the audio will be resampled.

        Returns:
            Tuple[bool, str, str]: (success, output_path, error_message)
        """
        try:
            filename = os.path.basename(input_path)
            filename_without_ext, _ = os.path.splitext(filename)
            output_filename = f"{filename_without_ext}.mp3"
            output_path = os.path.join(output_dir, output_filename)

            logger.info(f"Converting '{input_path}' to MP3 format.")
            
            # Load the audio file
            audio = AudioSegment.from_file(input_path)
            
            # Resample if target sample rate is provided
            if target_sample_rate and audio.frame_rate != target_sample_rate:
                logger.info(f"Resampling audio from {audio.frame_rate} Hz to {target_sample_rate} Hz.")
                audio = audio.set_frame_rate(target_sample_rate)

            # Export as MP3
            audio.export(output_path, format="mp3")
            
            input_size_mb = os.path.getsize(input_path) / (1024 * 1024)
            output_size_mb = os.path.getsize(output_path) / (1024 * 1024)

            logger.info(f"Successfully converted to '{output_path}'.")
            logger.info(f"File size changed from {input_size_mb:.2f} MB to {output_size_mb:.2f} MB.")

            return True, output_path, ""

        except Exception as e:
            error_msg = f"Error converting file to MP3: {str(e)}"
            logger.error(error_msg)
            return False, "", error_msg 