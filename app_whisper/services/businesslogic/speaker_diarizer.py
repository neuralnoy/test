"""
Speaker diarization for Step 3 of the whisper pipeline.
Uses local audio features for speaker segmentation and identification (no external models required).
"""
import os
import numpy as np
from typing import List, Dict, Optional, Tuple
import torch
import torchaudio
from sklearn.cluster import AgglomerativeClustering
from sklearn.preprocessing import StandardScaler
from scipy.signal import spectrogram
from common_new.logger import get_logger

logger = get_logger("whisper")

class SpeakerSegment:
    """Represents a speaker segment with timing information."""
    def __init__(self, speaker_id: str, start_time: float, end_time: float, confidence: float = 1.0):
        self.speaker_id = speaker_id
        self.start_time = start_time
        self.end_time = end_time
        self.confidence = confidence
    
    def __repr__(self):
        return f"SpeakerSegment(speaker={self.speaker_id}, {self.start_time:.2f}s-{self.end_time:.2f}s, conf={self.confidence:.3f})"

class SpeakerDiarizer:
    """
    Handles speaker diarization using local audio features (no external models required).
    
    This class implements Step 3 of the whisper pipeline using:
    - MFCC features for speaker characterization
    - Spectral features (pitch, formants, spectral centroid)
    - Agglomerative clustering for speaker grouping
    """
    
    def __init__(self, 
                 model_source: str = "local",  # Kept for compatibility but ignored
                 min_segment_duration: float = 1.0,
                 similarity_threshold: float = 0.75,
                 max_speakers: int = 6):
        """
        Initialize the speaker diarizer.
        
        Args:
            model_source: Ignored (kept for compatibility)
            min_segment_duration: Minimum duration for a speaker segment (seconds)
            similarity_threshold: Threshold for speaker similarity clustering
            max_speakers: Maximum number of speakers to detect
        """
        self.min_segment_duration = min_segment_duration
        self.similarity_threshold = similarity_threshold
        self.max_speakers = max_speakers
        
        logger.info(f"Initializing SpeakerDiarizer with local features (no external models required)")
    
    def _load_model(self):
        """No model loading required for local feature extraction."""
        logger.info("Using local feature extraction (no model loading required)")
    
    def diarize_audio(self, audio_path: str) -> List[SpeakerSegment]:
        """
        Perform speaker diarization on an audio file.
        
        Args:
            audio_path: Path to the preprocessed audio file
            
        Returns:
            List[SpeakerSegment]: List of speaker segments with timing
        """
        try:
            logger.info(f"Starting local speaker diarization for: {audio_path}")
            
            # Load audio with torchaudio
            waveform, sample_rate = torchaudio.load(audio_path)
            logger.info(f"Loaded audio: {waveform.shape}, sample_rate: {sample_rate}")
            
            # Convert to mono if stereo
            if waveform.shape[0] > 1:
                waveform = torch.mean(waveform, dim=0, keepdim=True)
                logger.info("Converted stereo to mono")
            
            # Get audio duration
            duration = waveform.shape[1] / sample_rate
            logger.info(f"Audio duration: {duration:.2f} seconds")
            
            # Extract speaker features using sliding window
            segments = self._extract_speaker_segments(waveform, sample_rate, duration)
            
            # Cluster speakers based on features
            clustered_segments = self._cluster_speakers(segments)
            
            logger.info(f"Local diarization completed: {len(clustered_segments)} segments, "
                       f"{len(set(seg.speaker_id for seg in clustered_segments))} speakers detected")
            
            return clustered_segments
            
        except Exception as e:
            logger.error(f"Error in local speaker diarization for {audio_path}: {str(e)}")
            # Return a single segment covering the whole audio as fallback
            return [SpeakerSegment("1", 0.0, self._get_audio_duration(audio_path), 0.5)]
    
    def _extract_speaker_segments(self, waveform: torch.Tensor, sample_rate: int, duration: float) -> List[Dict]:
        """
        Extract speaker features from audio using sliding window approach.
        
        Args:
            waveform: Audio waveform tensor
            sample_rate: Sample rate of the audio
            duration: Total duration of audio
            
        Returns:
            List[Dict]: List of segments with features and timing
        """
        segments = []
        window_size = 3.0  # 3-second windows
        hop_size = 1.5     # 1.5-second hop (50% overlap)
        
        window_samples = int(window_size * sample_rate)
        hop_samples = int(hop_size * sample_rate)
        
        logger.info(f"Extracting local features with {window_size}s windows, {hop_size}s hop")
        
        for start_sample in range(0, waveform.shape[1] - window_samples + 1, hop_samples):
            end_sample = start_sample + window_samples
            start_time = start_sample / sample_rate
            end_time = end_sample / sample_rate
            
            # Extract window
            window = waveform[0, start_sample:end_sample].numpy()
            
            try:
                # Extract multiple speaker features
                features = self._extract_window_features(window, sample_rate)
                
                segments.append({
                    'start_time': start_time,
                    'end_time': end_time,
                    'features': features,
                    'duration': window_size
                })
                
            except Exception as e:
                logger.warning(f"Failed to extract features for segment {start_time:.2f}-{end_time:.2f}s: {str(e)}")
                continue
        
        logger.info(f"Extracted features from {len(segments)} segments")
        return segments
    
    def _extract_window_features(self, window: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Extract comprehensive speaker features from an audio window.
        
        Args:
            window: Audio samples for the window
            sample_rate: Sample rate of the audio
            
        Returns:
            np.ndarray: Feature vector for the window
        """
        features = []
        
        # 1. MFCC features (most important for speaker identification)
        from python_speech_features import mfcc
        mfcc_features = mfcc(window, sample_rate, numcep=13, nfilt=26, nfft=512)
        features.extend(np.mean(mfcc_features, axis=0))  # Mean across time
        features.extend(np.std(mfcc_features, axis=0))   # Std across time
        
        # 2. Spectral features
        f, t, Sxx = spectrogram(window, sample_rate, nperseg=512, noverlap=256)
        
        # Spectral centroid (brightness)
        spectral_centroid = np.sum(f[:, np.newaxis] * Sxx, axis=0) / np.sum(Sxx, axis=0)
        features.extend([np.mean(spectral_centroid), np.std(spectral_centroid)])
        
        # Spectral rolloff
        cumsum_power = np.cumsum(Sxx, axis=0)
        total_power = cumsum_power[-1, :]
        rolloff_85 = np.argmax(cumsum_power >= 0.85 * total_power, axis=0)
        features.extend([np.mean(rolloff_85), np.std(rolloff_85)])
        
        # 3. Energy features
        energy = np.sum(window ** 2)
        features.append(energy)
        
        # Zero crossing rate
        zero_crossings = np.sum(np.diff(np.sign(window)) != 0)
        features.append(zero_crossings / len(window))
        
        # 4. Pitch-related features (fundamental frequency estimation)
        # Simple autocorrelation-based pitch estimation
        autocorr = np.correlate(window, window, mode='full')
        autocorr = autocorr[len(autocorr)//2:]
        
        # Find pitch period (avoid very low frequencies)
        min_period = int(sample_rate / 500)  # 500 Hz max
        max_period = int(sample_rate / 50)   # 50 Hz min
        
        if len(autocorr) > max_period:
            pitch_autocorr = autocorr[min_period:max_period]
            if len(pitch_autocorr) > 0:
                pitch_period = np.argmax(pitch_autocorr) + min_period
                pitch_freq = sample_rate / pitch_period if pitch_period > 0 else 0
                features.append(pitch_freq)
            else:
                features.append(0)
        else:
            features.append(0)
        
        return np.array(features)
    
    def _cluster_speakers(self, segments: List[Dict]) -> List[SpeakerSegment]:
        """
        Cluster speaker segments based on feature similarity.
        
        Args:
            segments: List of segments with features
            
        Returns:
            List[SpeakerSegment]: Clustered speaker segments
        """
        if not segments:
            return []
        
        logger.info("Clustering speaker features...")
        
        # Extract features
        features = np.array([seg['features'] for seg in segments])
        
        # Normalize features
        scaler = StandardScaler()
        features_normalized = scaler.fit_transform(features)
        
        # Estimate number of speakers (between 1 and max_speakers)
        n_segments = len(segments)
        if n_segments <= 2:
            n_clusters = 1
        else:
            # Use a heuristic: roughly 1 speaker per 10 segments, but cap at max_speakers
            n_clusters = min(max(1, n_segments // 10), self.max_speakers)
        
        logger.info(f"Clustering {n_segments} segments into {n_clusters} speakers")
        
        # Perform agglomerative clustering
        clustering = AgglomerativeClustering(
            n_clusters=n_clusters,
            linkage='ward'  # Ward linkage works well with normalized features
        )
        
        cluster_labels = clustering.fit_predict(features_normalized)
        
        # Create speaker segments
        speaker_segments = []
        for i, segment in enumerate(segments):
            speaker_id = str(cluster_labels[i] + 1)  # Simple numeric speaker IDs
            
            # Calculate confidence based on cluster cohesion
            # Use distance from cluster center as confidence measure
            cluster_mask = cluster_labels == cluster_labels[i]
            cluster_features = features_normalized[cluster_mask]
            cluster_center = np.mean(cluster_features, axis=0)
            
            # Distance from center (lower distance = higher confidence)
            distance = np.linalg.norm(features_normalized[i] - cluster_center)
            confidence = max(0.1, 1.0 - min(distance / 2.0, 0.9))  # Scale to 0.1-1.0
            
            speaker_segments.append(SpeakerSegment(
                speaker_id=speaker_id,
                start_time=segment['start_time'],
                end_time=segment['end_time'],
                confidence=confidence
            ))
        
        # Merge consecutive segments from the same speaker
        merged_segments = self._merge_consecutive_segments(speaker_segments)
        
        logger.info(f"Clustered into {len(set(seg.speaker_id for seg in merged_segments))} speakers")
        return merged_segments
    
    def _merge_consecutive_segments(self, segments: List[SpeakerSegment]) -> List[SpeakerSegment]:
        """
        Merge consecutive segments from the same speaker.
        
        Args:
            segments: List of speaker segments
            
        Returns:
            List[SpeakerSegment]: Merged segments
        """
        if not segments:
            return []
        
        # Sort segments by start time
        segments.sort(key=lambda x: x.start_time)
        
        merged = []
        current = segments[0]
        
        for next_seg in segments[1:]:
            # If same speaker and segments are close (within 0.5 seconds)
            if (current.speaker_id == next_seg.speaker_id and 
                next_seg.start_time - current.end_time <= 0.5):
                # Merge segments
                current.end_time = next_seg.end_time
                current.confidence = (current.confidence + next_seg.confidence) / 2
            else:
                # Add current segment and start new one
                if current.end_time - current.start_time >= self.min_segment_duration:
                    merged.append(current)
                current = next_seg
        
        # Add the last segment
        if current.end_time - current.start_time >= self.min_segment_duration:
            merged.append(current)
        
        logger.info(f"Merged segments: {len(segments)} → {len(merged)}")
        return merged
    
    def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio duration as fallback."""
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0
        except:
            return 60.0  # Default fallback
    
    def get_diarization_summary(self, segments: List[SpeakerSegment]) -> Dict:
        """
        Get summary statistics of the diarization results.
        
        Args:
            segments: List of speaker segments
            
        Returns:
            Dict: Summary statistics
        """
        if not segments:
            return {"num_speakers": 0, "total_duration": 0, "segments": 0}
        
        speakers = set(seg.speaker_id for seg in segments)
        total_duration = max(seg.end_time for seg in segments)
        avg_confidence = sum(seg.confidence for seg in segments) / len(segments)
        
        speaker_durations = {}
        for speaker in speakers:
            speaker_segments = [seg for seg in segments if seg.speaker_id == speaker]
            speaker_duration = sum(seg.end_time - seg.start_time for seg in speaker_segments)
            speaker_durations[speaker] = speaker_duration
        
        return {
            "num_speakers": len(speakers),
            "total_duration": total_duration,
            "segments": len(segments),
            "avg_confidence": avg_confidence,
            "speaker_durations": speaker_durations
        } 