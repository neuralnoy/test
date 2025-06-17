"""
Speaker Diarizer for channel-based speaker identification.
Converts Whisper transcription results into speaker-labeled segments.
"""
from typing import Tuple, List, Dict, Any, Optional
from app_whisper.models.schemas import AudioChunk, SpeakerSegment, WhisperTranscriptionResult
from common_new.logger import get_logger

logger = get_logger("businesslogic")

class SpeakerDiarizer:
    """Handles channel-based speaker diarization and segment creation."""
    
    def __init__(self, merge_threshold: float = 1.0, min_segment_duration: float = 0.5):
        """
        Initialize the diarizer.
        
        Args:
            merge_threshold: Gap threshold in seconds for merging consecutive segments from same speaker
            min_segment_duration: Minimum duration in seconds for a valid segment
        """
        self.merge_threshold = merge_threshold
        self.min_segment_duration = min_segment_duration
        
        logger.info(f"Initialized SpeakerDiarizer with merge_threshold: {merge_threshold}s, min_duration: {min_segment_duration}s")
    
    async def create_speaker_segments(self, 
                                    whisper_results: Dict[str, Any],
                                    channel_info_list: List,
                                    audio_chunks: List[AudioChunk]) -> Tuple[bool, List[SpeakerSegment], str]:
        """
        Create speaker segments from Whisper transcription results.
        
        Args:
            whisper_results: Results from WhisperTranscriber
            channel_info_list: List of ChannelInfo objects
            audio_chunks: List of AudioChunk objects
            
        Returns:
            Tuple[bool, List[SpeakerSegment], str]: (success, speaker_segments, error_message)
        """
        try:
            logger.info("Starting speaker segment creation from Whisper results")
            
            if not whisper_results or '_metadata' not in whisper_results:
                return False, [], "Invalid whisper results provided"
            
            metadata = whisper_results['_metadata']
            speakers = metadata.get('speakers', [])
            
            if not speakers:
                return False, [], "No speakers found in whisper results"
            
            logger.info(f"Processing transcription results for speakers: {speakers}")
            
            # Step 5a: Convert Whisper segments to SpeakerSegment objects
            all_speaker_segments = []
            
            for speaker_id in speakers:
                if speaker_id in whisper_results:
                    transcription_result = whisper_results[speaker_id]
                    
                    segments = self._convert_whisper_segments_to_speaker_segments(
                        speaker_id, transcription_result
                    )
                    
                    all_speaker_segments.extend(segments)
                    logger.info(f"Created {len(segments)} segments for {speaker_id}")
            
            if not all_speaker_segments:
                return False, [], "No valid segments created from Whisper results"
            
            # Step 5b: Merge all segments and sort by timestamp
            logger.info("Step 5b: Merging and sorting segments by timestamp")
            sorted_segments = sorted(all_speaker_segments, key=lambda x: x.start_time)
            
            # Step 5c: Detect overlapping speech periods
            logger.info("Step 5c: Detecting overlapping speech periods")
            overlap_info = self._detect_overlapping_speech(sorted_segments)
            
            # Step 5c.1: Clean up overlapping speech segments (NEW)
            logger.info("Step 5c.1: Cleaning up overlapping speech segments")
            cleaned_segments = self._cleanup_overlapping_speech(sorted_segments, overlap_info)
            
            # Step 5d: Merge consecutive segments from same speaker
            logger.info("Step 5d: Merging consecutive segments from same speaker")
            merged_segments = self._merge_consecutive_segments(cleaned_segments)
            
            # Final cleanup and validation
            final_segments = self._cleanup_segments(merged_segments)
            
            logger.info(f"Speaker diarization completed: {len(final_segments)} final segments")
            logger.info(f"Overlap detection: {overlap_info}")
            
            return True, final_segments, ""
            
        except Exception as e:
            error_msg = f"Error in speaker diarization: {str(e)}"
            logger.error(error_msg)
            return False, [], error_msg
    
    def _convert_whisper_segments_to_speaker_segments(self, 
                                                    speaker_id: str, 
                                                    transcription_result: WhisperTranscriptionResult) -> List[SpeakerSegment]:
        """
        Convert Whisper transcription segments to SpeakerSegment objects.
        
        Args:
            speaker_id: Speaker identifier (Speaker_1 or Speaker_2)
            transcription_result: WhisperTranscriptionResult object
            
        Returns:
            List of SpeakerSegment objects
        """
        speaker_segments = []
        
        try:
            segments = transcription_result.segments
            
            if not segments:
                # If no segments, create one segment from the full text
                if transcription_result.text.strip():
                    segment = SpeakerSegment(
                        start_time=0.0,
                        end_time=10.0,  # Default duration if no timing info
                        speaker_id=speaker_id,
                        text=transcription_result.text.strip(),
                        confidence=transcription_result.confidence
                    )
                    speaker_segments.append(segment)
                    logger.info(f"Created fallback segment for {speaker_id} from full text")
                
                return speaker_segments
            
            # Process each Whisper segment
            for i, whisper_segment in enumerate(segments):
                try:
                    # Extract timing information
                    start_time = float(whisper_segment.get('start', 0.0))
                    end_time = float(whisper_segment.get('end', start_time + 1.0))
                    text = whisper_segment.get('text', '').strip()
                    
                    # Skip segments that are too short or empty
                    if end_time - start_time < self.min_segment_duration or not text:
                        continue
                    
                    # Extract confidence if available
                    confidence = whisper_segment.get('confidence', transcription_result.confidence)
                    if confidence is None:
                        confidence = 0.8  # Default confidence
                    
                    # Create SpeakerSegment
                    speaker_segment = SpeakerSegment(
                        start_time=start_time,
                        end_time=end_time,
                        speaker_id=speaker_id,
                        text=text,
                        confidence=confidence
                    )
                    
                    speaker_segments.append(speaker_segment)
                    
                except Exception as e:
                    logger.warning(f"Error processing segment {i} for {speaker_id}: {str(e)}")
                    continue
            
            logger.info(f"Converted {len(speaker_segments)} Whisper segments to SpeakerSegments for {speaker_id}")
            
        except Exception as e:
            logger.error(f"Error converting Whisper segments for {speaker_id}: {str(e)}")
        
        return speaker_segments
    
    def _detect_overlapping_speech(self, sorted_segments: List[SpeakerSegment]) -> Dict[str, Any]:
        """
        Detect overlapping speech periods between speakers.
        
        Args:
            sorted_segments: List of SpeakerSegments sorted by start_time
            
        Returns:
            Dict with overlap statistics
        """
        overlaps = []
        total_overlap_duration = 0.0
        
        try:
            for i in range(len(sorted_segments)):
                current_segment = sorted_segments[i]
                
                # Check for overlaps with subsequent segments
                for j in range(i + 1, len(sorted_segments)):
                    next_segment = sorted_segments[j]
                    
                    # If next segment starts after current ends, no more overlaps possible
                    if next_segment.start_time >= current_segment.end_time:
                        break
                    
                    # Check if different speakers are overlapping
                    if current_segment.speaker_id != next_segment.speaker_id:
                        overlap_start = max(current_segment.start_time, next_segment.start_time)
                        overlap_end = min(current_segment.end_time, next_segment.end_time)
                        overlap_duration = overlap_end - overlap_start
                        
                        if overlap_duration > 0:
                            overlap_info = {
                                'start_time': overlap_start,
                                'end_time': overlap_end,
                                'duration': overlap_duration,
                                'speaker_1': current_segment.speaker_id,
                                'speaker_2': next_segment.speaker_id,
                                'segment_1_index': i,
                                'segment_2_index': j
                            }
                            overlaps.append(overlap_info)
                            total_overlap_duration += overlap_duration
            
            overlap_stats = {
                'overlap_count': len(overlaps),
                'total_overlap_duration': total_overlap_duration,
                'overlaps': overlaps
            }
            
            if overlaps:
                logger.info(f"Detected {len(overlaps)} overlapping speech periods (total: {total_overlap_duration:.2f}s)")
            
            return overlap_stats
            
        except Exception as e:
            logger.error(f"Error detecting overlapping speech: {str(e)}")
            return {'overlap_count': 0, 'total_overlap_duration': 0.0, 'overlaps': []}
    
    def _cleanup_overlapping_speech(self, 
                                   sorted_segments: List[SpeakerSegment], 
                                   overlap_info: Dict[str, Any]) -> List[SpeakerSegment]:
        """
        Clean up overlapping speech by removing non-dominant speakers during overlap periods.
        Uses duration coverage (70%) and text density (30%) to determine dominance.
        
        Args:
            sorted_segments: List of SpeakerSegments sorted by start_time
            overlap_info: Dictionary containing overlap detection results
            
        Returns:
            List of cleaned SpeakerSegments with overlaps resolved
        """
        if not overlap_info.get('overlaps'):
            logger.info("No overlaps detected, returning original segments")
            return sorted_segments
        
        overlaps = overlap_info['overlaps']
        logger.info(f"Processing {len(overlaps)} overlapping speech periods for cleanup")
        
        # Create a set to track segments that should be removed
        segments_to_remove = set()
        
        try:
            # Process each overlap
            for overlap in overlaps:
                overlap_start = overlap['start_time']
                overlap_end = overlap['end_time']
                overlap_duration = overlap['duration']
                speaker_1 = overlap['speaker_1']
                speaker_2 = overlap['speaker_2']
                
                # Find all segments that overlap in this period
                overlapping_segments = []
                for i, segment in enumerate(sorted_segments):
                    # Check if segment overlaps with this overlap period
                    if (segment.start_time < overlap_end and segment.end_time > overlap_start and
                        segment.speaker_id in [speaker_1, speaker_2]):
                        overlapping_segments.append((i, segment))
                
                if len(overlapping_segments) >= 2:
                    # Determine dominant speaker for this overlap
                    dominant_speaker_id = self._determine_dominant_speaker(overlapping_segments, overlap)
                    
                    # Mark non-dominant segments for removal if significant overlap (>50% of segment duration)
                    for seg_idx, segment in overlapping_segments:
                        if segment.speaker_id != dominant_speaker_id:
                            # Calculate how much of this segment overlaps with the overlap period
                            seg_overlap_start = max(segment.start_time, overlap_start)
                            seg_overlap_end = min(segment.end_time, overlap_end)
                            seg_overlap_duration = seg_overlap_end - seg_overlap_start
                            segment_total_duration = segment.end_time - segment.start_time
                            
                            # Remove if >50% of segment is within overlap OR if segment is entirely within overlap
                            overlap_percentage = seg_overlap_duration / segment_total_duration if segment_total_duration > 0 else 0
                            
                            if overlap_percentage > 0.5 or (segment.start_time >= overlap_start and segment.end_time <= overlap_end):
                                segments_to_remove.add(seg_idx)
                                logger.debug(f"Marking segment {seg_idx} for removal: {segment.speaker_id} "
                                           f"({segment.start_time:.2f}s-{segment.end_time:.2f}s) "
                                           f"overlap: {overlap_percentage:.1%} during {overlap_start:.2f}s-{overlap_end:.2f}s")
            
            # Create cleaned segments list by excluding marked segments
            cleaned_segments = []
            removed_count = 0
            
            for i, segment in enumerate(sorted_segments):
                if i not in segments_to_remove:
                    cleaned_segments.append(segment)
                else:
                    removed_count += 1
                    logger.debug(f"Removed overlapping segment: {segment.speaker_id} "
                               f"({segment.start_time:.2f}s-{segment.end_time:.2f}s) "
                               f"text: '{segment.text[:50]}...'")
            
            logger.info(f"Overlap cleanup completed: {len(overlaps)} overlaps processed, "
                       f"{removed_count} segments removed")
            
            return cleaned_segments
            
        except Exception as e:
            logger.error(f"Error in overlap cleanup: {str(e)}")
            return sorted_segments  # Return original segments if cleanup fails
    
    def _determine_dominant_speaker(self, 
                                   overlapping_segments: List[Tuple[int, SpeakerSegment]], 
                                   overlap: Dict[str, Any]) -> str:
        """
        Determine which speaker is dominant during an overlap period.
        Uses duration coverage (70%) and text density (30%) to calculate dominance.
        
        Args:
            overlapping_segments: List of (index, SpeakerSegment) tuples for overlapping segments
            overlap: Dictionary with overlap information
            
        Returns:
            Speaker ID of the dominant speaker
        """
        overlap_start = overlap['start_time']
        overlap_end = overlap['end_time']
        overlap_duration = overlap['duration']
        
        speaker_scores = {}
        
        try:
            for _, segment in overlapping_segments:
                speaker_id = segment.speaker_id
                
                # Calculate actual overlap duration for this segment
                seg_overlap_start = max(segment.start_time, overlap_start)
                seg_overlap_end = min(segment.end_time, overlap_end)
                seg_overlap_duration = seg_overlap_end - seg_overlap_start
                
                if seg_overlap_duration <= 0:
                    continue
                
                # 1. Duration Coverage Score (50% weight)
                # How much of the overlap period this speaker covers
                duration_score = seg_overlap_duration / overlap_duration
                
                # 2. Text Density Score (50% weight)
                # Approximate words spoken during overlap relative to segment length
                segment_duration = segment.end_time - segment.start_time
                total_words = len(segment.text.split())
                
                if segment_duration > 0 and total_words > 0:
                    # Estimate words in overlap period
                    words_in_overlap_ratio = seg_overlap_duration / segment_duration
                    estimated_words_in_overlap = max(1, int(total_words * words_in_overlap_ratio))
                    
                    # Text density: words per second in overlap
                    text_density = estimated_words_in_overlap / seg_overlap_duration
                    
                    # Normalize text density score (assume max reasonable density is 3 words/second)
                    text_score = min(1.0, text_density / 3.0)
                else:
                    text_score = 0.1  # Low score for segments with no meaningful text
                
                # Combined dominance score (duration-weighted: 70% duration + 30% text)
                dominance_score = (duration_score * 0.7) + (text_score * 0.3)
                
                # Track best score for each speaker
                if speaker_id not in speaker_scores:
                    speaker_scores[speaker_id] = []
                speaker_scores[speaker_id].append({
                    'score': dominance_score,
                    'duration_score': duration_score,
                    'text_score': text_score,
                    'words_in_overlap': estimated_words_in_overlap if segment_duration > 0 else 0,
                    'overlap_duration': seg_overlap_duration
                })
                
                logger.debug(f"Speaker {speaker_id} segment dominance: "
                           f"total={dominance_score:.3f} "
                           f"(duration={duration_score:.3f}, text={text_score:.3f}) "
                           f"words_est={estimated_words_in_overlap if segment_duration > 0 else 0}")
            
            # Select speaker with highest average score
            best_speaker = None
            best_avg_score = -1
            
            for speaker_id, score_list in speaker_scores.items():
                if not score_list:
                    continue
                    
                # Calculate average score for this speaker across all their segments in this overlap
                avg_score = sum(s['score'] for s in score_list) / len(score_list)
                total_duration = sum(s['overlap_duration'] for s in score_list)
                total_words = sum(s['words_in_overlap'] for s in score_list)
                
                logger.debug(f"Speaker {speaker_id} overlap summary: "
                           f"avg_score={avg_score:.3f}, "
                           f"total_duration={total_duration:.2f}s, "
                           f"total_words_est={total_words}")
                
                if avg_score > best_avg_score:
                    best_avg_score = avg_score
                    best_speaker = speaker_id
            
            logger.info(f"Dominant speaker for overlap {overlap_start:.2f}s-{overlap_end:.2f}s: "
                       f"{best_speaker} (avg_score: {best_avg_score:.3f})")
            
            return best_speaker or overlap['speaker_1']  # Fallback to first speaker
            
        except Exception as e:
            logger.error(f"Error determining dominant speaker: {str(e)}")
            return overlap['speaker_1']  # Fallback to first speaker
    
    def _merge_consecutive_segments(self, sorted_segments: List[SpeakerSegment]) -> List[SpeakerSegment]:
        """
        Merge consecutive segments from the same speaker if gap is below threshold.
        
        Args:
            sorted_segments: List of SpeakerSegments sorted by start_time
            
        Returns:
            List of merged SpeakerSegments
        """
        if not sorted_segments:
            return []
        
        merged_segments = []
        current_segment = sorted_segments[0]
        
        try:
            for i in range(1, len(sorted_segments)):
                next_segment = sorted_segments[i]
                
                # Check if we should merge with current segment
                should_merge = (
                    current_segment.speaker_id == next_segment.speaker_id and
                    next_segment.start_time - current_segment.end_time <= self.merge_threshold
                )
                
                if should_merge:
                    # Merge segments
                    merged_text = current_segment.text + " " + next_segment.text
                    merged_confidence = (current_segment.confidence + next_segment.confidence) / 2
                    
                    current_segment = SpeakerSegment(
                        start_time=current_segment.start_time,
                        end_time=next_segment.end_time,
                        speaker_id=current_segment.speaker_id,
                        text=merged_text.strip(),
                        confidence=merged_confidence
                    )
                    
                    logger.debug(f"Merged segments for {current_segment.speaker_id}: {current_segment.start_time:.2f}s-{current_segment.end_time:.2f}s")
                else:
                    # Add current segment to results and start new one
                    merged_segments.append(current_segment)
                    current_segment = next_segment
            
            # Add the last segment
            merged_segments.append(current_segment)
            
            original_count = len(sorted_segments)
            merged_count = len(merged_segments)
            logger.info(f"Merged consecutive segments: {original_count} -> {merged_count} segments")
            
        except Exception as e:
            logger.error(f"Error merging consecutive segments: {str(e)}")
            return sorted_segments  # Return original if merging fails
        
        return merged_segments
    
    def _cleanup_segments(self, segments: List[SpeakerSegment]) -> List[SpeakerSegment]:
        """
        Clean up segments by removing invalid ones and ensuring proper formatting.
        
        Args:
            segments: List of SpeakerSegments
            
        Returns:
            List of cleaned SpeakerSegments
        """
        cleaned_segments = []
        
        try:
            for segment in segments:
                # Validate segment
                if (segment.end_time > segment.start_time and 
                    segment.end_time - segment.start_time >= self.min_segment_duration and
                    segment.text.strip()):
                    
                    # Clean up text
                    cleaned_text = ' '.join(segment.text.split())  # Remove extra whitespace
                    
                    cleaned_segment = SpeakerSegment(
                        start_time=segment.start_time,
                        end_time=segment.end_time,
                        speaker_id=segment.speaker_id,
                        text=cleaned_text,
                        confidence=segment.confidence
                    )
                    
                    cleaned_segments.append(cleaned_segment)
                else:
                    logger.debug(f"Removed invalid segment: {segment.speaker_id} {segment.start_time:.2f}s-{segment.end_time:.2f}s")
            
            logger.info(f"Segment cleanup: {len(segments)} -> {len(cleaned_segments)} valid segments")
            
        except Exception as e:
            logger.error(f"Error cleaning up segments: {str(e)}")
            return segments  # Return original if cleanup fails
        
        return cleaned_segments
    
    def get_diarization_summary(self, speaker_segments: List[SpeakerSegment]) -> Dict[str, Any]:
        """
        Get summary statistics about the diarization results.
        
        Args:
            speaker_segments: List of SpeakerSegments
            
        Returns:
            Dict with summary statistics
        """
        if not speaker_segments:
            return {}
        
        # Group by speaker
        speaker_stats = {}
        total_duration = 0.0
        
        for segment in speaker_segments:
            speaker_id = segment.speaker_id
            duration = segment.end_time - segment.start_time
            
            if speaker_id not in speaker_stats:
                speaker_stats[speaker_id] = {
                    'segment_count': 0,
                    'total_duration': 0.0,
                    'total_words': 0,
                    'avg_confidence': 0.0,
                    'confidences': []
                }
            
            speaker_stats[speaker_id]['segment_count'] += 1
            speaker_stats[speaker_id]['total_duration'] += duration
            speaker_stats[speaker_id]['total_words'] += len(segment.text.split())
            speaker_stats[speaker_id]['confidences'].append(segment.confidence or 0.0)
            total_duration += duration
        
        # Calculate averages
        for speaker_id in speaker_stats:
            confidences = speaker_stats[speaker_id]['confidences']
            speaker_stats[speaker_id]['avg_confidence'] = sum(confidences) / len(confidences) if confidences else 0.0
            del speaker_stats[speaker_id]['confidences']  # Remove raw data
        
        summary = {
            'num_speakers': len(speaker_stats),
            'num_segments': len(speaker_segments),
            'total_duration': total_duration,
            'speaker_statistics': speaker_stats
        }
        
        return summary
    
    def cleanup(self):
        """Clean up resources (placeholder for future use)."""
        logger.info("SpeakerDiarizer cleanup completed")
    
    def __del__(self):
        """Cleanup on object destruction."""
        self.cleanup()
