"""
Speaker Diarizer for channel-based speaker identification.
Converts Whisper transcription results into speaker-labeled segments.
"""
from typing import List, Dict, Optional
from app_whisper.models.schemas import SpeakerSegment, TranscribedChunk
from common_new.logger import get_logger
import math

logger = get_logger("businesslogic")

class SpeakerDiarizer:
    """
    Performs speaker diarization and filtering based on word density dominance.
    Identifies the dominant speaker in sliding windows and filters out the non-dominant speaker's transcription.
    """

    def diarize_and_filter(
        self,
        transcribed_chunks: List[TranscribedChunk],
        window_size: float = 3.0
    ) -> List[SpeakerSegment]:
        """
        Processes transcribed chunks to identify and retain only the dominant speaker's words.

        Args:
            transcribed_chunks: A list of transcribed chunks with word-level timestamps.
            window_size: The size of the sliding window in seconds for density calculation.

        Returns:
            A list of SpeakerSegment objects containing only the text from the dominant speaker.
        """
        logger.info("Starting speaker diarization and dominance filtering.")
        
        # 1. Aggregate all words from all chunks with their absolute timestamps
        all_words = self._get_all_words(transcribed_chunks)
        if not all_words:
            logger.warning("No words found in transcribed chunks to perform diarization.")
            return []

        # 2. Determine total duration and number of windows
        total_duration = max(word['end'] for word in all_words) if all_words else 0
        num_windows = math.ceil(total_duration / window_size)
        logger.info(f"Total audio duration: {total_duration:.2f}s, processing in {num_windows} windows of {window_size}s.")

        # 3. Calculate word densities for each speaker in each window
        density_vectors = self._calculate_word_densities(all_words, num_windows, window_size)

        # 4. Determine the dominant speaker for each window
        dominant_speakers_by_window = self._get_dominant_speakers(density_vectors)

        # 5. Filter words based on dominance and merge them into final speaker segments
        final_segments = self._create_final_segments(all_words, dominant_speakers_by_window, window_size)
        
        logger.info(f"Diarization complete. Generated {len(final_segments)} final speaker segments.")
        return final_segments

    def _get_all_words(self, transcribed_chunks: List[TranscribedChunk]) -> List[Dict]:
        """Extracts and flattens all word-level data from transcribed chunks."""
        all_words = []
        for t_chunk in transcribed_chunks:
            if t_chunk.error or not t_chunk.transcription_result or not t_chunk.transcription_result.segments:
                continue
            
            chunk_start_time = t_chunk.chunk.start_time
            speaker_id = t_chunk.chunk.speaker_id

            for segment in t_chunk.transcription_result.segments:
                if 'words' not in segment or not segment['words']:
                    continue
                for word_info in segment['words']:
                    all_words.append({
                        'text': word_info['word'],
                        'start': word_info['start'] + chunk_start_time,
                        'end': word_info['end'] + chunk_start_time,
                        'speaker_id': speaker_id
                    })
        
        all_words.sort(key=lambda x: x['start'])
        return all_words

    def _calculate_word_densities(self, all_words: List[Dict], num_windows: int, window_size: float) -> Dict[str, List[int]]:
        """Calculates the number of words spoken by each speaker in each window."""
        densities = {
            '*Speaker 1*': [0] * num_windows,
            '*Speaker 2*': [0] * num_windows
        }
        for word in all_words:
            window_index = math.floor(word['start'] / window_size)
            if window_index < num_windows:
                speaker = word['speaker_id']
                if speaker in densities:
                    densities[speaker][window_index] += 1
        return densities

    def _get_dominant_speakers(self, density_vectors: Dict[str, List[int]]) -> List[Optional[str]]:
        """Determines the dominant speaker for each window based on word density ratio."""
        num_windows = len(density_vectors['*Speaker 1*'])
        dominant_speakers = []
        for i in range(num_windows):
            d1 = density_vectors['*Speaker 1*'][i]
            d2 = density_vectors['*Speaker 2*'][i]
            
            total_density = d1 + d2
            if total_density == 0:
                dominant_speakers.append(None)  # Indicates silence
                continue

            # If ratio is >= 0.5, Speaker 1 is dominant. This handles division by zero implicitly.
            ratio = d1 / total_density
            if ratio >= 0.5:
                dominant_speakers.append('*Speaker 1*')
            else:
                dominant_speakers.append('*Speaker 2*')
        return dominant_speakers

    def _create_final_segments(self, all_words: List[Dict], dominant_speakers_by_window: List[Optional[str]], window_size: float) -> List[SpeakerSegment]:
        """Filters words based on dominance and merges them into clean speaker segments."""
        filtered_words = []
        for word in all_words:
            window_index = math.floor(word['start'] / window_size)
            if window_index < len(dominant_speakers_by_window):
                dominant_speaker = dominant_speakers_by_window[window_index]
                if word['speaker_id'] == dominant_speaker:
                    filtered_words.append(word)
        
        if not filtered_words:
            return []
            
        final_segments = []
        current_segment = SpeakerSegment(
            start_time=filtered_words[0]['start'],
            end_time=filtered_words[0]['end'],
            speaker_id=filtered_words[0]['speaker_id'],
            text=filtered_words[0]['text'].strip()
        )

        for i in range(1, len(filtered_words)):
            word = filtered_words[i]
            # Merge if the speaker is the same and the gap is small (e.g., < 0.5s)
            time_gap = word['start'] - current_segment.end_time
            if word['speaker_id'] == current_segment.speaker_id and time_gap < 0.5:
                current_segment.text += " " + word['text'].strip()
                current_segment.end_time = word['end']
            else:
                final_segments.append(current_segment)
                current_segment = SpeakerSegment(
                    start_time=word['start'],
                    end_time=word['end'],
                    speaker_id=word['speaker_id'],
                    text=word['text'].strip()
                )
        
        final_segments.append(current_segment)
        return final_segments