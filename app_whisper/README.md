# Whisper Transcription and Diarization Service

This service provides a complete, end-to-end pipeline for transcribing and diarizing audio files, specifically optimized for call center recordings. It processes stereo audio, identifies the dominant speaker in overlapping segments, cleans up transcription artifacts, and produces a final, human-readable transcript.

## Core Logic & Workflow

The pipeline is designed to be robust, efficient, and clean. It executes the following steps in order for each audio file it processes:

### 1. Audio Download and Initial Validation
- **Source**: Downloads audio files from the Azure Blob Storage container specified by the `WHISPER_AUDIO_CONTAINER` environment variable.
- **Validation**:
    - Verifies that the audio file is in a supported format (e.g., `.wav`, `.mp3`).
    - Checks that the audio is stereo.
    - Ensures the audio duration is greater than a minimum threshold (e.g., 5 seconds) to avoid processing empty or trivial files.

### 2. Preprocessing & Silence Trimming
- **Component**: `AudioPreprocessor`
- **Actions**:
    1.  **Simultaneous Silence Trimming**: The first action is to analyze both channels of the stereo audio simultaneously. Any silence at the beginning or end of the recording where *both* channels are silent is trimmed. This is done without altering the synchronization between the channels.
    2.  **Channel Separation**: The (now trimmed) stereo audio is split into two separate mono channels.
    3.  **Speaker Assignment**: The channels are statically assigned:
        - **Left Channel** -> `Speaker_1` (assumed to be the call center agent)
        - **Right Channel**-> `Speaker_2` (assumed to be the client)
    4.  **Upsampling**: Each mono channel is upsampled to a 16,000 Hz sample rate, which is optimal for the Whisper transcription model.
    5.  **Format Conversion**: Each processed channel is saved as a separate `.flac` file for efficient processing.

### 3. Intelligent, Size-Based Chunking
- **Component**: `AudioChunker`
- **Purpose**: To handle large audio files that exceed the Whisper API's 25MB limit.
- **Logic**:
    - If both channel files are under 24MB, this step is skipped.
    - If either file is over 24MB, it calculates the minimum number of chunks needed to ensure every piece is under the limit. It then splits **both channels** into this same number of chunks.
    - **Synchronization is key**: `chunk 1` from Speaker 1 corresponds to the exact same time interval as `chunk 1` from Speaker 2.

### 4. Concurrent Transcription
- **Component**: `WhisperTranscriber`
- **Action**: All audio chunks are sent to the Azure OpenAI Whisper API for transcription.
- **Features**:
    - **Concurrency**: Chunks are transcribed in parallel to maximize throughput.
    - **Rate Limiting**: It communicates with a central counter service (`app_counter`) to ensure it never exceeds the API's rate limits, automatically waiting for an open slot if necessary.
    - **Segment Timestamps**: It requests segment-level timestamps, which are crucial for the diarization process.

### 5. Speaker Diarization (Simplified)
- **Component**: `SpeakerDiarizer`
- **Purpose**: To create a clean, chronological conversation from the raw transcribed segments.
- **Logic**:
    1.  **Aggregate & Sort**: All transcribed segments from both speakers are collected into a single list and sorted chronologically by their start time.
    2.  **Merge Consecutive Segments**: The sorted list is processed to find any consecutive segments that belong to the same speaker. These are merged into a single, longer segment. This creates a clean, turn-by-turn conversational flow.

### 6. Post-Processing and Cleaning
- **Component**: `TranscriptionPostProcessor`
- **Purpose**: To clean and format the final transcript, correcting for common AI transcription artifacts.
- **Actions**:
    1.  **Whitespace Normalization**: It removes any extra spaces between words, ensuring clean and consistent formatting.
    2.  **Repetition Cleaning**: It detects and cleans up "hallucinations" where a single word is repeated more than three times (e.g., "yes yes yes yes yes"). It truncates the sequence to three occurrences and adds "..." to signify the cleanup. This logic is case-insensitive and handles punctuation.
    3.  **Final Formatting**: It assembles the cleaned segments into the final string output, formatted as `Speaker_ID: [text]`.

### 7. Guaranteed Cleanup & Monitoring
- **Mechanism**: The entire pipeline is wrapped in a `try...finally` block.
- **Guaranteed Execution**: The `finally` block ensures that **all temporary directories and files** created during the process (downloaded audio, processed channels, chunks) are reliably and completely deleted from the disk, even if an error occurs mid-pipeline.
- **Monitoring**:
    - **Execution Time**: The total time taken for the pipeline to run is logged upon completion or failure.
    - **Memory Usage**: The pipeline logs the process's memory usage at the start and end of execution to monitor its resource footprint.

## Configuration

The service is configured through environment variables. The most critical ones are:
- `APP_BLOB_ACCOUNT_NAME`: The name of the Azure Blob Storage account.
- `WHISPER_AUDIO_CONTAINER`: The container within the storage account where audio files are located.
- `APP_OPENAI_API_BASE`: The endpoint for the Azure OpenAI service.
- `APP_OPENAI_ENGINE`: The name of the Whisper model deployment.
- `COUNTER_APP_BASE_URL`: The URL for the rate-limiting counter service.

## How to Run

1.  Ensure all dependencies are installed:
    ```bash
    pip install -r requirements.txt
    ```
2.  Set up the necessary environment variables in a `.env` file or as system variables.
3.  The service is triggered by messages to a queue, which are handled by the `data_processor.py`.
