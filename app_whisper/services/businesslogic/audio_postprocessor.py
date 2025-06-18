"""
Transcription Post-Processor for final assembly and formatting.
Creates diarized transcripts with proper speaker labels and conversation flow.
"""
from typing import Tuple, List, Dict, Any, Optional
from app_whisper.models.schemas import SpeakerSegment, WhisperTranscriptionResult
from common_new.logger import get_logger

logger = get_logger("businesslogic")

class TranscriptionPostProcessor:
    """Handles final transcript assembly and formatting."""
    
    def __init__(self, 
                 include_timestamps: bool = True,
                 include_confidence: bool = False,
                 timestamp_format: str = "[{:02d}:{:05.2f}]"):
        """
        Initialize the post-processor.
        
        Args:
            include_timestamps: Whether to include timestamps in final transcript
            include_confidence: Whether to include confidence scores
            timestamp_format: Format string for timestamps (minutes:seconds)
        """
        self.include_timestamps = include_timestamps
        self.include_confidence = include_confidence
        self.timestamp_format = timestamp_format
        
        logger.info(f"Initialized TranscriptionPostProcessor with timestamps: {include_timestamps}, confidence: {include_confidence}")
    
    async def create_final_transcript(self,
                                    speaker_segments: List[SpeakerSegment],
                                    whisper_results: Dict[str, Any],
                                    channel_info_list: List) -> Tuple[bool, Dict[str, Any], str]:
        """
        Create the final diarized transcript with proper formatting.
        
        Args:
            speaker_segments: List of SpeakerSegment objects
            whisper_results: Results from WhisperTranscriber
            channel_info_list: List of ChannelInfo objects
            
        Returns:
            Tuple[bool, Dict[str, Any], str]: (success, final_result, error_message)
        """
        try:
            logger.info(f"Creating final transcript from {len(speaker_segments)} speaker segments")
            
            if not speaker_segments:
                return False, {}, "No speaker segments provided for transcript creation"
            
            # Step 6a: Create consolidated transcript without timestamps and with speaker consolidation
            logger.info("Step 6a: Creating consolidated transcript")
            diarized_transcript = self._create_consolidated_transcript(speaker_segments)
            
            # Step 6b: Generate conversation flow with proper formatting
            logger.info("Step 6b: Generating conversation flow with proper formatting")
            conversation_flow = self._generate_conversation_flow(speaker_segments)
            
            # Create speaker summary
            speaker_summary = self._create_speaker_summary(speaker_segments)
            
            # Create timing summary
            timing_summary = self._create_timing_summary(speaker_segments)
            
            # Calculate overall confidence
            overall_confidence = self._calculate_overall_confidence(speaker_segments)
            
            # Assemble final result
            final_result = {
                'text': diarized_transcript,
                'conversation_flow': conversation_flow,
                'speaker_summary': speaker_summary,
                'timing_summary': timing_summary,
                'confidence': overall_confidence,
                'format_info': {
                    'includes_timestamps': False,  # Updated to reflect consolidated format
                    'includes_confidence': self.include_confidence,
                    'total_segments': len(speaker_segments),
                    'speakers': list(set(seg.speaker_id for seg in speaker_segments))
                }
            }
            
            logger.info(f"Final transcript created: {len(diarized_transcript)} characters")
            logger.info(f"Conversation flow: {len(conversation_flow)} turns")
            logger.info(f"Overall confidence: {overall_confidence:.3f}")
            
            return True, final_result, ""
            
        except Exception as e:
            error_msg = f"Error creating final transcript: {str(e)}"
            logger.error(error_msg)
            return False, {}, error_msg
    
    def _create_consolidated_transcript(self, speaker_segments: List[SpeakerSegment]) -> str:
        """
        Create a consolidated transcript without timestamps and with speaker consolidation.
        Only shows speaker labels when the speaker changes.
        
        Args:
            speaker_segments: List of SpeakerSegment objects sorted by time
            
        Returns:
            String containing the consolidated transcript
        """
        transcript_lines = []
        
        try:
            # Sort segments by start time to ensure chronological order
            sorted_segments = sorted(speaker_segments, key=lambda x: x.start_time)
            
            if not sorted_segments:
                return ""
            
            current_speaker = None
            current_text_parts = []
            
            for segment in sorted_segments:
                # Clean up the text in the segment itself before consolidation
                segment.text = self._filter_hallucinations(segment.text)

                # Check if speaker changed
                if segment.speaker_id != current_speaker:
                    # If we have accumulated text from previous speaker, add it
                    if current_speaker is not None and current_text_parts:
                        combined_text = " ".join(current_text_parts)
                        transcript_lines.append(f"{current_speaker}: {combined_text}")
                    
                    # Start new speaker section
                    current_speaker = segment.speaker_id
                    current_text_parts = [segment.text]
                else:
                    # Same speaker, accumulate text
                    current_text_parts.append(segment.text)
            
            # Add the final speaker section
            if current_speaker is not None and current_text_parts:
                combined_text = " ".join(current_text_parts)
                transcript_lines.append(f"{current_speaker}: {combined_text}")
            
            # Join all lines with newlines
            full_transcript = "\n".join(transcript_lines)
            
            logger.info(f"Created consolidated transcript with {len(transcript_lines)} speaker sections")
            
            return full_transcript
            
        except Exception as e:
            logger.error(f"Error creating consolidated transcript: {str(e)}")
            return "Error creating transcript"
    
    def _filter_hallucinations(self, text: str) -> str:
        """
        Filters Whisper hallucinations where a word is repeated many times.
        e.g. "yes, yes, yes, yes, yes" becomes "yes, yes, yes..."
        
        Args:
            text: The input text.
        
        Returns:
            Cleaned text.
        """
        import re
        # This regex splits the text into words and the delimiters (spaces, punctuation) that follow them.
        tokens = re.findall(r'(\w+)(\W*)', text)
        if not tokens:
            return text
        
        # Handle trailing text not captured by regex
        end_of_tokens_str = "".join([w+d for w,d in tokens])
        trailing_text = text[len(end_of_tokens_str):]

        processed_tokens = []
        i = 0
        while i < len(tokens):
            current_word, _ = tokens[i]
            
            # Look ahead for repetitions of the current word
            count = 1
            j = i + 1
            while j < len(tokens) and tokens[j][0].lower() == current_word.lower():
                count += 1
                j += 1
            
            if count > 3:  # More than 3 repetitions
                # Keep the first 3 occurrences
                processed_tokens.extend(tokens[i:i+3])
                
                # Get the last of the three to append "..."
                last_word, last_delim = processed_tokens.pop()
                
                # Append "..." smartly to the delimiter
                if last_delim.endswith(' '):
                    new_delim = last_delim.rstrip(' ') + '... '
                else:
                    new_delim = last_delim + '...'
                processed_tokens.append((last_word, new_delim))
                
                # Move index past the entire repeated sequence
                i = j
            else:
                # No hallucination, just add the token and move on
                processed_tokens.append(tokens[i])
                i += 1
                
        return "".join([word + delim for word, delim in processed_tokens]) + trailing_text
    
    def _generate_conversation_flow(self, speaker_segments: List[SpeakerSegment]) -> List[Dict[str, Any]]:
        """
        Generate a structured conversation flow for easier processing.
        
        Args:
            speaker_segments: List of SpeakerSegment objects
            
        Returns:
            List of dictionaries representing conversation turns
        """
        conversation_turns = []
        
        try:
            # Sort segments by start time
            sorted_segments = sorted(speaker_segments, key=lambda x: x.start_time)
            
            for i, segment in enumerate(sorted_segments):
                turn = {
                    'turn_id': i + 1,
                    'speaker_id': segment.speaker_id,
                    'start_time': segment.start_time,
                    'end_time': segment.end_time,
                    'duration': segment.end_time - segment.start_time,
                    'text': segment.text,
                    'confidence': segment.confidence,
                    'word_count': len(segment.text.split()),
                    'timestamp_formatted': self._format_timestamp(segment.start_time)
                }
                
                # Add turn transition info
                if i > 0:
                    prev_segment = sorted_segments[i - 1]
                    turn['gap_from_previous'] = segment.start_time - prev_segment.end_time
                    turn['speaker_changed'] = segment.speaker_id != prev_segment.speaker_id
                else:
                    turn['gap_from_previous'] = 0.0
                    turn['speaker_changed'] = True
                
                conversation_turns.append(turn)
            
            logger.info(f"Generated conversation flow with {len(conversation_turns)} turns")
            
            return conversation_turns
            
        except Exception as e:
            logger.error(f"Error generating conversation flow: {str(e)}")
            return []
    
    def _create_speaker_summary(self, speaker_segments: List[SpeakerSegment]) -> Dict[str, Any]:
        """
        Create summary statistics for each speaker.
        
        Args:
            speaker_segments: List of SpeakerSegment objects
            
        Returns:
            Dict with speaker statistics
        """
        speaker_stats = {}
        total_conversation_time = 0.0
        
        try:
            if speaker_segments:
                total_conversation_time = max(seg.end_time for seg in speaker_segments)
            
            for segment in speaker_segments:
                speaker_id = segment.speaker_id
                
                if speaker_id not in speaker_stats:
                    speaker_stats[speaker_id] = {
                        'segment_count': 0,
                        'total_speaking_time': 0.0,
                        'total_words': 0,
                        'avg_confidence': 0.0,
                        'confidences': [],
                        'longest_segment': 0.0,
                        'shortest_segment': float('inf'),
                        'speaking_percentage': 0.0
                    }
                
                duration = segment.end_time - segment.start_time
                word_count = len(segment.text.split())
                
                speaker_stats[speaker_id]['segment_count'] += 1
                speaker_stats[speaker_id]['total_speaking_time'] += duration
                speaker_stats[speaker_id]['total_words'] += word_count
                speaker_stats[speaker_id]['longest_segment'] = max(
                    speaker_stats[speaker_id]['longest_segment'], duration
                )
                speaker_stats[speaker_id]['shortest_segment'] = min(
                    speaker_stats[speaker_id]['shortest_segment'], duration
                )
                
                if segment.confidence is not None:
                    speaker_stats[speaker_id]['confidences'].append(segment.confidence)
            
            # Calculate final statistics
            for speaker_id in speaker_stats:
                stats = speaker_stats[speaker_id]
                
                # Calculate average confidence
                if stats['confidences']:
                    stats['avg_confidence'] = sum(stats['confidences']) / len(stats['confidences'])
                del stats['confidences']  # Remove raw data
                
                # Calculate speaking percentage
                if total_conversation_time > 0:
                    stats['speaking_percentage'] = (stats['total_speaking_time'] / total_conversation_time) * 100
                
                # Handle edge case for shortest segment
                if stats['shortest_segment'] == float('inf'):
                    stats['shortest_segment'] = 0.0
                
                # Add formatted times
                stats['total_speaking_time_formatted'] = self._format_duration(stats['total_speaking_time'])
                stats['avg_segment_duration'] = stats['total_speaking_time'] / max(stats['segment_count'], 1)
            
            logger.info(f"Created speaker summary for {len(speaker_stats)} speakers")
            
            return speaker_stats
            
        except Exception as e:
            logger.error(f"Error creating speaker summary: {str(e)}")
            return {}
    
    def _create_timing_summary(self, speaker_segments: List[SpeakerSegment]) -> Dict[str, Any]:
        """
        Create timing summary for the entire conversation.
        
        Args:
            speaker_segments: List of SpeakerSegment objects
            
        Returns:
            Dict with timing statistics
        """
        try:
            if not speaker_segments:
                return {}
            
            # Sort by time
            sorted_segments = sorted(speaker_segments, key=lambda x: x.start_time)
            
            # Calculate timing metrics
            start_time = sorted_segments[0].start_time
            end_time = max(seg.end_time for seg in sorted_segments)
            total_duration = end_time - start_time
            
            # Calculate speaking vs silence time
            total_speaking_time = sum(seg.end_time - seg.start_time for seg in sorted_segments)
            silence_time = total_duration - total_speaking_time
            
            # Calculate gaps between segments
            gaps = []
            for i in range(1, len(sorted_segments)):
                gap = sorted_segments[i].start_time - sorted_segments[i-1].end_time
                if gap > 0:
                    gaps.append(gap)
            
            # Speaker turn statistics
            speaker_changes = 0
            for i in range(1, len(sorted_segments)):
                if sorted_segments[i].speaker_id != sorted_segments[i-1].speaker_id:
                    speaker_changes += 1
            
            timing_summary = {
                'total_duration': total_duration,
                'total_speaking_time': total_speaking_time,
                'total_silence_time': silence_time,
                'speaking_percentage': (total_speaking_time / total_duration * 100) if total_duration > 0 else 0,
                'silence_percentage': (silence_time / total_duration * 100) if total_duration > 0 else 0,
                'average_gap': sum(gaps) / len(gaps) if gaps else 0.0,
                'max_gap': max(gaps) if gaps else 0.0,
                'total_gaps': len(gaps),
                'speaker_changes': speaker_changes,
                'segments_per_minute': (len(sorted_segments) / (total_duration / 60)) if total_duration > 0 else 0,
                
                # Formatted versions
                'total_duration_formatted': self._format_duration(total_duration),
                'total_speaking_time_formatted': self._format_duration(total_speaking_time),
                'total_silence_time_formatted': self._format_duration(silence_time)
            }
            
            logger.info(f"Created timing summary: {timing_summary['total_duration_formatted']} total, {timing_summary['speaking_percentage']:.1f}% speaking")
            
            return timing_summary
            
        except Exception as e:
            logger.error(f"Error creating timing summary: {str(e)}")
            return {}
    
    def _calculate_overall_confidence(self, speaker_segments: List[SpeakerSegment]) -> float:
        """
        Calculate overall confidence score weighted by segment duration.
        
        Args:
            speaker_segments: List of SpeakerSegment objects
            
        Returns:
            Float representing overall confidence (0.0 to 1.0)
        """
        try:
            if not speaker_segments:
                return 0.0
            
            total_weighted_confidence = 0.0
            total_duration = 0.0
            
            for segment in speaker_segments:
                if segment.confidence is not None:
                    duration = segment.end_time - segment.start_time
                    total_weighted_confidence += segment.confidence * duration
                    total_duration += duration
            
            overall_confidence = total_weighted_confidence / total_duration if total_duration > 0 else 0.0
            
            return min(max(overall_confidence, 0.0), 1.0)  # Clamp to [0, 1]
            
        except Exception as e:
            logger.error(f"Error calculating overall confidence: {str(e)}")
            return 0.0
    
    def _format_timestamp(self, seconds: float) -> str:
        """
        Format timestamp in MM:SS.ss format.
        
        Args:
            seconds: Time in seconds
            
        Returns:
            Formatted timestamp string
        """
        try:
            minutes = int(seconds // 60)
            remaining_seconds = seconds % 60
            return self.timestamp_format.format(minutes, remaining_seconds)
        except:
            return "[00:00.00]"
    
    def _format_duration(self, seconds: float) -> str:
        """
        Format duration in human-readable format.
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            Formatted duration string (e.g., "2m 34.5s")
        """
        try:
            if seconds < 60:
                return f"{seconds:.1f}s"
            else:
                minutes = int(seconds // 60)
                remaining_seconds = seconds % 60
                return f"{minutes}m {remaining_seconds:.1f}s"
        except:
            return "0.0s"
    
    def export_transcript_formats(self, final_result: Dict[str, Any]) -> Dict[str, str]:
        """
        Export transcript in multiple formats.
        
        Args:
            final_result: Final result dictionary from create_final_transcript
            
        Returns:
            Dict with different format exports
        """
        try:
            formats = {}
            
            # Plain text format (current diarized transcript)
            formats['plain'] = final_result.get('text', '')
            
            # JSON format for API consumption
            formats['json'] = {
                'conversation': final_result.get('conversation_flow', []),
                'summary': final_result.get('speaker_summary', {}),
                'timing': final_result.get('timing_summary', {}),
                'confidence': final_result.get('confidence', 0.0)
            }
            
            # SRT subtitle format
            formats['srt'] = self._create_srt_format(final_result.get('conversation_flow', []))
            
            # Simple conversation format
            formats['conversation'] = self._create_conversation_format(final_result.get('conversation_flow', []))
            
            logger.info(f"Exported transcript in {len(formats)} formats")
            
            return formats
            
        except Exception as e:
            logger.error(f"Error exporting transcript formats: {str(e)}")
            return {'plain': final_result.get('text', '')}
    
    def _create_srt_format(self, conversation_flow: List[Dict[str, Any]]) -> str:
        """Create SRT subtitle format."""
        srt_lines = []
        
        for i, turn in enumerate(conversation_flow, 1):
            start_time = self._seconds_to_srt_time(turn['start_time'])
            end_time = self._seconds_to_srt_time(turn['end_time'])
            
            srt_lines.append(f"{i}")
            srt_lines.append(f"{start_time} --> {end_time}")
            srt_lines.append(f"{turn['speaker_id']}: {turn['text']}")
            srt_lines.append("")  # Empty line between subtitles
        
        return "\n".join(srt_lines)
    
    def _create_conversation_format(self, conversation_flow: List[Dict[str, Any]]) -> str:
        """Create simple conversation format."""
        conversation_lines = []
        
        for turn in conversation_flow:
            conversation_lines.append(f"{turn['speaker_id']}: {turn['text']}")
        
        return "\n".join(conversation_lines)
    
    def _seconds_to_srt_time(self, seconds: float) -> str:
        """Convert seconds to SRT time format (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
    
    def cleanup(self):
        """Clean up resources (placeholder for future use)."""
        logger.info("TranscriptionPostProcessor cleanup completed")
    
    def __del__(self):
        """Cleanup on object destruction."""
        self.cleanup()