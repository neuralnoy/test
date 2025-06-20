"""
Speaker Diarizer for channel-based speaker identification.
Converts Whisper transcription results into speaker-labeled segments.
"""

from common_new.logger import get_logger
import librosa
import numpy as np
import itertools
from typing import List, Tuple
from app_whisper.models.schemas import SpeakerSegment

logger = get_logger("businesslogic")

class AudioDiarizer:
    """
    Performs speaker diarization on a stereo audio file where each channel
    represents a distinct speaker. It uses per-frame energy (RMS) to determine
    the active speaker and an inertia mechanism to resolve overlapping speech.
    """

    def __init__(self, frame_sec: float = 0.05, hop_sec: float = 0.025, energy_threshold_ratio: float = 0.15, inertia_sec: float = 0.5):
        """
        Initializes the diarizer with parameters for audio processing.

        Args:
            frame_sec: The length of each analysis frame in seconds.
            hop_sec: The step size between frames in seconds.
            energy_threshold_ratio: The RMS threshold for speech detection, as a ratio of the channel's max RMS.
            inertia_sec: The duration in seconds to look back to determine speaker momentum for resolving overlaps.
        """
        self.frame_sec = frame_sec
        self.hop_sec = hop_sec
        self.energy_threshold_ratio = energy_threshold_ratio
        self.inertia_sec = inertia_sec
        self.speaker_ids = ["Speaker_1", "Speaker_2"]
        logger.info(f"Initialized AudioDiarizer with: frame_sec={frame_sec}, hop_sec={hop_sec}, energy_ratio={energy_threshold_ratio}, inertia={inertia_sec}s")

    def diarize(self, file_path: str) -> Tuple[bool, List[SpeakerSegment], str]:
        """
        Processes a stereo audio file to generate speaker-labeled segments.

        Args:
            file_path: The path to the stereo audio file to be diarized.

        Returns:
            A tuple containing:
            - bool: True if diarization was successful, False otherwise.
            - List[SpeakerSegment]: A list of speaker segments.
            - str: An error message if diarization failed.
        """
        try:
            logger.info(f"Starting diarization for audio file: {file_path}")
            y, sr = librosa.load(file_path, sr=None, mono=False)

            if y.shape[0] != 2:
                msg = f"Audio file is not stereo (has {y.shape[0]} channels), cannot perform channel-based diarization."
                logger.error(msg)
                return False, [], msg
            
            # --- 1. Convert time-based parameters to sample/frame units ---
            frame_length = int(self.frame_sec * sr)
            hop_length = int(self.hop_sec * sr)
            inertia_frames = int(self.inertia_sec / self.hop_sec)

            # --- 2. Calculate RMS energy for each channel ---
            rms1 = librosa.feature.rms(y=y[0], frame_length=frame_length, hop_length=hop_length)[0]
            rms2 = librosa.feature.rms(y=y[1], frame_length=frame_length, hop_length=hop_length)[0]
            
            # --- 3. Determine active speaker per frame (with overlaps) ---
            threshold1 = np.max(rms1) * self.energy_threshold_ratio
            threshold2 = np.max(rms2) * self.energy_threshold_ratio
            
            frame_labels = []
            for i in range(len(rms1)):
                active1 = rms1[i] > threshold1
                active2 = rms2[i] > threshold2
                
                if active1 and active2:
                    frame_labels.append("Overlap")
                elif active1:
                    frame_labels.append(self.speaker_ids[0])
                elif active2:
                    frame_labels.append(self.speaker_ids[1])
                else:
                    frame_labels.append("Silence")

            # --- 4. Apply inertia to resolve overlaps ---
            final_labels = list(frame_labels)
            for i, label in enumerate(frame_labels):
                if label == "Overlap":
                    start = max(0, i - inertia_frames)
                    window = final_labels[start:i]
                    
                    count1 = window.count(self.speaker_ids[0])
                    count2 = window.count(self.speaker_ids[1])
                    
                    if count1 > count2:
                        final_labels[i] = self.speaker_ids[0]
                    elif count2 > count1:
                        final_labels[i] = self.speaker_ids[1]
                    else: # Tie-breaker: assign to louder speaker in the current frame
                        final_labels[i] = self.speaker_ids[0] if rms1[i] > rms2[i] else self.speaker_ids[1]
            
            # --- 5. Convert frame labels to time-based segments ---
            segments = []
            for speaker, group in itertools.groupby(enumerate(final_labels), key=lambda x: x[1]):
                if speaker == "Silence":
                    continue
                
                frame_indices = [item[0] for item in group]
                start_frame = frame_indices[0]
                end_frame = frame_indices[-1] + 1

                start_time = librosa.frames_to_time(start_frame, sr=sr, hop_length=hop_length)
                end_time = librosa.frames_to_time(end_frame, sr=sr, hop_length=hop_length)
                
                segments.append(SpeakerSegment(start_time=start_time, end_time=end_time, speaker_id=speaker))

            logger.info(f"Diarization complete. Found {len(segments)} speaker segments.")
            return True, segments, ""

        except Exception as e:
            error_msg = f"An unexpected error occurred during diarization: {e}"
            logger.error(error_msg, exc_info=True)
            return False, [], error_msg