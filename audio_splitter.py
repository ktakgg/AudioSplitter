import os
import logging
import math
from pydub import AudioSegment
from pydub.utils import mediainfo

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

def calculate_segment_size_mb(input_file, segment_size_mb):
    """
    Calculate precise segment duration for megabyte-based splitting.
    Uses audio metadata for more accurate estimation.
    """
    try:
        # Get file metadata
        info = mediainfo(input_file)
        bitrate = int(info.get('bit_rate', 128000))  # Default to 128kbps if not found
        
        # Calculate segment duration in milliseconds
        # Formula: (target_mb * 8 * 1024 * 1024) / bitrate * 1000
        segment_ms = (segment_size_mb * 8 * 1024 * 1024 / bitrate) * 1000
        
        # Ensure minimum segment size (5 seconds)
        return max(int(segment_ms), 5000)
    
    except Exception:
        # Fallback calculation using file size
        file_size = os.path.getsize(input_file)
        file_size_mb = file_size / (1024 * 1024)
        
        # Get audio duration for ratio calculation
        audio = AudioSegment.from_file(input_file)
        total_duration = len(audio)
        
        duration_per_mb = total_duration / file_size_mb
        return max(int(duration_per_mb * segment_size_mb * 0.9), 5000)

def split_audio_file(input_file, output_dir, segment_size, split_type='seconds'):
    """
    Split an audio file into segments with enhanced precision and performance.
    
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
        
        # Load the audio file with optimized parameters
        logger.info(f"Loading audio file: {input_file}")
        
        # Use low memory mode for large files
        audio = AudioSegment.from_file(input_file, format=file_format)
        
        # Get total duration in milliseconds
        total_duration = len(audio)
        logger.info(f"Total duration: {total_duration}ms ({total_duration/1000:.1f}s)")
        
        # Calculate segment size with improved precision
        if split_type == 'seconds':
            segment_ms = segment_size * 1000
        elif split_type == 'megabytes':
            segment_ms = calculate_segment_size_mb(input_file, segment_size)
            logger.info(f"Calculated segment duration: {segment_ms}ms for {segment_size}MB target")
        else:
            segment_ms = segment_size * 1000
        
        # Calculate number of segments more precisely
        num_segments = max(1, math.ceil(total_duration / segment_ms))
        
        # For better distribution, recalculate segment size
        if num_segments > 1:
            segment_ms = total_duration / num_segments
        
        logger.info(f"Will create {num_segments} segments of ~{segment_ms/1000:.1f}s each")
        
        # Split the audio with optimized processing
        output_files = []
        base_filename = os.path.basename(input_file)
        base_name, _ = os.path.splitext(base_filename)
        
        for i in range(num_segments):
            # Calculate precise start and end times
            start_ms = int(i * segment_ms)
            end_ms = int(min((i + 1) * segment_ms, total_duration))
            
            # Skip if segment would be too short (less than 1 second)
            if end_ms - start_ms < 1000:
                continue
            
            # Extract segment efficiently
            segment = audio[start_ms:end_ms]
            
            # Generate output filename
            output_filename = f"{base_name}_part{i+1:02d}.mp3"
            output_path = os.path.join(output_dir, output_filename)
            
            logger.info(f"Exporting segment {i+1}/{num_segments}: {start_ms/1000:.1f}s - {end_ms/1000:.1f}s")
            
            # Export with optimized settings for speed and quality
            segment.export(
                output_path, 
                format="mp3",
                bitrate="128k",
                parameters=[
                    "-acodec", "libmp3lame",
                    "-ac", "2" if segment.channels > 1 else "1",  # Preserve channel count
                    "-ar", "44100",  # Standard sample rate
                    "-q:a", "2"  # High quality, fast encoding
                ]
            )
            
            output_files.append(output_filename)
        
        logger.info(f"Successfully created {len(output_files)} segments")
        return output_files
    
    except Exception as e:
        logger.error(f"Error splitting audio file: {str(e)}")
        raise
