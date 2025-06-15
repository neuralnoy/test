"""
Audio file downloader for fetching audio files from Azure Blob Storage.
Handles Step 1 of the whisper pipeline: Input Processing.
"""
import os
import tempfile
from typing import Optional
from common_new.blob_storage import AsyncBlobStorageDownloader
from common_new.logger import get_logger

logger = get_logger("whisper")

class AudioFileDownloader:
    """
    Handles downloading audio files from Azure Blob Storage for processing.
    
    This class implements Step 1 of the whisper pipeline: receiving audio files
    from Azure Blob Storage based on filename from service bus message.
    """
    
    def __init__(self):
        """Initialize the downloader with environment variables."""
        self.account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
        self.container_name = os.getenv("WHISPER_AUDIO_CONTAINER", "audio-files")
        
        # Create temporary directory for audio downloads
        self.temp_dir = tempfile.mkdtemp(prefix="whisper_audio_")
        logger.info(f"Created temporary directory for audio: {self.temp_dir}")
        
        if not self.account_url:
            raise ValueError("AZURE_STORAGE_ACCOUNT_URL environment variable is required")
        
        self.downloader = AsyncBlobStorageDownloader(
            account_url=self.account_url,
            container_name=self.container_name,
            download_dir=self.temp_dir
        )
    
    async def download_audio_file(self, filename: str) -> Optional[str]:
        """
        Download an audio file from Azure Blob Storage.
        
        Args:
            filename: Name of the audio file (blob name) to download
            
        Returns:
            str: Local path to the downloaded file, or None if download failed
        """
        try:
            logger.info(f"Starting download of audio file: {filename}")
            
            # Initialize the downloader if not already done
            if not self.downloader._initialized:
                success = await self.downloader.initialize()
                if not success:
                    logger.error("Failed to initialize blob storage downloader")
                    return None
            
            # Download the file
            local_path = await self.downloader.download_file(filename)
            
            if local_path and os.path.exists(local_path):
                file_size = os.path.getsize(local_path)
                logger.info(f"Successfully downloaded {filename} to {local_path} ({file_size} bytes)")
                return local_path
            else:
                logger.error(f"Failed to download audio file: {filename}")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading audio file {filename}: {str(e)}")
            return None
    
    def get_audio_info(self, local_path: str) -> dict:
        """
        Get basic information about the downloaded audio file.
        
        Args:
            local_path: Path to the local audio file
            
        Returns:
            dict: Audio file information
        """
        try:
            from pydub import AudioSegment
            
            # Load audio file with pydub
            audio = AudioSegment.from_file(local_path)
            
            # Get duration in seconds
            duration = len(audio) / 1000.0
            
            return {
                "file_path": local_path,
                "file_size": os.path.getsize(local_path),
                "duration": duration,
                "format": os.path.splitext(local_path)[1].lower(),
                "sample_rate": audio.frame_rate,
                "channels": audio.channels
            }
        except Exception as e:
            logger.warning(f"Could not get audio info for {local_path}: {str(e)}")
            return {
                "file_path": local_path,
                "file_size": os.path.getsize(local_path),
                "duration": None,
                "format": os.path.splitext(local_path)[1].lower(),
                "sample_rate": None,
                "channels": None
            }
    
    def cleanup_temp_files(self):
        """Clean up temporary downloaded files."""
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temporary directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up temporary files: {str(e)}") 