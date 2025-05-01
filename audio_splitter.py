import os
import logging
from pydub import AudioSegment

logger = logging.getLogger(__name__)

def get_audio_format(filename):
    """
    Returns the format of the audio file based on its extension.
    Ensures compatibility with common audio formats.
    """
    ext = os.path.splitext(filename)[1][1:].lower()
    # Map m4a to mp4 for ffmpeg compatibility
    if ext == 'm4a':
        return 'mp4'
    return ext

def split_audio_file(input_file, output_dir, segment_size, split_type='seconds'):
    """
    Split an audio file into segments of specified size.
    Optimized for performance with larger files.
    
    Args:
        input_file (str): Path to the input audio file
        output_dir (str): Directory to save the split segments
        segment_size (int): Size of each segment
        split_type (str): Type of splitting - 'seconds', 'megabytes'
        
    Returns:
        list: List of output filenames
    """
    try:
        # Make sure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Get the file format
        file_format = get_audio_format(input_file)
        
        # Load the audio file
        logger.info(f"Loading audio file: {input_file}")
        audio = AudioSegment.from_file(input_file, format=file_format)
        
        # Get total duration in milliseconds
        total_duration = len(audio)
        logger.info(f"Total duration: {total_duration}ms")
        
        # Calculate segment size in milliseconds - with improved calculations
        if split_type == 'seconds':
            # Simple time-based splitting
            segment_ms = segment_size * 1000
        elif split_type == 'megabytes':
            # More accurate calculation for megabyte-based splitting
            # This takes into account compression differences in different parts of audio
            file_size = os.path.getsize(input_file)
            file_size_mb = file_size / (1024 * 1024)
            
            # Calculate approximate ratio of duration to file size
            # This ensures more uniform segments by size
            duration_per_mb = total_duration / file_size_mb
            target_duration = duration_per_mb * segment_size
            
            # Apply some safety margin to avoid overflowing target size
            segment_ms = int(target_duration * 0.95)
            
            # Ensure minimum segment size
            segment_ms = max(segment_ms, 5000)  # At least 5 seconds per segment
        else:
            # Fallback - use seconds
            segment_ms = segment_size * 1000
        
        # Calculate number of segments
        num_segments = max(1, int(total_duration / segment_ms))
        
        # Split the audio
        output_files = []
        
        base_filename = os.path.basename(input_file)
        base_name, _ = os.path.splitext(base_filename)
        
        for i in range(num_segments):
            # Calculate start and end times for this segment
            start_ms = i * segment_ms
            end_ms = min((i + 1) * segment_ms, total_duration)
            
            # Extract segment
            segment = audio[start_ms:end_ms]
            
            # Generate output filename - always use mp3 for consistency
            output_filename = f"{base_name}_part{i+1}.mp3"
            output_path = os.path.join(output_dir, output_filename)
            
            # Export segment as MP3 for better compatibility 
            logger.info(f"Exporting segment {i+1}/{num_segments} to {output_path}")
            # Add bitrate parameter for faster processing and smaller file size
            segment.export(output_path, format="mp3", bitrate="128k", codec="libmp3lame")
            
            output_files.append(output_filename)
        
        logger.info(f"Successfully split audio into {len(output_files)} segments")
        return output_files
    
    except Exception as e:
        logger.error(f"Error splitting audio file: {str(e)}")
        raise
