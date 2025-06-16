# Audio Processing Pipeline with Channel-Based Speaker Diarization

A complete audio processing pipeline that downloads stereo audio files from Azure Blob Storage, processes them through OpenAI Whisper for transcription, and performs channel-based speaker diarization to create timestamped conversation transcripts.

## Overview

This pipeline processes stereo audio files by treating each channel as a separate speaker (left channel = Speaker_1, right channel = Speaker_2). It handles the complete workflow from file download to final transcript generation with comprehensive error handling and logging.

## Architecture

### Pipeline Flow

1. **Audio File Download** - Downloads audio from Azure Blob Storage
2. **Audio Preprocessing** - Converts to FLAC, splits channels, resamples to 16kHz, trims silence
3. **Audio Chunking** - Creates manageable chunks (24MB max) while maintaining timestamp alignment
4. **Parallel Transcription** - Processes both channels simultaneously using OpenAI Whisper
5. **Speaker Diarization** - Converts channel-based segments to speaker-labeled segments
6. **Post-Processing** - Creates final transcript with speaker labels and timestamps
7. **Cleanup** - Removes temporary files

### Core Components

- **AudioFileDownloader** - Downloads audio files from Azure Blob Storage
- **AudioPreprocessor** - Handles format conversion, channel separation, and audio optimization
- **AudioChunker** - Splits large audio files into processable chunks
- **WhisperTranscriber** - Manages parallel OpenAI Whisper API calls
- **SpeakerDiarizer** - Converts channel-based audio to speaker segments
- **TranscriptionPostProcessor** - Creates final formatted transcripts

## Requirements

### Dependencies

```
soundfile>=0.12.1
librosa>=0.10.0
numpy>=1.24.0
scikit-learn>=1.3.0
openai>=1.0.0
azure-storage-blob>=12.19.0
azure-identity>=1.15.0
pydantic>=2.0.0
fastapi>=0.104.0
```

### Environment Variables

```bash
# Azure Storage Configuration
AZURE_STORAGE_ACCOUNT_URL=https://youraccount.blob.core.windows.net
AZURE_AUDIO_CONTAINER_NAME=audio-files

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key
OPENAI_API_BASE=https://your-azure-openai-endpoint.openai.azure.com/  # For Azure OpenAI

# Optional: Application Name for logging
APP_NAME=audio_processor
```

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables (see above)

3. Ensure Azure credentials are configured (using DefaultAzureCredential)

## Usage

### Basic Usage

```python
from app_whisper.services.businesslogic.pipeline import process_audio

# Process an audio file
success, result = await process_audio("example_audio.wav")

if success:
    print(f"Transcription: {result.text}")
    print(f"Number of speakers: {len(set(seg.speaker_id for seg in result.speaker_segments))}")
    print(f"Processing time: {result.processing_metadata.processing_time_seconds:.2f}s")
else:
    print(f"Processing failed: {result.text}")
```

### Integration with Data Processor

```python
from app_whisper.services.data_processor import process_audio_request

# This is the main entry point used by the FastAPI application
success, result = await process_audio_request("filename.wav")
```

## Configuration

### Audio Processing Settings

- **Maximum file size per chunk**: 24MB (to stay within OpenAI Whisper limits)
- **Target sample rate**: 16kHz (optimal for Whisper)
- **Audio format**: FLAC (for compression and quality)
- **Minimum segment duration**: 0.5 seconds
- **Speaker merge threshold**: 1.0 seconds

### Transcription Settings

- **Whisper model**: Configurable (default: latest available)
- **Response format**: verbose_json (includes word-level timestamps)
- **Concurrent requests**: Maximum 3 simultaneous API calls
- **API request delay**: 0.1 seconds between requests
- **Success threshold**: 80% of chunks must succeed

### Speaker Diarization Settings

- **Channel mapping**: Left = Speaker_1, Right = Speaker_2
- **Overlap detection**: Automatic detection of simultaneous speech
- **Segment merging**: Consecutive segments from same speaker within 1.0s are merged
- **Confidence weighting**: Duration-weighted confidence scores

## Data Models

### Core Schemas

**SpeakerSegment**
```python
{
    "start_time": 0.0,           # Segment start time in seconds
    "end_time": 5.2,             # Segment end time in seconds
    "speaker_id": "Speaker_1",   # Speaker identifier
    "text": "Hello there",       # Transcribed text
    "confidence": 0.85           # Confidence score (0.0-1.0)
}
```

**ChannelInfo**
```python
{
    "channel_id": "left",        # Channel identifier
    "speaker_id": "Speaker_1",   # Associated speaker
    "file_path": "/path/to/file.flac",
    "duration": 120.5,           # Duration in seconds
    "file_size_mb": 3.2          # File size in megabytes
}
```

**InternalWhisperResult**
```python
{
    "text": "Complete transcript...",
    "diarization": true,
    "confidence": 0.87,
    "speaker_segments": [...],   # List of SpeakerSegment objects
    "processing_metadata": {...} # ProcessingMetadata object
}
```

## Output Formats

### Plain Text Transcript
```
Speaker_1 [00:00:00 - 00:00:03]: Hello, how are you today?
Speaker_2 [00:00:03 - 00:00:07]: I'm doing well, thank you for asking.
```

### JSON Format
```json
{
    "conversation": [
        {
            "speaker": "Speaker_1",
            "start_time": 0.0,
            "end_time": 3.2,
            "text": "Hello, how are you today?",
            "confidence": 0.89
        }
    ],
    "summary": {
        "total_duration": 120.5,
        "num_speakers": 2,
        "num_segments": 45,
        "average_confidence": 0.87
    }
}
```

## Error Handling

The pipeline includes comprehensive error handling at each stage:

- **Download failures**: Network issues, missing files, authentication problems
- **Audio processing errors**: Invalid formats, corrupted files, processing failures
- **API failures**: Rate limiting, quota exceeded, service unavailable
- **Resource management**: Automatic cleanup of temporary files

### Error Response Format

```python
InternalWhisperResult(
    text="Error description here",
    diarization=False,
    processing_metadata=ProcessingMetadata(
        filename="problem_file.wav",
        processing_time_seconds=5.2,
        transcription_method="failed",
        chunk_method="none"
    )
)
```

## Testing

### Quick Structure Test

```bash
python -m app_whisper.test_pipeline_simple
```

This runs a fast test that verifies:
- All imports work correctly
- Schema objects can be created
- Components can be initialized
- Pipeline structure is valid

### Manual Testing

For end-to-end testing, ensure you have:
1. Valid Azure Storage credentials
2. OpenAI API access
3. A stereo audio file in your blob storage container

## Performance Characteristics

### Processing Times

- **Small files (< 5MB)**: 30-60 seconds
- **Medium files (5-25MB)**: 1-3 minutes  
- **Large files (25-100MB)**: 3-10 minutes

*Times depend on audio duration, API response times, and chunk processing*

### Resource Usage

- **Memory**: ~500MB peak during processing
- **Disk**: 2-3x original file size for temporary files
- **Network**: Parallel API calls optimize throughput

### Limitations

- **Maximum file size**: Limited by available disk space and processing time
- **Audio formats**: Supports common formats (WAV, MP3, MP4, FLAC, etc.)
- **Channel requirement**: Optimized for stereo audio (2 channels)
- **API rate limits**: Respects OpenAI Whisper API limitations

## Troubleshooting

### Common Issues

**Import Errors**
- Verify all dependencies are installed
- Check Python path and module structure

**Azure Connection Issues**  
- Verify `AZURE_STORAGE_ACCOUNT_URL` is correct
- Ensure Azure credentials are properly configured
- Check container name and file permissions

**OpenAI API Issues**
- Verify API key is valid and has sufficient quota
- Check endpoint configuration for Azure OpenAI
- Monitor rate limiting and retry logic

**Audio Processing Errors**
- Ensure audio files are valid and not corrupted
- Check file size limits (large files may need chunking)
- Verify stereo format for optimal results

### Debug Logging

The pipeline includes comprehensive logging at INFO level. For debugging, enable DEBUG level logging:

```python
import logging
logging.getLogger("audio_processor").setLevel(logging.DEBUG)
```

## Contributing

When modifying the pipeline:

1. Maintain backward compatibility in schemas
2. Add comprehensive error handling for new components
3. Update tests for any structural changes
4. Follow the existing logging patterns
5. Ensure proper cleanup of resources

## License

[Include your license information here]
