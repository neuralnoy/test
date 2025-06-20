"""
Audio Preprocessor for channel-based speaker diarization.
"""

from common_new.logger import get_logger
import os
import tempfile
import librosa
import numpy as np
import soundfile as sf
from typing import Tuple

logger = get_logger("mono_businesslogic_preprocessor")

class AudioPreprocessor:
    """Preprocesses stereo audio for channel-based speaker diarization."""
    
    def __init__(self):
        """Initializes the preprocessor and creates a temporary directory for output files."""
        self.temp_dir = tempfile.mkdtemp(prefix="whisper_preprocessed_")
        logger.info(f"Initialized AudioPreprocessor with temp directory: {self.temp_dir}")

    def remove_silence_from_stereo(self, file_path: str, top_db: int = 40) -> Tuple[bool, str, str]:
        """
        Removes periods where both channels are silent from a stereo audio file.

        It works by creating a mono representation that is loud if *either* channel is loud,
        then finds the non-silent parts of that mono track and uses those timings to clip
        the original stereo audio.

        Args:
            file_path: Path to the input stereo audio file.
            top_db: The threshold (in dB) below the peak to consider as silence.

        Returns:
            Tuple[bool, str, str]: (success, output_file_path, error_message)
        """
        try:
            logger.info(f"Starting silence removal for {file_path} with top_db={top_db}")
            
            y, sr = librosa.load(file_path, sr=None, mono=False)

            if y.shape[0] != 2:
                msg = f"Audio file {file_path} is not stereo (has {y.shape[0]} channels), cannot remove shared silence."
                logger.error(msg)
                return False, "", msg
            
            y_mono_for_split = np.max(np.abs(y), axis=0)
            
            non_silent_intervals = librosa.effects.split(y_mono_for_split, top_db=top_db)
            
            if len(non_silent_intervals) == 0:
                msg = f"The entire audio file {file_path} was detected as silent."
                logger.warning(msg)
                # Return success but with an empty path to indicate no audio is left.
                return True, "", "File is entirely silent"

            y_trimmed = np.concatenate([y[:, start:end] for start, end in non_silent_intervals], axis=1)

            original_basename = os.path.splitext(os.path.basename(file_path))[0]
            output_filename = f"{original_basename}_silence_removed.wav"
            output_filepath = os.path.join(self.temp_dir, output_filename)
            
            sf.write(output_filepath, y_trimmed.T, sr, format='WAV', subtype='PCM_16')
            
            original_duration = librosa.get_duration(y=y, sr=sr)
            trimmed_duration = librosa.get_duration(y=y_trimmed, sr=sr)
            removed_duration = original_duration - trimmed_duration
            
            logger.info(f"Silence removal complete. Original: {original_duration:.2f}s, New: {trimmed_duration:.2f}s, Removed: {removed_duration:.2f}s.")
            logger.info(f"Saved silence-removed file to: {output_filepath}")
            
            return True, output_filepath, ""

        except Exception as e:
            error_msg = f"Error during silence removal for {file_path}: {str(e)}"
            logger.error(error_msg)
            return False, "", error_msg

    def process_to_mono_flac(self, file_path: str, target_sr: int = 16000) -> Tuple[bool, str, str, dict]:
        """
        Converts an audio file to a mono, 16kHz FLAC file.

        Args:
            file_path: Path to the input audio file.
            target_sr: The target sample rate.

        Returns:
            Tuple[bool, str, str, dict]: (success, output_file_path, error_message, audio_info)
        """
        try:
            logger.info(f"Starting mono conversion and resampling for {file_path} to {target_sr}Hz.")
            
            # Load the file, converting to mono and resampling to the target sample rate
            y, sr = librosa.load(file_path, sr=target_sr, mono=True)
            
            # Create the output path
            original_basename = os.path.splitext(os.path.basename(file_path))[0]
            output_filename = f"{original_basename}_mono_16k.flac"
            output_filepath = os.path.join(self.temp_dir, output_filename)
            
            # Write the mono, resampled audio to a FLAC file
            sf.write(output_filepath, y, sr, format='FLAC', subtype='PCM_16')
            
            # Gather info about the processed file
            file_size_mb = os.path.getsize(output_filepath) / (1024 * 1024)
            duration = librosa.get_duration(y=y, sr=sr)
            
            audio_info = {
                'sample_rate': sr,
                'duration': duration,
                'channels': 1,
                'file_size_mb': file_size_mb,
                'path': output_filepath
            }
            
            logger.info(f"Successfully converted to mono FLAC at {target_sr}Hz. Output at: {output_filepath}")
            logger.info(f"Processed audio info: {audio_info}")
            
            return True, output_filepath, "", audio_info

        except Exception as e:
            error_msg = f"Error during mono conversion/resampling for {file_path}: {str(e)}"
            logger.error(error_msg)
            return False, "", error_msg, {}

    def cleanup(self):
        """Clean up the temporary directory used for preprocessed files."""
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temporary preprocessor directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up temp directory {self.temp_dir}: {str(e)}")

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()