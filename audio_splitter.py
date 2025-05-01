import os
import logging
from pydub import AudioSegment

logger = logging.getLogger(__name__)

def get_audio_format(filename):
    """
    Returns the format of the audio file based on its extension.
    """
    return os.path.splitext(filename)[1][1:].lower()

def split_audio_file(input_file, output_dir, segment_size, split_type='seconds'):
    """
    Split an audio file into segments of specified size.
    
    Args:
        input_file (str): Path to the input audio file
        output_dir (str): Directory to save the split segments
        segment_size (int): Size of each segment
        split_type (str): Type of splitting - 'seconds' or 'bytes'
        
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
        
        # Calculate segment size in milliseconds
        if split_type == 'seconds':
            segment_ms = segment_size * 1000
        elif split_type == 'megabytes':
            # If split by megabytes, estimate milliseconds per segment
            # This is a rough approximation based on file size and duration
            file_size = os.path.getsize(input_file)
            ms_per_mb = total_duration / (file_size / (1024 * 1024))
            segment_ms = segment_size * ms_per_mb
        else:
            # Fallback (bytes)
            file_size = os.path.getsize(input_file)
            ms_per_byte = total_duration / file_size
            segment_ms = segment_size * ms_per_byte
        
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
            
            # Generate output filename
            output_filename = f"{base_name}_part{i+1}.{file_format}"
            output_path = os.path.join(output_dir, output_filename)
            
            # Export segment
            logger.info(f"Exporting segment {i+1}/{num_segments} to {output_path}")
            segment.export(output_path, format=file_format)
            
            output_files.append(output_filename)
        
        logger.info(f"Successfully split audio into {len(output_files)} segments")
        return output_files
    
    except Exception as e:
        logger.error(f"Error splitting audio file: {str(e)}")
        raise
