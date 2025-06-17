import os
import logging
import math
import subprocess
import tempfile

logger = logging.getLogger(__name__)

def get_audio_duration(input_file):
    """Get audio duration using ffprobe."""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
            '-of', 'csv=p=0', input_file
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"Failed to get duration with ffprobe: {e}")
    return None

def split_audio_file_ffmpeg(input_file, output_dir, segment_size, split_type='seconds'):
    """
    Split audio file using ffmpeg directly for better performance and reliability.
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        
        # Get file size for optimization decisions
        file_size_mb = os.path.getsize(input_file) / (1024 * 1024)
        logger.info(f"Processing file: {file_size_mb:.1f}MB")
        
        # Get audio duration
        duration = get_audio_duration(input_file)
        if not duration:
            logger.error("Could not determine audio duration")
            return []
        
        logger.info(f"Audio duration: {duration:.1f} seconds")
        
        # Calculate segment duration
        if split_type == 'seconds':
            segment_duration = segment_size
        else:  # megabytes
            # Rough estimation: assume average bitrate
            estimated_bitrate = (file_size_mb * 8) / duration  # Mbps
            segment_duration = (segment_size * 8) / estimated_bitrate if estimated_bitrate > 0 else 60
        
        # Limit segments for large files to prevent timeout
        max_segments = 6 if file_size_mb > 30 else 20
        num_segments = min(max_segments, math.ceil(duration / segment_duration))
        segment_duration = duration / num_segments
        
        logger.info(f"Creating {num_segments} segments of {segment_duration:.1f}s each")
        
        # Generate output filenames
        base_filename = os.path.basename(input_file)
        base_name, _ = os.path.splitext(base_filename)
        # Sanitize filename
        import re
        base_name = re.sub(r'[^\w\-_.]', '_', base_name)
        
        output_files = []
        
        # Use WAV format for large files to ensure speed
        output_format = 'wav' if file_size_mb > 30 else 'mp3'
        logger.info(f"Using {output_format.upper()} format for output")
        
        for i in range(num_segments):
            start_time = i * segment_duration
            
            # Generate output filename
            output_filename = f"{base_name}_part{i+1:02d}.{output_format}"
            output_path = os.path.join(output_dir, output_filename)
            
            logger.info(f"Creating segment {i+1}/{num_segments}: {start_time:.1f}s - {start_time + segment_duration:.1f}s")
            
            # Build ffmpeg command
            if output_format == 'wav':
                cmd = [
                    'ffmpeg', '-y', '-i', input_file,
                    '-ss', str(start_time),
                    '-t', str(segment_duration),
                    '-c:a', 'pcm_s16le',  # Fast WAV encoding
                    '-ac', '1',  # Mono for speed
                    '-ar', '16000',  # Lower sample rate
                    output_path
                ]
            else:
                cmd = [
                    'ffmpeg', '-y', '-i', input_file,
                    '-ss', str(start_time),
                    '-t', str(segment_duration),
                    '-c:a', 'libmp3lame',
                    '-b:a', '128k',
                    '-ac', '2',
                    output_path
                ]
            
            try:
                # Run ffmpeg with timeout
                result = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True, 
                    timeout=60,  # 1 minute timeout per segment
                    cwd=output_dir
                )
                
                if result.returncode == 0 and os.path.exists(output_path):
                    output_files.append(output_filename)
                    logger.info(f"Successfully created segment {i+1}")
                else:
                    logger.error(f"ffmpeg failed for segment {i+1}: {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                logger.error(f"Timeout creating segment {i+1}")
                continue
            except Exception as e:
                logger.error(f"Error creating segment {i+1}: {e}")
                continue
        
        logger.info(f"Successfully created {len(output_files)} segments")
        return output_files
        
    except Exception as e:
        logger.error(f"Error in ffmpeg audio splitting: {e}")
        raise Exception(f"Audio processing failed: {str(e)}")

def split_audio_file(input_file, output_dir, segment_size, split_type='seconds'):
    """
    Main split function that uses ffmpeg for better performance.
    """
    file_size_mb = os.path.getsize(input_file) / (1024 * 1024)
    
    # For large files, always use ffmpeg approach
    if file_size_mb > 25:
        logger.info("Using ffmpeg direct splitting for large file")
        return split_audio_file_ffmpeg(input_file, output_dir, segment_size, split_type)
    
    # For smaller files, use the original pydub approach
    logger.info("Using pydub splitting for small file")
    try:
        from pydub import AudioSegment
        
        # Load and process with pydub
        audio = AudioSegment.from_file(input_file)
        total_duration = len(audio)
        
        if split_type == 'seconds':
            segment_ms = segment_size * 1000
        else:
            # Simple estimation for megabytes
            segment_ms = (segment_size * total_duration) // (file_size_mb)
        
        num_segments = max(1, math.ceil(total_duration / segment_ms))
        if num_segments > 1:
            segment_ms = total_duration / num_segments
        
        output_files = []
        base_filename = os.path.basename(input_file)
        base_name, _ = os.path.splitext(base_filename)
        
        import re
        base_name = re.sub(r'[^\w\-_.]', '_', base_name)
        
        for i in range(num_segments):
            start_ms = int(i * segment_ms)
            end_ms = int(min((i + 1) * segment_ms, total_duration))
            
            if end_ms - start_ms < 1000:
                continue
            
            segment = audio[start_ms:end_ms]
            output_filename = f"{base_name}_part{i+1:02d}.mp3"
            output_path = os.path.join(output_dir, output_filename)
            
            try:
                segment.export(output_path, format="mp3", bitrate="128k")
                output_files.append(output_filename)
            except Exception as e:
                logger.error(f"Failed to export segment {i+1}: {e}")
                continue
        
        return output_files
        
    except Exception as e:
        logger.error(f"Pydub splitting failed: {e}")
        # Fallback to ffmpeg
        return split_audio_file_ffmpeg(input_file, output_dir, segment_size, split_type)