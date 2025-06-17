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
    # Format mapping for better ffmpeg compatibility
    format_map = {
        'm4a': 'mp4',
        'aac': 'mp4',
        'wma': 'asf'
    }
    return format_map.get(ext, ext)

def calculate_segment_size_mb(input_file, segment_size_mb):
    """
    Calculate precise segment duration for megabyte-based splitting.
    Uses audio metadata for more accurate estimation.
    """
    try:
        # Get file metadata with better error handling
        info = mediainfo(input_file)
        
        # Handle various bitrate formats
        bitrate_str = info.get('bit_rate', '128000')
        if isinstance(bitrate_str, str):
            # Remove any non-numeric characters except decimal point
            import re
            bitrate_str = re.sub(r'[^\d.]', '', bitrate_str)
            try:
                bitrate = int(float(bitrate_str))
            except (ValueError, TypeError):
                bitrate = 128000
        else:
            bitrate = int(bitrate_str) if bitrate_str else 128000
        
        # Calculate segment duration in milliseconds
        # Formula: (target_mb * 8 * 1024 * 1024) / bitrate * 1000
        segment_ms = (segment_size_mb * 8 * 1024 * 1024 / bitrate) * 1000
        
        # Ensure minimum segment size (5 seconds)
        return max(int(segment_ms), 5000)
    
    except Exception as e:
        logger.warning(f"Error calculating segment size from metadata: {e}")
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
        
        # Use streaming mode for large files to reduce memory usage
        try:
            # For large files, use lower quality settings to speed up processing
            audio = AudioSegment.from_file(input_file, format=file_format)
            
            # If file is very large (>100MB), reduce quality for faster processing
            file_size_mb = os.path.getsize(input_file) / (1024 * 1024)
            if file_size_mb > 100:
                logger.info(f"Large file detected ({file_size_mb:.1f}MB), using optimized processing")
                # Convert to mono and lower sample rate for faster processing
                if audio.channels > 1:
                    audio = audio.set_channels(1)
                if audio.frame_rate > 22050:
                    audio = audio.set_frame_rate(22050)
        except Exception as e:
            logger.warning(f"Failed to load with format {file_format}, trying automatic detection: {e}")
            audio = AudioSegment.from_file(input_file)
            # Apply same optimizations for auto-detected files
            file_size_mb = os.path.getsize(input_file) / (1024 * 1024)
            if file_size_mb > 100:
                if audio.channels > 1:
                    audio = audio.set_channels(1)
                if audio.frame_rate > 22050:
                    audio = audio.set_frame_rate(22050)
        
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
        
        # Sanitize base name to avoid any pattern matching issues
        import re
        base_name = re.sub(r'[^\w\-_.]', '_', base_name)
        
        # Process segments with optimized settings
        for i in range(num_segments):
            # Calculate precise start and end times
            start_ms = int(i * segment_ms)
            end_ms = int(min((i + 1) * segment_ms, total_duration))
            
            # Skip if segment would be too short (less than 1 second)
            if end_ms - start_ms < 1000:
                continue
            
            logger.info(f"Processing segment {i+1}/{num_segments}: {start_ms/1000:.1f}s - {end_ms/1000:.1f}s")
            
            try:
                # Extract segment efficiently
                segment = audio[start_ms:end_ms]
                
                # For very large segments, apply compression to speed up processing
                if len(segment) > 300000:  # 5 minutes
                    if segment.channels > 1:
                        segment = segment.set_channels(1)
                    if segment.frame_rate > 22050:
                        segment = segment.set_frame_rate(22050)
                
                # Generate output filename
                output_filename = f"{base_name}_part{i+1:02d}.mp3"
                output_path = os.path.join(output_dir, output_filename)
                
                # Export with optimized settings for speed and reliability
                export_success = False
                
                # Use faster encoding for large files
                if file_size_mb > 50:
                    # Fast encoding settings for large files
                    export_attempts = [
                    # Attempt 1: Fast MP3 encoding
                    lambda: segment.export(
                        output_path, 
                        format="mp3",
                        bitrate="96k",
                        parameters=[
                            "-acodec", "libmp3lame",
                            "-ac", "1",  # Force mono for speed
                            "-ar", "22050",  # Lower sample rate
                            "-compression_level", "1"  # Fast compression
                        ]
                    ),
                    # Attempt 2: Very basic MP3
                    lambda: segment.export(output_path, format="mp3", bitrate="96k"),
                    # Attempt 3: WAV fallback (fastest)
                    lambda: segment.export(output_path.replace('.mp3', '.wav'), format="wav")
                ]
            else:
                # Standard quality for smaller files
                export_attempts = [
                    # Attempt 1: Standard MP3
                    lambda: segment.export(
                        output_path, 
                        format="mp3",
                        bitrate="128k",
                        parameters=["-acodec", "libmp3lame", "-q:a", "4"]
                    ),
                    # Attempt 2: Basic MP3
                    lambda: segment.export(output_path, format="mp3", bitrate="128k"),
                    # Attempt 3: WAV fallback
                    lambda: segment.export(output_path.replace('.mp3', '.wav'), format="wav")
                ]
            
            for attempt_num, export_func in enumerate(export_attempts, 1):
                try:
                    export_func()
                    export_success = True
                    # Update filename if we used WAV fallback
                    if attempt_num == 5:
                        output_filename = output_filename.replace('.mp3', '.wav')
                    break
                except Exception as export_error:
                    logger.warning(f"Export attempt {attempt_num} failed: {export_error}")
                    if attempt_num == len(export_attempts):
                        raise Exception(f"All export attempts failed. Last error: {export_error}")
            
            if not export_success:
                raise Exception("Failed to export audio segment after all attempts")
            
            output_files.append(output_filename)
        
        logger.info(f"Successfully created {len(output_files)} segments")
        return output_files
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error splitting audio file: {error_msg}")
        
        # Provide more specific error information
        if "string did not match the expected pattern" in error_msg.lower():
            logger.error("Pattern matching error detected - likely ffmpeg parameter issue")
            raise Exception("Audio processing failed due to format compatibility issue. Please try with a different audio file or contact support.")
        elif "no such file or directory" in error_msg.lower():
            raise Exception("Audio file not found or cannot be accessed.")
        elif "permission denied" in error_msg.lower():
            raise Exception("Permission denied while processing audio file.")
        else:
            raise Exception(f"Audio processing failed: {error_msg}")
