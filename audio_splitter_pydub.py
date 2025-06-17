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
        
        # Get the file format and size
        file_format = get_audio_format(input_file)
        file_size_mb = os.path.getsize(input_file) / (1024 * 1024)
        
        # Load the audio file with optimized parameters
        logger.info(f"Loading audio file: {input_file}")
        
        # Use streaming mode for large files to reduce memory usage
        try:
            audio = AudioSegment.from_file(input_file, format=file_format)
            
            # Aggressive optimization for large files to prevent timeouts
            if file_size_mb > 30:
                logger.info(f"Large file detected ({file_size_mb:.1f}MB), applying aggressive optimization")
                # Convert to mono for faster processing
                if audio.channels > 1:
                    audio = audio.set_channels(1)
                    logger.info("Converted to mono for faster processing")
                # Reduce sample rate significantly
                if audio.frame_rate > 16000:
                    audio = audio.set_frame_rate(16000)
                    logger.info("Reduced sample rate to 16kHz for faster processing")
        except Exception as e:
            logger.warning(f"Failed to load with format {file_format}, trying automatic detection: {e}")
            audio = AudioSegment.from_file(input_file)
            # Apply same optimizations for auto-detected files
            if file_size_mb > 30:
                if audio.channels > 1:
                    audio = audio.set_channels(1)
                if audio.frame_rate > 16000:
                    audio = audio.set_frame_rate(16000)
        
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
        
        # For very large files, limit the number of segments to prevent timeout
        if file_size_mb > 30 and num_segments > 6:
            num_segments = 6
            segment_ms = total_duration / num_segments
            logger.info(f"Limited to {num_segments} segments for large file to prevent timeout")
        
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
                
                # Generate output filename
                output_filename = f"{base_name}_part{i+1:02d}.mp3"
                output_path = os.path.join(output_dir, output_filename)
                
                # Export with fast, reliable settings
                export_success = False
                export_error_details = []
                
                # Use extremely fast encoding for large files to prevent timeouts
                if file_size_mb > 30:
                    # Ultra-fast encoding for large files - prioritize speed over quality
                    export_attempts = [
                        ("WAV fast", lambda: segment.export(output_path.replace('.mp3', '.wav'), format="wav")),
                        ("MP3 ultra-fast", lambda: segment.export(
                            output_path, 
                            format="mp3", 
                            bitrate="64k",
                            parameters=["-preset", "ultrafast", "-ac", "1", "-ar", "16000"]
                        ))
                    ]
                    # Update filename for WAV
                    if not output_filename.endswith('.wav'):
                        output_filename = output_filename.replace('.mp3', '.wav')
                        output_path = output_path.replace('.mp3', '.wav')
                else:
                    # Standard quality for smaller files
                    export_attempts = [
                        ("MP3 standard", lambda: segment.export(output_path, format="mp3", bitrate="128k")),
                        ("WAV fallback", lambda: segment.export(output_path.replace('.mp3', '.wav'), format="wav"))
                    ]
                
                for attempt_name, export_func in export_attempts:
                    try:
                        logger.info(f"Attempting {attempt_name} export for segment {i+1}")
                        export_func()
                        if attempt_name == "WAV fallback":
                            output_filename = output_filename.replace('.mp3', '.wav')
                        export_success = True
                        logger.info(f"Successfully exported segment {i+1} using {attempt_name}")
                        break
                    except Exception as e:
                        error_detail = f"{attempt_name}: {str(e)}"
                        export_error_details.append(error_detail)
                        logger.warning(f"Export attempt {attempt_name} failed: {e}")
                        
                        # Check for specific pattern matching error
                        if "string did not match the expected pattern" in str(e).lower():
                            logger.error(f"Pattern matching error in {attempt_name}: {e}")
                
                if not export_success:
                    error_msg = f"All export attempts failed for segment {i+1}: " + "; ".join(export_error_details)
                    logger.error(error_msg)
                    continue
                
                if export_success:
                    output_files.append(output_filename)
                
            except Exception as e:
                logger.error(f"Error processing segment {i+1}: {e}")
                continue
        
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