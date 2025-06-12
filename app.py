import os
import logging
import uuid
from flask import Flask, render_template, request, jsonify, send_from_directory, url_for, flash, redirect, session
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
import tempfile
import shutil
from audio_splitter import split_audio_file

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev_secret_key")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configuration
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'audio_uploads')
OUTPUT_FOLDER = os.path.join(tempfile.gettempdir(), 'audio_splits')
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac', 'wma'}
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max file size

# Optimized configuration for better performance
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable caching for development
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Create upload and output directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Helper function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': f'Unsupported file format. Allowed formats: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
    
    try:
        # Create unique session ID for this upload
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
        
        # Create session directory
        session_upload_dir = os.path.join(UPLOAD_FOLDER, session_id)
        session_output_dir = os.path.join(OUTPUT_FOLDER, session_id)
        os.makedirs(session_upload_dir, exist_ok=True)
        os.makedirs(session_output_dir, exist_ok=True)
        
        # Save the file
        if not file.filename:
            return jsonify({'error': 'Invalid file name'}), 400
        filename = secure_filename(file.filename)
        filepath = os.path.join(session_upload_dir, filename)
        file.save(filepath)
        
        # Store filename in session
        session['original_filename'] = filename
        session['filepath'] = filepath
        session['output_dir'] = session_output_dir
        
        return jsonify({
            'success': True,
            'filename': filename,
            'session_id': session_id
        })
    
    except Exception as e:
        logger.error(f"Error during file upload: {str(e)}")
        return jsonify({'error': f'Error uploading file: {str(e)}'}), 500

@app.route('/split', methods=['POST'])
def split_file():
    if 'filepath' not in session or 'output_dir' not in session:
        return jsonify({'error': 'No file uploaded'}), 400
    
    try:
        # Get parameters from the form
        segment_size = request.form.get('segment_size', type=int)
        split_type = request.form.get('split_type', 'seconds')
        
        # Enhanced validation
        if not segment_size or segment_size <= 0:
            return jsonify({'error': 'Invalid segment size'}), 400
        
        if split_type == 'megabytes' and segment_size > 50:
            return jsonify({'error': 'Segment size too large. Maximum 50MB per segment.'}), 400
        
        if split_type == 'seconds' and segment_size > 3600:
            return jsonify({'error': 'Segment size too large. Maximum 1 hour per segment.'}), 400
        
        # Process the audio file
        filepath = session['filepath']
        output_dir = session['output_dir']
        original_filename = session['original_filename']
        
        logger.info(f"Starting split process: {original_filename}, {segment_size} {split_type}")
        
        # Split the audio file with enhanced error handling
        output_files = split_audio_file(
            filepath, 
            output_dir, 
            segment_size, 
            split_type
        )
        
        if not output_files:
            return jsonify({'error': 'No segments were created. File may be too short.'}), 400
        
        # Store output files in session
        session['output_files'] = output_files
        
        # Calculate total output size for user information
        total_size = 0
        for filename in output_files:
            file_path = os.path.join(output_dir, filename)
            if os.path.exists(file_path):
                total_size += os.path.getsize(file_path)
        
        total_size_mb = total_size / (1024 * 1024)
        
        logger.info(f"Successfully created {len(output_files)} segments, total size: {total_size_mb:.1f}MB")
        
        # Return success response with detailed information
        return jsonify({
            'success': True,
            'message': f'Successfully split into {len(output_files)} segments',
            'files': output_files,
            'total_size_mb': round(total_size_mb, 2),
            'segment_count': len(output_files)
        })
    
    except Exception as e:
        logger.error(f"Error during file splitting: {str(e)}")
        error_msg = str(e)
        if "timeout" in error_msg.lower() or "worker timeout" in error_msg.lower():
            error_msg = "File processing took too long. Try splitting into smaller segments or use a smaller file."
        return jsonify({'error': f'Processing failed: {error_msg}'}), 500

@app.route('/download/<path:filename>', methods=['GET'])
def download_file(filename):
    if 'output_dir' not in session:
        return "No files available for download", 400
    
    try:
        return send_from_directory(
            session['output_dir'],
            filename,
            as_attachment=True
        )
    except Exception as e:
        logger.error(f"Error during file download: {str(e)}")
        return f"Error downloading file: {str(e)}", 500

@app.route('/download-all', methods=['GET'])
def download_all():
    if 'output_files' not in session or 'session_id' not in session:
        return "No files available for download", 400
    
    try:
        # Create a zip file with all segments
        zip_path = os.path.join(OUTPUT_FOLDER, f"{session['session_id']}_all_segments.zip")
        output_dir = session['output_dir']
        
        shutil.make_archive(
            zip_path.replace('.zip', ''),
            'zip',
            output_dir
        )
        
        return send_from_directory(
            OUTPUT_FOLDER,
            f"{session['session_id']}_all_segments.zip",
            as_attachment=True
        )
    except Exception as e:
        logger.error(f"Error during zip file download: {str(e)}")
        return f"Error creating zip file: {str(e)}", 500

@app.route('/cleanup', methods=['POST'])
def cleanup():
    # Clean up temp files when user is done
    if 'session_id' in session:
        session_id = session['session_id']
        upload_dir = os.path.join(UPLOAD_FOLDER, session_id)
        output_dir = os.path.join(OUTPUT_FOLDER, session_id)
        
        try:
            if os.path.exists(upload_dir):
                shutil.rmtree(upload_dir)
            if os.path.exists(output_dir):
                shutil.rmtree(output_dir)
                
            # Clear session
            session.clear()
            return jsonify({'success': True})
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            return jsonify({'error': f'Error cleaning up: {str(e)}'}), 500
    
    return jsonify({'success': True})

# Error handlers
@app.errorhandler(413)
def request_entity_too_large(error):
    flash(f'File too large. Maximum size is {MAX_CONTENT_LENGTH // (1024 * 1024)}MB')
    return redirect(url_for('index'))

@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
