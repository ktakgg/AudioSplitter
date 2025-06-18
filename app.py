import os
import logging
import uuid
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, send_from_directory, url_for, flash, redirect, session, send_file
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
import tempfile
import shutil
from audio_splitter import split_audio_file

# Import improved modules
from database import db
from security import validate_audio_file, generate_secure_session_id, validate_segment_parameters

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev_secret_key")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)  # セッション有効期限30分
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Database configuration
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL environment variable is not set")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Configuration - Use persistent storage instead of temp directories
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
OUTPUT_FOLDER = os.path.join(os.getcwd(), 'splits')
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac', 'wma'}

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Get max content length from environment or default to 200MB
# Use consistent 200MB limit for both development and deployment
MAX_CONTENT_LENGTH = int(os.environ.get('FLASK_MAX_CONTENT_LENGTH', 200 * 1024 * 1024))  # 200MB for all environments

# Flask configuration for deployment
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Initialize the app with the database extension
db.init_app(app)

# Create upload and output directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Create database tables
with app.app_context():
    # Import models after app is created
    import models
    db.create_all()

# Helper function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/config')
def get_config():
    """Return client configuration including file size limits"""
    return jsonify({
        'max_file_size': MAX_CONTENT_LENGTH,
        'max_file_size_mb': MAX_CONTENT_LENGTH // (1024 * 1024),
        'environment': os.environ.get('REPLIT_DEPLOYMENT', 'development'),
        'flask_config_max': app.config.get('MAX_CONTENT_LENGTH'),
        'env_flask_max': os.environ.get('FLASK_MAX_CONTENT_LENGTH'),
        'deployment_id': os.environ.get('REPL_ID', 'local')
    })

@app.route('/admin')
def admin_dashboard():
    return render_template('admin.html')

@app.route('/upload-chunk', methods=['POST'])
def upload_chunk():
    """Handle chunked file uploads for large files"""
    try:
        chunk = request.files.get('chunk')
        chunk_number = int(request.form.get('chunkNumber', 0))
        total_chunks = int(request.form.get('totalChunks', 1))
        filename = request.form.get('filename', '')
        file_size = int(request.form.get('fileSize', 0))
        
        if not chunk or not filename:
            return jsonify({'error': 'Missing chunk data'}), 400
        
        # Validate file type
        if not allowed_file(filename):
            return jsonify({'error': f'Unsupported file format. Allowed formats: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
        
        # Get or create session ID using secure generation
        session_id = session.get('session_id') or generate_secure_session_id()
        session['session_id'] = session_id
        session.permanent = True
        
        # Create directories
        session_upload_dir = os.path.join(UPLOAD_FOLDER, session_id)
        os.makedirs(session_upload_dir, exist_ok=True)
        
        # Save chunk
        secure_name = secure_filename(filename)
        chunk_path = os.path.join(session_upload_dir, f"{secure_name}.part{chunk_number}")
        chunk.save(chunk_path)
        
        # Check if all chunks are uploaded
        chunks_received = len([f for f in os.listdir(session_upload_dir) if f.startswith(f"{secure_name}.part")])
        
        if chunks_received == total_chunks:
            # Assemble the complete file
            final_path = os.path.join(session_upload_dir, secure_name)
            with open(final_path, 'wb') as final_file:
                for i in range(total_chunks):
                    chunk_file = os.path.join(session_upload_dir, f"{secure_name}.part{i}")
                    with open(chunk_file, 'rb') as part:
                        final_file.write(part.read())
                    os.remove(chunk_file)  # Clean up chunk
            
            # Create database record
            from models import FileUpload
            file_format = secure_name.rsplit('.', 1)[1].lower() if '.' in secure_name else 'unknown'
            
            upload_record = FileUpload()
            upload_record.session_id = session_id
            upload_record.original_filename = secure_name
            upload_record.file_size = file_size
            upload_record.file_format = file_format
            upload_record.status = 'uploaded'
            db.session.add(upload_record)
            db.session.commit()
            
            # Store session data
            session['upload_id'] = upload_record.id
            session['original_filename'] = secure_name
            session['filepath'] = final_path
            session['output_dir'] = os.path.join(OUTPUT_FOLDER, session_id)
            os.makedirs(session['output_dir'], exist_ok=True)
            
            return jsonify({
                'success': True,
                'complete': True,
                'filename': secure_name,
                'session_id': session_id,
                'file_size': file_size,
                'upload_id': upload_record.id
            })
        else:
            return jsonify({
                'success': True,
                'complete': False,
                'chunks_received': chunks_received,
                'total_chunks': total_chunks
            })
            
    except Exception as e:
        logger.error(f"Error during chunk upload: {str(e)}")
        return jsonify({'error': f'Chunk upload failed: {str(e)}'}), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': f'Unsupported file format. Allowed formats: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
    
    session_id = None
    try:
        # Create unique session ID for this upload using secure generation
        session_id = generate_secure_session_id()
        session['session_id'] = session_id
        session.permanent = True
        
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
        
        # Get file information
        file_size = os.path.getsize(filepath)
        file_format = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'unknown'
        
        # Create database record
        from models import FileUpload
        upload_record = FileUpload()
        upload_record.session_id = session_id
        upload_record.original_filename = filename
        upload_record.file_size = file_size
        upload_record.file_format = file_format
        upload_record.status = 'uploaded'
        db.session.add(upload_record)
        db.session.commit()
        
        # Store information in session
        session['upload_id'] = upload_record.id
        session['original_filename'] = filename
        session['filepath'] = filepath
        session['output_dir'] = session_output_dir
        
        logger.info(f"File uploaded successfully: {filename} ({file_size} bytes)")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'session_id': session_id,
            'file_size': file_size,
            'upload_id': upload_record.id
        })
    
    except Exception as e:
        logger.error(f"Error during file upload: {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Clean up session directories if they were created
        try:
            if session_id:
                session_upload_dir = os.path.join(UPLOAD_FOLDER, session_id)
                session_output_dir = os.path.join(OUTPUT_FOLDER, session_id)
                if os.path.exists(session_upload_dir):
                    shutil.rmtree(session_upload_dir)
                if os.path.exists(session_output_dir):
                    shutil.rmtree(session_output_dir)
        except:
            pass
        
        return jsonify({'error': f'Error uploading file: {str(e)}'}), 500

@app.route('/split', methods=['POST'])
def split_file():
    if 'filepath' not in session or 'output_dir' not in session or 'upload_id' not in session:
        return jsonify({'error': 'No file uploaded'}), 400
    
    try:
        # Get parameters from the form
        segment_size = request.form.get('segment_size', type=int)
        split_type = request.form.get('split_type', 'seconds')
        
        # Enhanced validation using security module
        is_valid, validation_error = validate_segment_parameters(segment_size, split_type)
        if not is_valid:
            return jsonify({'error': validation_error}), 400
        
        # Get upload record and update status
        from models import FileUpload, AudioSegment
        upload_id = session['upload_id']
        upload_record = FileUpload.query.get(upload_id)
        if not upload_record:
            return jsonify({'error': 'Upload record not found'}), 400
        
        # Update processing parameters
        upload_record.segment_size = segment_size
        upload_record.split_type = split_type
        upload_record.status = 'processing'
        upload_record.processing_timestamp = datetime.utcnow()
        db.session.commit()
        
        # Process the audio file
        filepath = session['filepath']
        output_dir = session['output_dir']
        original_filename = session['original_filename']
        
        logger.info(f"Starting split process: {original_filename}, {segment_size} {split_type}")
        logger.info(f"File path: {filepath}")
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"File exists: {os.path.exists(filepath)}")
        
        # Verify file accessibility
        if not os.path.exists(filepath):
            raise Exception(f"Input file not found: {filepath}")
        
        # Track processing time
        start_time = time.time()
        
        # Split the audio file with enhanced error handling
        try:
            output_files = split_audio_file(
                filepath, 
                output_dir, 
                segment_size, 
                split_type
            )
        except Exception as split_error:
            logger.error(f"Split audio file error: {str(split_error)}")
            logger.error(f"Error type: {type(split_error).__name__}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
        
        processing_duration = time.time() - start_time
        
        if not output_files:
            upload_record.status = 'error'
            upload_record.error_message = 'No segments were created. File may be too short.'
            db.session.commit()
            return jsonify({'error': 'No segments were created. File may be too short.'}), 400
        
        # Calculate total output size and create segment records
        total_size = 0
        logger.info(f"Processing {len(output_files)} output files:")
        for i, filename in enumerate(output_files):
            file_path = os.path.join(output_dir, filename)
            logger.info(f"Checking file {i+1}: {file_path}")
            logger.info(f"File exists: {os.path.exists(file_path)}")
            
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                total_size += file_size
                logger.info(f"File size: {file_size} bytes")
                
                # Verify file is readable
                try:
                    with open(file_path, 'rb') as test_file:
                        test_file.read(1024)  # Test read first 1KB
                    logger.info(f"File is readable: {filename}")
                except Exception as e:
                    logger.error(f"File read error for {filename}: {e}")
                
                # Create segment record in database
                segment_record = AudioSegment()
                segment_record.upload_id = upload_id
                segment_record.filename = filename
                segment_record.segment_number = i + 1
                segment_record.file_size = file_size
                segment_record.duration_ms = 0  # Will be calculated later if needed
                segment_record.start_time_ms = 0  # Will be calculated later if needed
                segment_record.end_time_ms = 0   # Will be calculated later if needed
                db.session.add(segment_record)
            else:
                logger.error(f"Output file missing: {file_path}")
                # Check if file exists in directory listing
                if os.path.exists(output_dir):
                    dir_contents = os.listdir(output_dir)
                    logger.info(f"Directory contents: {dir_contents}")
                else:
                    logger.error(f"Output directory missing: {output_dir}")
        
        # Update upload record with completion details
        upload_record.segments_created = len(output_files)
        upload_record.total_output_size = total_size
        upload_record.processing_duration = processing_duration
        upload_record.status = 'completed'
        db.session.commit()
        
        # Store output files in session
        session['output_files'] = output_files
        
        # Get session ID
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({'error': 'Session ID not found'}), 400
        
        # Create ZIP file immediately after splitting
        zip_filename = f"{session_id}_all_segments.zip"
        zip_path = os.path.join(OUTPUT_FOLDER, zip_filename)
        
        try:
            import zipfile
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for filename in output_files:
                    file_path = os.path.join(output_dir, filename)
                    if os.path.exists(file_path):
                        zipf.write(file_path, filename)
                        logger.info(f"Added to ZIP: {filename}")
            
            logger.info(f"Created ZIP file: {zip_path} ({os.path.getsize(zip_path)} bytes)")
            session['zip_filename'] = zip_filename
        except Exception as zip_error:
            logger.error(f"Error creating ZIP file: {zip_error}")
            # Continue without ZIP file - individual downloads will still work
        
        total_size_mb = total_size / (1024 * 1024)
        
        logger.info(f"Successfully created {len(output_files)} segments, total size: {total_size_mb:.1f}MB, processing time: {processing_duration:.2f}s")
        
        # Return success response with detailed information
        return jsonify({
            'success': True,
            'message': f'Successfully split into {len(output_files)} segments',
            'files': output_files,
            'total_size_mb': round(total_size_mb, 2),
            'segment_count': len(output_files),
            'processing_time': round(processing_duration, 2),
            'zip_filename': zip_filename
        })
    
    except Exception as e:
        # Update upload record with error
        try:
            from models import FileUpload
            upload_id = session.get('upload_id')
            if upload_id:
                upload_record = FileUpload.query.get(upload_id)
                if upload_record:
                    upload_record.status = 'error'
                    upload_record.error_message = str(e)
                    db.session.commit()
        except:
            pass
        
        logger.error(f"Error during file splitting: {str(e)}")
        error_msg = str(e)
        if "timeout" in error_msg.lower() or "worker timeout" in error_msg.lower():
            error_msg = "File processing took too long. Try splitting into smaller segments or use a smaller file."
        return jsonify({'error': f'Processing failed: {error_msg}'}), 500

@app.route('/download/<path:filename>', methods=['GET'])
def download_file(filename):
    try:
        from models import AudioSegment, FileUpload
        
        # First try to find the file in database records
        segment = AudioSegment.query.filter_by(filename=filename).order_by(AudioSegment.created_timestamp.desc()).first()
        
        if segment:
            # Get the upload record to find session_id
            upload = FileUpload.query.get(segment.upload_id)
            if upload:
                output_dir = os.path.join(OUTPUT_FOLDER, upload.session_id)
                file_path = os.path.join(output_dir, filename)
                
                logger.info(f"Download request from DB: {filename}")
                logger.info(f"Session ID: {upload.session_id}")
                logger.info(f"Output directory: {output_dir}")
                logger.info(f"File path: {file_path}")
                
                if os.path.exists(file_path):
                    # Update download count
                    segment.download_count += 1
                    db.session.commit()
                    
                    return send_file(file_path, as_attachment=True)
        
        # Fallback: try session-based approach
        if 'output_dir' in session:
            output_dir = session['output_dir']
            file_path = os.path.join(output_dir, filename)
            
            logger.info(f"Download fallback from session: {filename}")
            logger.info(f"Output directory: {output_dir}")
            
            if os.path.exists(file_path):
                return send_file(file_path, as_attachment=True)
        
        logger.error(f"File not found anywhere: {filename}")
        return f"File not found: {filename}", 404
    
    except Exception as e:
        logger.error(f"Download error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return f"Error downloading file: {str(e)}", 500

@app.route('/download-zip/<path:zip_filename>', methods=['GET'])
def download_zip(zip_filename):
    """Download pre-created ZIP file directly"""
    try:
        zip_path = os.path.join(OUTPUT_FOLDER, zip_filename)
        
        logger.info(f"ZIP download request: {zip_filename}")
        logger.info(f"ZIP file path: {zip_path}")
        logger.info(f"ZIP file exists: {os.path.exists(zip_path)}")
        
        if os.path.exists(zip_path):
            try:
                logger.info(f"Attempting to send file: {zip_path}")
                return send_file(zip_path, as_attachment=True)
            except Exception as send_error:
                logger.error(f"Error sending ZIP file: {send_error}")
                import traceback
                logger.error(f"Send file traceback: {traceback.format_exc()}")
                return f"Error sending ZIP file: {str(send_error)}", 500
        else:
            logger.error(f"ZIP file not found: {zip_path}")
            return "ZIP file not found", 404
    
    except FileNotFoundError:
        logger.error(f"FileNotFoundError: ZIP file not found: {zip_path}")
        return "ZIP file not found", 404
    except Exception as e:
        logger.error(f"Error downloading ZIP file: {e}")
        import traceback
        logger.error(f"General download traceback: {traceback.format_exc()}")
        return f"Error downloading ZIP file: {str(e)}", 500

@app.route('/download-all', methods=['GET'])
def download_all():
    logger.info(f"Download-all request - session keys: {list(session.keys())}")
    
    # For debugging, try to find any recent session with files
    session_id = session.get('session_id')
    output_dir = session.get('output_dir')
    
    if not session_id or not output_dir:
        # Try to find the most recent upload session from database
        try:
            from models import FileUpload
            recent_upload = FileUpload.query.filter_by(status='completed').order_by(FileUpload.processing_timestamp.desc()).first()
            if recent_upload:
                session_id = recent_upload.session_id
                output_dir = os.path.join(OUTPUT_FOLDER, session_id)
                logger.info(f"Using most recent upload session: {session_id}")
            else:
                logger.error("No recent completed uploads found")
                return "No files available for download", 400
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            return "No files available for download", 400
    
    # Try to get output_files from session, or rebuild from directory
    output_files = session.get('output_files', [])
    if not output_files and os.path.exists(output_dir):
        output_files = [f for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
        session['output_files'] = output_files  # Update session
        session['session_id'] = session_id
        session['output_dir'] = output_dir
    
    if not output_files:
        logger.error(f"No output files found in {output_dir}")
        return "No files available for download", 400
    
    try:
        # Verify session data exists
        session_id = session['session_id']
        output_dir = session['output_dir']
        output_files = session.get('output_files', [])
        
        logger.info(f"Download-all request for session: {session_id}")
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"Session output_files: {output_files}")
        
        # Check if output directory exists
        if not os.path.exists(output_dir):
            logger.error(f"Output directory does not exist: {output_dir}")
            return "Files not found. They may have been cleaned up.", 400
        
        # Get list of actual files in the directory
        actual_files = []
        if os.path.exists(output_dir):
            actual_files = [f for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
        
        logger.info(f"Actual files in directory: {actual_files}")
        
        if not actual_files:
            logger.error(f"No files found in output directory: {output_dir}")
            return "No segment files found to download.", 400
        
        # Create zip file with all segments
        zip_filename = f"{session_id}_all_segments.zip"
        zip_path = os.path.join(OUTPUT_FOLDER, zip_filename)
        
        logger.info(f"Creating ZIP file: {zip_path}")
        
        # Remove existing zip file if it exists
        if os.path.exists(zip_path):
            os.remove(zip_path)
        
        import zipfile
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename in actual_files:
                file_path = os.path.join(output_dir, filename)
                if os.path.exists(file_path):
                    zipf.write(file_path, filename)
                    logger.info(f"Added to ZIP: {filename}")
        
        # Verify zip file was created and has content
        if not os.path.exists(zip_path) or os.path.getsize(zip_path) == 0:
            logger.error("ZIP file creation failed or empty")
            return "Error: ZIP file creation failed", 500
            
        logger.info(f"Created ZIP file: {zip_path} ({os.path.getsize(zip_path)} bytes) with {len(actual_files)} files")
        
        return send_from_directory(
            OUTPUT_FOLDER,
            zip_filename,
            as_attachment=True,
            download_name=f"audio_segments_{session.get('original_filename', 'audio').split('.')[0]}.zip"
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

@app.route('/delete-files', methods=['POST'])
def delete_files():
    """Delete files for a specific session after download"""
    try:
        data = request.get_json()
        if not data or 'session_id' not in data:
            return jsonify({'error': 'Session ID is required'}), 400
        
        session_id = data['session_id']
        
        # Verify session matches current user session (allow both current session and the provided session_id)
        current_session_id = session.get('session_id')
        if current_session_id != session_id:
            # Check if the provided session_id exists in the database and belongs to recent uploads
            from models import FileUpload
            upload_record = FileUpload.query.filter_by(session_id=session_id).first()
            if not upload_record:
                return jsonify({'error': 'Invalid session'}), 403
        
        upload_dir = os.path.join(UPLOAD_FOLDER, session_id)
        output_dir = os.path.join(OUTPUT_FOLDER, session_id)
        
        deleted_files = []
        
        # Delete upload directory
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)
            deleted_files.append('upload directory')
        
        # Delete output directory
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
            deleted_files.append('output directory')
        
        # Update database record to indicate files were deleted
        upload_id = session.get('upload_id')
        if upload_id:
            from models import FileUpload
            upload_record = FileUpload.query.get(upload_id)
            if upload_record:
                upload_record.status = 'deleted'
                db.session.commit()
        
        # Clear session data related to files
        session.pop('output_files', None)
        session.pop('filepath', None)
        session.pop('output_dir', None)
        
        # Also clean up any ZIP files
        try:
            zip_path = os.path.join(OUTPUT_FOLDER, f"{session_id}_all_segments.zip")
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except:
            pass
        
        logger.info(f"Files deleted successfully for session: {session_id}")
        
        return jsonify({
            'success': True,
            'message': f'Deleted {len(deleted_files)} directories',
            'deleted': deleted_files
        })
        
    except Exception as e:
        logger.error(f"Error during file deletion: {str(e)}")
        return jsonify({'error': f'Error deleting files: {str(e)}'}), 500

# Analytics API endpoints
@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get application usage statistics"""
    try:
        from models import FileUpload, AudioSegment
        from sqlalchemy import func
        
        # Basic statistics
        total_uploads = FileUpload.query.count()
        total_segments = AudioSegment.query.count()
        total_downloads = db.session.query(func.sum(AudioSegment.download_count)).scalar() or 0
        
        # File format distribution
        format_stats = db.session.query(
            FileUpload.file_format,
            func.count(FileUpload.id).label('count')
        ).group_by(FileUpload.file_format).all()
        
        # Processing status distribution
        status_stats = db.session.query(
            FileUpload.status,
            func.count(FileUpload.id).label('count')
        ).group_by(FileUpload.status).all()
        
        # Average processing time
        avg_processing_time = db.session.query(
            func.avg(FileUpload.processing_duration)
        ).filter(FileUpload.processing_duration.isnot(None)).scalar() or 0
        
        # Total data processed (in MB)
        total_data_processed = db.session.query(
            func.sum(FileUpload.file_size)
        ).scalar() or 0
        total_data_processed_mb = total_data_processed / (1024 * 1024)
        
        return jsonify({
            'total_uploads': total_uploads,
            'total_segments': total_segments,
            'total_downloads': total_downloads,
            'total_data_processed_mb': round(total_data_processed_mb, 2),
            'avg_processing_time': round(avg_processing_time, 2) if avg_processing_time else 0,
            'format_distribution': [{'format': f, 'count': c} for f, c in format_stats],
            'status_distribution': [{'status': s, 'count': c} for s, c in status_stats]
        })
    
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return jsonify({'error': 'Failed to retrieve statistics'}), 500

@app.route('/api/recent-uploads', methods=['GET'])
def get_recent_uploads():
    """Get recent upload history"""
    try:
        from models import FileUpload
        
        limit = request.args.get('limit', 10, type=int)
        
        recent_uploads = FileUpload.query.order_by(
            FileUpload.upload_timestamp.desc()
        ).limit(limit).all()
        
        return jsonify({
            'uploads': [upload.to_dict() for upload in recent_uploads]
        })
    
    except Exception as e:
        logger.error(f"Error getting recent uploads: {str(e)}")
        return jsonify({'error': 'Failed to retrieve recent uploads'}), 500

@app.route('/api/upload/<int:upload_id>', methods=['GET'])
def get_upload_details(upload_id):
    """Get detailed information about a specific upload"""
    try:
        from models import FileUpload, AudioSegment
        
        upload = FileUpload.query.get_or_404(upload_id)
        segments = AudioSegment.query.filter_by(upload_id=upload_id).all()
        
        return jsonify({
            'upload': upload.to_dict(),
            'segments': [segment.to_dict() for segment in segments]
        })
    
    except Exception as e:
        logger.error(f"Error getting upload details: {str(e)}")
        return jsonify({'error': 'Failed to retrieve upload details'}), 500

# Error handlers
@app.errorhandler(413)
def request_entity_too_large(error):
    max_size_mb = MAX_CONTENT_LENGTH // (1024 * 1024)
    error_message = f'File too large. Maximum size is {max_size_mb}MB. Please try a smaller file or split it before uploading.'
    
    # Check if this is an AJAX request
    if request.headers.get('Content-Type') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'error': error_message,
            'max_size_mb': max_size_mb,
            'error_code': 'FILE_TOO_LARGE'
        }), 413
    
    # For regular form requests
    flash(error_message)
    return redirect(url_for('index'))

@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
