"""
Speaker diarization for Step 3 of the whisper pipeline.
Uses Resemblyzer for speaker embeddings and identification.
"""
import os
import numpy as np
from typing import List, Dict, Optional, Tuple
from resemblyzer import VoiceEncoder, preprocess_wav
from pydub import AudioSegment
from sklearn.cluster import AgglomerativeClustering
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity
from app_whisper.models.schemas import SpeakerSegment
from common_new.logger import get_logger

logger = get_logger("whisper")

class SpeakerDiarizer:
    """
    Handles speaker diarization using Resemblyzer for voice embeddings.
    
    This class implements Step 3 of the whisper pipeline using:
    - Resemblyzer for speaker embeddings
    - Sliding window approach for segment extraction
    - Agglomerative clustering for speaker grouping
    """
    
    def __init__(self, 
                 model_source: str = "resemblyzer",
                 min_segment_duration: float = 1.0,
                 similarity_threshold: float = 0.75,
                 max_speakers: int = 6,
                 window_size: float = 1.5,  # seconds
                 hop_size: float = 0.75):   # seconds
        """
        Initialize the speaker diarizer.
        
        Args:
            model_source: Model source (ignored, always uses Resemblyzer)
            min_segment_duration: Minimum duration for a speaker segment (seconds)
            similarity_threshold: Threshold for speaker similarity clustering
            max_speakers: Maximum number of speakers to detect
            window_size: Size of analysis windows in seconds
            hop_size: Hop size between windows in seconds
        """
        self.min_segment_duration = min_segment_duration
        self.similarity_threshold = similarity_threshold
        self.max_speakers = max_speakers
        self.window_size = window_size
        self.hop_size = hop_size
        self.encoder = None
        
        logger.info(f"Initializing SpeakerDiarizer with Resemblyzer")
        logger.info(f"Config: min_duration={min_segment_duration}s, similarity={similarity_threshold}, "
                   f"max_speakers={max_speakers}, window={window_size}s, hop={hop_size}s")
    
    def _load_model(self):
        """Load the Resemblyzer voice encoder."""
        if self.encoder is None:
            logger.info("Loading Resemblyzer voice encoder...")
            try:
                self.encoder = VoiceEncoder()
                logger.info("Resemblyzer voice encoder loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load Resemblyzer: {str(e)}")
                raise
    
    def diarize_audio(self, audio_path: str) -> List[SpeakerSegment]:
        """
        Perform speaker diarization on an audio file.
        
        Args:
            audio_path: Path to the preprocessed audio file
            
        Returns:
            List[SpeakerSegment]: List of speaker segments with timing
        """
        try:
            logger.info(f"Starting Resemblyzer speaker diarization for: {audio_path}")
            
            # Load the voice encoder
            self._load_model()
            
            # Load and preprocess audio
            audio = AudioSegment.from_file(audio_path)
            duration = len(audio) / 1000.0  # Convert to seconds
            logger.info(f"Audio duration: {duration:.2f} seconds")
            
            # Convert to numpy array for Resemblyzer
            # Resemblyzer expects 16kHz mono audio
            audio_16k = audio.set_frame_rate(16000).set_channels(1)
            audio_array = np.array(audio_16k.get_array_of_samples(), dtype=np.float32)
            audio_array = audio_array / np.max(np.abs(audio_array))  # Normalize
            
            # Preprocess with Resemblyzer
            wav = preprocess_wav(audio_array, 16000)
            logger.info(f"Preprocessed audio shape: {wav.shape}")
            
            # Extract embeddings using sliding window
            embeddings, timestamps = self._extract_embeddings(wav, duration)
            
            if len(embeddings) == 0:
                logger.warning("No valid embeddings extracted, returning single speaker")
                return [SpeakerSegment(speaker_id="Speaker_1", start_time=0.0, end_time=duration, confidence=0.5)]
            
            # Cluster speakers based on embeddings
            clustered_segments = self._cluster_speakers(embeddings, timestamps, duration)
            
            logger.info(f"Resemblyzer diarization completed: {len(clustered_segments)} segments, "
                       f"{len(set(seg.speaker_id for seg in clustered_segments))} speakers detected")
            
            return clustered_segments
            
        except Exception as e:
            logger.error(f"Error in Resemblyzer speaker diarization for {audio_path}: {str(e)}")
            # Return a single segment covering the whole audio as fallback
            duration = self._get_audio_duration(audio_path)
            return [SpeakerSegment(speaker_id="Speaker_1", start_time=0.0, end_time=duration, confidence=0.5)]
    
    def _extract_embeddings(self, wav: np.ndarray, duration: float) -> Tuple[List[np.ndarray], List[float]]:
        """
        Extract speaker embeddings from audio using sliding window.
        
        Args:
            wav: Preprocessed audio array
            duration: Total duration of audio
            
        Returns:
            Tuple[List[np.ndarray], List[float]]: Embeddings and their center timestamps
        """
        sample_rate = 16000  # Resemblyzer uses 16kHz
        window_samples = int(self.window_size * sample_rate)
        hop_samples = int(self.hop_size * sample_rate)
        
        embeddings = []
        timestamps = []
        
        logger.info(f"Extracting embeddings with {self.window_size}s windows, {self.hop_size}s hop")
        
        for start_sample in range(0, len(wav) - window_samples + 1, hop_samples):
            end_sample = start_sample + window_samples
            start_time = start_sample / sample_rate
            end_time = end_sample / sample_rate
            center_time = (start_time + end_time) / 2
            
            # Extract window
            window = wav[start_sample:end_sample]
            
            # Skip windows that are too quiet
            if np.max(np.abs(window)) < 0.01:
                continue
            
            try:
                # Get embedding for this window
                embedding = self.encoder.embed_utterance(window)
                embeddings.append(embedding)
                timestamps.append(center_time)
                
            except Exception as e:
                logger.warning(f"Failed to extract embedding for segment {start_time:.2f}-{end_time:.2f}s: {str(e)}")
                continue
        
        logger.info(f"Extracted {len(embeddings)} embeddings from {duration:.2f}s audio")
        return embeddings, timestamps
    
    def _cluster_speakers(self, embeddings: List[np.ndarray], timestamps: List[float], duration: float) -> List[SpeakerSegment]:
        """
        Cluster speaker embeddings and create segments.
        
        Args:
            embeddings: List of speaker embeddings
            timestamps: Center timestamps for each embedding
            duration: Total audio duration
            
        Returns:
            List[SpeakerSegment]: Clustered speaker segments
        """
        if len(embeddings) == 0:
            return [SpeakerSegment(speaker_id="Speaker_1", start_time=0.0, end_time=duration, confidence=0.5)]
        
        if len(embeddings) == 1:
            return [SpeakerSegment(speaker_id="Speaker_1", start_time=0.0, end_time=duration, confidence=1.0)]
        
        # Convert embeddings to numpy array
        embedding_matrix = np.array(embeddings)
        logger.info(f"Clustering {len(embeddings)} embeddings of shape {embedding_matrix.shape}")
        
        # Determine optimal number of clusters
        n_clusters = min(self.max_speakers, len(embeddings))
        
        # Use similarity-based clustering
        # Calculate similarity matrix
        similarity_matrix = cosine_similarity(embedding_matrix)
        distance_matrix = 1 - similarity_matrix
        
        # Agglomerative clustering
        clustering = AgglomerativeClustering(
            n_clusters=None,
            metric='precomputed',
            linkage='average',
            distance_threshold=1 - self.similarity_threshold
        )
        
        try:
            cluster_labels = clustering.fit_predict(distance_matrix)
            n_clusters_found = len(np.unique(cluster_labels))
            logger.info(f"Found {n_clusters_found} speaker clusters")
        except Exception as e:
            logger.warning(f"Clustering failed: {str(e)}, using single speaker")
            cluster_labels = np.zeros(len(embeddings))
            n_clusters_found = 1
        
        # Create segments from clusters
        segments = []
        for i, (timestamp, cluster_id) in enumerate(zip(timestamps, cluster_labels)):
            speaker_id = f"Speaker_{cluster_id + 1}"
            
            # Calculate segment boundaries
            start_time = max(0, timestamp - self.hop_size / 2)
            end_time = min(duration, timestamp + self.hop_size / 2)
            
            # Calculate confidence based on cluster coherence
            confidence = self._calculate_confidence(embeddings[i], embeddings, cluster_labels, cluster_id)
            
            segments.append(SpeakerSegment(speaker_id=speaker_id, start_time=start_time, end_time=end_time, confidence=confidence))
        
        # Merge consecutive segments from the same speaker
        merged_segments = self._merge_consecutive_segments(segments)
        
        # Filter out segments that are too short
        filtered_segments = [seg for seg in merged_segments if seg.end_time - seg.start_time >= self.min_segment_duration]
        
        if not filtered_segments:
            # If all segments were filtered out, return a single segment
            return [SpeakerSegment(speaker_id="Speaker_1", start_time=0.0, end_time=duration, confidence=0.5)]
        
        logger.info(f"Final segments: {len(filtered_segments)} after merging and filtering")
        return filtered_segments
    
    def _calculate_confidence(self, embedding: np.ndarray, all_embeddings: List[np.ndarray], 
                            cluster_labels: np.ndarray, cluster_id: int) -> float:
        """Calculate confidence score for a speaker assignment."""
        # Get embeddings from the same cluster
        same_cluster_indices = np.where(cluster_labels == cluster_id)[0]
        
        if len(same_cluster_indices) <= 1:
            return 0.5
        
        # Calculate similarity to other embeddings in the same cluster
        similarities = []
        for idx in same_cluster_indices:
            if np.array_equal(embedding, all_embeddings[idx]):
                continue
            similarity = cosine_similarity([embedding], [all_embeddings[idx]])[0][0]
            similarities.append(similarity)
        
        if not similarities:
            return 0.5
        
        return min(1.0, max(0.0, np.mean(similarities)))
    
    def _merge_consecutive_segments(self, segments: List[SpeakerSegment]) -> List[SpeakerSegment]:
        """
        Merge consecutive segments from the same speaker.
        
        Args:
            segments: List of segments to merge
            
        Returns:
            List[SpeakerSegment]: Merged segments
        """
        if not segments:
            return []
        
        # Sort segments by start time
        sorted_segments = sorted(segments, key=lambda x: x.start_time)
        merged = []
        current = sorted_segments[0]
        
        for next_segment in sorted_segments[1:]:
            # Check if segments are from the same speaker and consecutive/overlapping
            if (current.speaker_id == next_segment.speaker_id and 
                next_segment.start_time <= current.end_time + 0.5):  # 0.5s gap tolerance
                
                # Merge segments
                current.end_time = max(current.end_time, next_segment.end_time)
                current.confidence = max(current.confidence, next_segment.confidence)
            else:
                # Add current segment and start new one
                merged.append(current)
                current = next_segment
        
        # Add the last segment
        merged.append(current)
        
        logger.info(f"Merged {len(segments)} segments into {len(merged)} segments")
        return merged
    
    def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio duration in seconds."""
        try:
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0
        except Exception as e:
            logger.error(f"Failed to get audio duration: {str(e)}")
            return 0.0
    
    def get_diarization_summary(self, segments: List[SpeakerSegment]) -> Dict:
        """
        Generate a summary of the diarization results.
        
        Args:
            segments: List of speaker segments
            
        Returns:
            Dict: Summary statistics
        """
        if not segments:
            return {
                "num_speakers": 0,
                "num_segments": 0,
                "total_duration": 0.0,
                "speaker_durations": {},
                "average_segment_duration": 0.0
            }
        
        speakers = set(seg.speaker_id for seg in segments)
        total_duration = sum(seg.end_time - seg.start_time for seg in segments)
        
        speaker_durations = {}
        for speaker in speakers:
            speaker_segments = [seg for seg in segments if seg.speaker_id == speaker]
            speaker_duration = sum(seg.end_time - seg.start_time for seg in speaker_segments)
            speaker_durations[speaker] = round(speaker_duration, 2)
        
        return {
            "num_speakers": len(speakers),
            "num_segments": len(segments),
            "total_duration": round(total_duration, 2),
            "speaker_durations": speaker_durations,
            "average_segment_duration": round(total_duration / len(segments), 2)
        } 