"""
Audio File Downloader for Azure Blob Storage.
Downloads audio files from blob storage using the filename as blob name.
"""
import os
import tempfile
from typing import Tuple, Optional
from common_new.blob_storage import AsyncBlobStorageDownloader
from common_new.logger import get_logger

logger = get_logger("businesslogic")

class AudioFileDownloader:
    """Downloads audio files from Azure Blob Storage."""
    
    def __init__(self, container_name: Optional[str] = None):
        """
        Initialize the downloader.
        
        Args:
            container_name: Azure blob container name (if None, will use env var)
        """
        # Azure Storage configuration
        account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL", "https://your-account.blob.core.windows.net")
        self.container_name = container_name or os.getenv("AZURE_AUDIO_CONTAINER_NAME", "audio-files")
        
        # Initialize blob downloader
        self.blob_service = AsyncBlobStorageDownloader(
            account_url=account_url,
            container_name=self.container_name
        )
        
        # Create temp directory for downloads
        self.temp_dir = tempfile.mkdtemp(prefix="whisper_downloads_")
        logger.info(f"Initialized AudioFileDownloader with container: {self.container_name}")
        logger.info(f"Using temp directory: {self.temp_dir}")
    
    async def download_audio_file(self, filename: str) -> Tuple[bool, str, str]:
        """
        Download audio file from blob storage.
        
        Args:
            filename: The filename/blob name to download
            
        Returns:
            Tuple[bool, str, str]: (success, local_file_path, error_message)
        """
        try:
            logger.info(f"Starting download of audio file: {filename}")
            
            # Ensure the filename has a valid audio extension
            if not self._is_valid_audio_file(filename):
                error_msg = f"Invalid audio file format: {filename}"
                logger.error(error_msg)
                return False, "", error_msg
            
            # Create local file path
            local_file_path = os.path.join(self.temp_dir, filename)
            
            # Initialize downloader if needed
            await self.blob_service.initialize()
            
            # Download from blob storage
            downloaded_path = await self.blob_service.download_file(
                blob_name=filename,
                local_file_path=local_file_path
            )
            success = downloaded_path is not None
            
            if success:
                # Verify file was downloaded and has content
                if os.path.exists(local_file_path) and os.path.getsize(local_file_path) > 0:
                    file_size_mb = os.path.getsize(local_file_path) / (1024 * 1024)
                    logger.info(f"Successfully downloaded {filename} ({file_size_mb:.2f} MB) to {local_file_path}")
                    return True, local_file_path, ""
                else:
                    error_msg = f"Downloaded file is empty or doesn't exist: {local_file_path}"
                    logger.error(error_msg)
                    return False, "", error_msg
            else:
                error_msg = f"Failed to download {filename} from blob storage"
                logger.error(error_msg)
                return False, "", error_msg
                
        except Exception as e:
            error_msg = f"Error downloading audio file {filename}: {str(e)}"
            logger.error(error_msg)
            return False, "", error_msg
    
    def _is_valid_audio_file(self, filename: str) -> bool:
        """
        Check if filename has a valid audio extension.
        
        Args:
            filename: The filename to check
            
        Returns:
            bool: True if valid audio file extension
        """
        valid_extensions = {'.wav', '.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.webm', '.flac'}
        file_extension = os.path.splitext(filename)[1].lower()
        return file_extension in valid_extensions
    
    def verify_stereo_format(self, file_path: str) -> Tuple[bool, dict]:
        """
        Verify that the audio file is in stereo format (2 channels) using pydub.
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Tuple[bool, dict]: (is_stereo, audio_info)
        """
        try:
            from pydub import AudioSegment
            
            # Use pydub to get audio file info, which supports more formats
            audio = AudioSegment.from_file(file_path)
            
            audio_info = {
                'channels': audio.channels,
                'samplerate': audio.frame_rate,
                'duration': audio.duration_seconds,
                'format': os.path.splitext(file_path)[1],
                'subtype': None  # pydub does not provide a subtype
            }
            
            is_stereo = audio.channels == 2
            
            if is_stereo:
                logger.info(f"Audio file verified as stereo: {audio_info}")
            else:
                logger.warning(f"Audio file is not stereo ({audio.channels} channels): {audio_info}")
            
            return is_stereo, audio_info
            
        except Exception as e:
            logger.error(f"Error verifying audio format for {file_path}: {str(e)}")
            return False, {}
    
    def cleanup(self):
        """Clean up temporary downloaded files."""
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temporary directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up temp directory {self.temp_dir}: {str(e)}")
    
    def __del__(self):
        """Cleanup on object destruction."""
        self.cleanup()
