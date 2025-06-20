from database import db
from datetime import datetime
from sqlalchemy import func, CheckConstraint


class FileUpload(db.Model):
    __tablename__ = 'file_uploads'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), nullable=False, index=True)
    original_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.BigInteger, nullable=False)
    file_format = db.Column(db.String(10), nullable=False)
    upload_timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Processing details
    segment_size = db.Column(db.Integer)
    split_type = db.Column(db.String(20))  # 'seconds' or 'megabytes'
    segments_created = db.Column(db.Integer)
    total_output_size = db.Column(db.BigInteger)
    processing_duration = db.Column(db.Float)  # in seconds
    processing_timestamp = db.Column(db.DateTime)
    
    # Status tracking
    status = db.Column(db.String(20), default='uploaded', nullable=False)  # uploaded, processing, completed, error
    error_message = db.Column(db.Text)
    
    # Relationships
    segments = db.relationship('AudioSegment', backref='upload', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<FileUpload {self.original_filename}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'original_filename': self.original_filename,
            'file_size': self.file_size,
            'file_format': self.file_format,
            'upload_timestamp': self.upload_timestamp.isoformat() if self.upload_timestamp else None,
            'segment_size': self.segment_size,
            'split_type': self.split_type,
            'segments_created': self.segments_created,
            'total_output_size': self.total_output_size,
            'processing_duration': self.processing_duration,
            'processing_timestamp': self.processing_timestamp.isoformat() if self.processing_timestamp else None,
            'status': self.status,
            'error_message': self.error_message
        }


class AudioSegment(db.Model):
    __tablename__ = 'audio_segments'
    
    id = db.Column(db.Integer, primary_key=True)
    upload_id = db.Column(db.Integer, db.ForeignKey('file_uploads.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    segment_number = db.Column(db.Integer, nullable=False)
    file_size = db.Column(db.BigInteger, nullable=False)
    duration_ms = db.Column(db.Integer, nullable=False)
    start_time_ms = db.Column(db.Integer, nullable=False)
    end_time_ms = db.Column(db.Integer, nullable=False)
    created_timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    download_count = db.Column(db.Integer, default=0, nullable=False)
    
    def __repr__(self):
        return f'<AudioSegment {self.filename}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'upload_id': self.upload_id,
            'filename': self.filename,
            'segment_number': self.segment_number,
            'file_size': self.file_size,
            'duration_ms': self.duration_ms,
            'start_time_ms': self.start_time_ms,
            'end_time_ms': self.end_time_ms,
            'created_timestamp': self.created_timestamp.isoformat() if self.created_timestamp else None,
            'download_count': self.download_count
        }


class ProcessingStats(db.Model):
    __tablename__ = 'processing_stats'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=func.current_date(), nullable=False, unique=True)
    total_files = db.Column(db.Integer, default=0, nullable=False)
    total_segments = db.Column(db.Integer, default=0, nullable=False)
    total_size_processed = db.Column(db.BigInteger, default=0, nullable=False)
    total_downloads = db.Column(db.Integer, default=0, nullable=False)
    avg_processing_time = db.Column(db.Float, default=0.0, nullable=False)
    
    def __repr__(self):
        return f'<ProcessingStats {self.date}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'total_files': self.total_files,
            'total_segments': self.total_segments,
            'total_size_processed': self.total_size_processed,
            'total_downloads': self.total_downloads,
            'avg_processing_time': self.avg_processing_time
        }
