"""
Speaker diarization for Step 3 of the whisper pipeline.
Uses SpeechBrain for high-quality speaker segmentation and identification.
"""
import os
import tempfile
from typing import List, Dict, Optional, Tuple
import torch
import torchaudio
from speechbrain.inference.speaker import SpeakerRecognition
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
    Handles speaker diarization using SpeechBrain.
    
    This class implements Step 3 of the whisper pipeline:
    - Speaker embedding extraction
    - Speaker clustering and identification
    - Timestamped speaker segments generation
    """
    
    def __init__(self, 
                 model_source: str = "speechbrain/spkrec-ecapa-voxceleb",
                 min_segment_duration: float = 1.0,
                 similarity_threshold: float = 0.75):
        """
        Initialize the speaker diarizer.
        
        Args:
            model_source: SpeechBrain model for speaker recognition
            min_segment_duration: Minimum duration for a speaker segment (seconds)
            similarity_threshold: Threshold for speaker similarity clustering
        """
        self.model_source = model_source
        self.min_segment_duration = min_segment_duration
        self.similarity_threshold = similarity_threshold
        self.speaker_model = None
        
        logger.info(f"Initializing SpeakerDiarizer with model: {model_source}")
    
    def _load_model(self):
        """Load the SpeechBrain speaker recognition model."""
        if self.speaker_model is None:
            try:
                logger.info("Loading SpeechBrain speaker recognition model...")
                self.speaker_model = SpeakerRecognition.from_hparams(
                    source=self.model_source,
                    savedir=tempfile.mkdtemp(prefix="speechbrain_")
                )
                logger.info("SpeechBrain model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load SpeechBrain model: {str(e)}")
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
            logger.info(f"Starting speaker diarization for: {audio_path}")
            
            # Load the model if not already loaded
            self._load_model()
            
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
            
            # Perform sliding window speaker embedding extraction
            segments = self._extract_speaker_segments(waveform, sample_rate, duration)
            
            # Cluster speakers based on embeddings
            clustered_segments = self._cluster_speakers(segments)
            
            logger.info(f"Diarization completed: {len(clustered_segments)} segments, "
                       f"{len(set(seg.speaker_id for seg in clustered_segments))} speakers detected")
            
            return clustered_segments
            
        except Exception as e:
            logger.error(f"Error in speaker diarization for {audio_path}: {str(e)}")
            # Return a single segment covering the whole audio as fallback
            return [SpeakerSegment("Speaker_1", 0.0, self._get_audio_duration(audio_path), 0.5)]
    
    def _extract_speaker_segments(self, waveform: torch.Tensor, sample_rate: int, duration: float) -> List[Dict]:
        """
        Extract speaker embeddings from audio using sliding window approach.
        
        Args:
            waveform: Audio waveform tensor
            sample_rate: Sample rate of the audio
            duration: Total duration of audio
            
        Returns:
            List[Dict]: List of segments with embeddings and timing
        """
        segments = []
        window_size = 3.0  # 3-second windows
        hop_size = 1.5     # 1.5-second hop (50% overlap)
        
        window_samples = int(window_size * sample_rate)
        hop_samples = int(hop_size * sample_rate)
        
        logger.info(f"Extracting embeddings with {window_size}s windows, {hop_size}s hop")
        
        for start_sample in range(0, waveform.shape[1] - window_samples + 1, hop_samples):
            end_sample = start_sample + window_samples
            start_time = start_sample / sample_rate
            end_time = end_sample / sample_rate
            
            # Extract window
            window = waveform[:, start_sample:end_sample]
            
            try:
                # Get speaker embedding
                embedding = self.speaker_model.encode_batch(window.unsqueeze(0))
                
                segments.append({
                    'start_time': start_time,
                    'end_time': end_time,
                    'embedding': embedding.squeeze().cpu().numpy(),
                    'duration': window_size
                })
                
            except Exception as e:
                logger.warning(f"Failed to extract embedding for segment {start_time:.2f}-{end_time:.2f}s: {str(e)}")
                continue
        
        logger.info(f"Extracted {len(segments)} speaker embeddings")
        return segments
    
    def _cluster_speakers(self, segments: List[Dict]) -> List[SpeakerSegment]:
        """
        Cluster speaker segments based on embedding similarity.
        
        Args:
            segments: List of segments with embeddings
            
        Returns:
            List[SpeakerSegment]: Clustered speaker segments
        """
        if not segments:
            return []
        
        import numpy as np
        from sklearn.cluster import AgglomerativeClustering
        from sklearn.metrics.pairwise import cosine_similarity
        
        logger.info("Clustering speaker embeddings...")
        
        # Extract embeddings
        embeddings = np.array([seg['embedding'] for seg in segments])
        
        # Compute cosine similarity matrix
        similarity_matrix = cosine_similarity(embeddings)
        
        # Convert similarity to distance (1 - similarity)
        distance_matrix = 1 - similarity_matrix
        
        # Perform agglomerative clustering
        # Estimate number of speakers (between 1 and 6)
        n_clusters = min(max(1, len(segments) // 10), 6)
        
        clustering = AgglomerativeClustering(
            n_clusters=n_clusters,
            metric='precomputed',
            linkage='average'
        )
        
        cluster_labels = clustering.fit_predict(distance_matrix)
        
        # Create speaker segments
        speaker_segments = []
        for i, segment in enumerate(segments):
            speaker_id = f"Speaker_{cluster_labels[i] + 1}"
            
            # Calculate confidence based on intra-cluster similarity
            cluster_mask = cluster_labels == cluster_labels[i]
            cluster_similarities = similarity_matrix[i][cluster_mask]
            confidence = float(np.mean(cluster_similarities))
            
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