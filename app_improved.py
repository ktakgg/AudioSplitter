import os
import logging
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, url_for, flash, redirect, session, send_file
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
import tempfile
import shutil
from typing import Optional, Tuple

# 改善されたインポート
from database import db
from config import config
from security import (
    validate_audio_file, 
    generate_secure_session_id, 
    sanitize_path,
    validate_segment_parameters
)
from audio_splitter import split_audio_file

def create_app(config_name: str = None) -> Flask:
    """アプリケーションファクトリパターン"""
    app = Flask(__name__)
    
    # 設定の読み込み
    config_name = config_name or os.environ.get('FLASK_ENV', 'default')
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
    # ミドルウェア設定
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    
    # ログ設定
    setup_logging(app)
    
    # データベース初期化
    db.init_app(app)
    
    # ルート登録
    register_routes(app)
    register_error_handlers(app)
    
    # データベーステーブル作成
    with app.app_context():
        import models
        db.create_all()
    
    return app

def setup_logging(app: Flask):
    """ログ設定"""
    log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO'))
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s'
    )
    
    # 本番環境では機密情報をログに出力しない
    if not app.debug:
        logging.getLogger('werkzeug').setLevel(logging.WARNING)

def register_routes(app: Flask):
    """ルート登録"""
    
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/config')
    def get_config():
        """クライアント設定を返す"""
        return jsonify({
            'max_file_size': app.config['MAX_CONTENT_LENGTH'],
            'max_file_size_mb': app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024),
            'environment': os.environ.get('REPLIT_DEPLOYMENT', 'development'),
            'deployment_id': os.environ.get('REPL_ID', 'local')
        })

    @app.route('/admin')
    def admin_dashboard():
        return render_template('admin.html')

    @app.route('/upload-chunk', methods=['POST'])
    def upload_chunk():
        """チャンク分割アップロード処理"""
        try:
            chunk = request.files.get('chunk')
            chunk_number = int(request.form.get('chunkNumber', 0))
            total_chunks = int(request.form.get('totalChunks', 1))
            filename = request.form.get('filename', '')
            file_size = int(request.form.get('fileSize', 0))
            
            if not chunk or not filename:
                return jsonify({'error': 'チャンクデータが不足しています'}), 400
            
            # ファイル名の安全性チェック
            safe_filename = secure_filename(filename)
            if not safe_filename:
                return jsonify({'error': '無効なファイル名です'}), 400
            
            # セッションID生成または取得
            session_id = session.get('session_id') or generate_secure_session_id()
            session['session_id'] = session_id
            session.permanent = True
            
            # ディレクトリ作成
            session_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
            os.makedirs(session_upload_dir, exist_ok=True)
            
            # チャンク保存
            chunk_path = os.path.join(session_upload_dir, f"{safe_filename}.part{chunk_number}")
            chunk.save(chunk_path)
            
            # 全チャンクが揃ったかチェック
            chunks_received = len([f for f in os.listdir(session_upload_dir) 
                                 if f.startswith(f"{safe_filename}.part")])
            
            if chunks_received == total_chunks:
                # ファイル結合
                final_path = os.path.join(session_upload_dir, safe_filename)
                success, error_msg = _assemble_chunks(session_upload_dir, safe_filename, total_chunks)
                
                if not success:
                    return jsonify({'error': error_msg}), 500
                
                # ファイル検証
                is_valid, validation_error = validate_audio_file(final_path, safe_filename)
                if not is_valid:
                    os.remove(final_path)
                    return jsonify({'error': validation_error}), 400
                
                # データベース記録
                upload_record = _create_upload_record(session_id, safe_filename, file_size, final_path)
                
                # セッション情報保存
                _save_session_info(session, upload_record, final_path, session_id)
                
                return jsonify({
                    'success': True,
                    'complete': True,
                    'filename': safe_filename,
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
            app.logger.error(f"チャンクアップロードエラー: {str(e)}")
            return jsonify({'error': 'チャンクアップロードに失敗しました'}), 500

    @app.route('/upload', methods=['POST'])
    def upload_file():
        """通常のファイルアップロード処理"""
        if 'file' not in request.files:
            return jsonify({'error': 'ファイルが選択されていません'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'ファイルが選択されていません'}), 400
        
        # ファイル名の安全性チェック
        safe_filename = secure_filename(file.filename)
        if not safe_filename:
            return jsonify({'error': '無効なファイル名です'}), 400
        
        session_id = None
        try:
            # セッションID生成
            session_id = generate_secure_session_id()
            session['session_id'] = session_id
            session.permanent = True
            
            # ディレクトリ作成
            session_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
            session_output_dir = os.path.join(app.config['OUTPUT_FOLDER'], session_id)
            os.makedirs(session_upload_dir, exist_ok=True)
            os.makedirs(session_output_dir, exist_ok=True)
            
            # ファイル保存
            filepath = os.path.join(session_upload_dir, safe_filename)
            file.save(filepath)
            
            # ファイル検証
            is_valid, validation_error = validate_audio_file(filepath, safe_filename)
            if not is_valid:
                _cleanup_session_dirs(session_id, app.config)
                return jsonify({'error': validation_error}), 400
            
            # ファイル情報取得
            file_size = os.path.getsize(filepath)
            
            # データベース記録
            upload_record = _create_upload_record(session_id, safe_filename, file_size, filepath)
            
            # セッション情報保存
            _save_session_info(session, upload_record, filepath, session_id)
            
            app.logger.info(f"ファイルアップロード成功: {safe_filename} ({file_size} bytes)")
            
            return jsonify({
                'success': True,
                'filename': safe_filename,
                'session_id': session_id,
                'file_size': file_size,
                'upload_id': upload_record.id
            })
        
        except Exception as e:
            app.logger.error(f"ファイルアップロードエラー: {str(e)}")
            if session_id:
                _cleanup_session_dirs(session_id, app.config)
            return jsonify({'error': 'ファイルアップロードに失敗しました'}), 500

    @app.route('/split', methods=['POST'])
    def split_file():
        """音声ファイル分割処理"""
        if not _validate_session():
            return jsonify({'error': 'セッションが無効です'}), 400
        
        try:
            # パラメータ取得と検証
            segment_size = request.form.get('segment_size', type=int)
            split_type = request.form.get('split_type', 'seconds')
            
            is_valid, validation_error = validate_segment_parameters(segment_size, split_type)
            if not is_valid:
                return jsonify({'error': validation_error}), 400
            
            # アップロード記録更新
            upload_record = _update_processing_status(session['upload_id'], segment_size, split_type)
            if not upload_record:
                return jsonify({'error': 'アップロード記録が見つかりません'}), 400
            
            # 音声分割処理
            filepath = session['filepath']
            output_dir = session['output_dir']
            
            app.logger.info(f"音声分割開始: {session['original_filename']}")
            
            start_time = time.time()
            output_files = split_audio_file(filepath, output_dir, segment_size, split_type)
            processing_duration = time.time() - start_time
            
            if not output_files:
                upload_record.status = 'error'
                upload_record.error_message = 'セグメントが作成されませんでした'
                db.session.commit()
                return jsonify({'error': 'セグメントが作成されませんでした'}), 400
            
            # 結果処理
            total_size = _process_output_files(output_files, output_dir, upload_record.id)
            
            # 完了状態更新
            upload_record.segments_created = len(output_files)
            upload_record.total_output_size = total_size
            upload_record.processing_duration = processing_duration
            upload_record.status = 'completed'
            db.session.commit()
            
            session['output_files'] = output_files
            
            app.logger.info(f"音声分割完了: {len(output_files)}セグメント作成")
            
            return jsonify({
                'success': True,
                'message': f'{len(output_files)}個のセグメントに分割しました',
                'files': output_files,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'segment_count': len(output_files),
                'processing_time': round(processing_duration, 2)
            })
        
        except Exception as e:
            app.logger.error(f"音声分割エラー: {str(e)}")
            _update_error_status(session.get('upload_id'), str(e))
            return jsonify({'error': '音声分割処理に失敗しました'}), 500

    # 他のルートも同様に改善...
    # (download_file, download_all, cleanup, delete_files, API endpoints)

def register_error_handlers(app: Flask):
    """エラーハンドラー登録"""
    
    @app.errorhandler(413)
    def request_entity_too_large(error):
        max_size_mb = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
        error_message = f'ファイルサイズが大きすぎます。最大サイズは{max_size_mb}MBです。'
        
        if request.headers.get('Content-Type') == 'application/json':
            return jsonify({
                'error': error_message,
                'max_size_mb': max_size_mb,
                'error_code': 'FILE_TOO_LARGE'
            }), 413
        
        flash(error_message)
        return redirect(url_for('index'))

    @app.errorhandler(500)
    def server_error(error):
        app.logger.error(f"サーバーエラー: {str(error)}")
        return jsonify({'error': '内部サーバーエラーが発生しました'}), 500

# ヘルパー関数
def _validate_session() -> bool:
    """セッション検証"""
    required_keys = ['filepath', 'output_dir', 'upload_id']
    return all(key in session for key in required_keys)

def _assemble_chunks(upload_dir: str, filename: str, total_chunks: int) -> Tuple[bool, Optional[str]]:
    """チャンクファイルを結合"""
    try:
        final_path = os.path.join(upload_dir, filename)
        with open(final_path, 'wb') as final_file:
            for i in range(total_chunks):
                chunk_file = os.path.join(upload_dir, f"{filename}.part{i}")
                if not os.path.exists(chunk_file):
                    return False, f"チャンク{i}が見つかりません"
                
                with open(chunk_file, 'rb') as part:
                    final_file.write(part.read())
                os.remove(chunk_file)
        
        return True, None
    except Exception as e:
        return False, f"ファイル結合エラー: {str(e)}"

def _create_upload_record(session_id: str, filename: str, file_size: int, filepath: str):
    """アップロード記録作成"""
    from models import FileUpload
    
    file_format = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'unknown'
    
    upload_record = FileUpload()
    upload_record.session_id = session_id
    upload_record.original_filename = filename
    upload_record.file_size = file_size
    upload_record.file_format = file_format
    upload_record.status = 'uploaded'
    db.session.add(upload_record)
    db.session.commit()
    
    return upload_record

def _save_session_info(session, upload_record, filepath: str, session_id: str):
    """セッション情報保存"""
    session['upload_id'] = upload_record.id
    session['original_filename'] = upload_record.original_filename
    session['filepath'] = filepath
    session['output_dir'] = os.path.join(current_app.config['OUTPUT_FOLDER'], session_id)
    os.makedirs(session['output_dir'], exist_ok=True)

def _cleanup_session_dirs(session_id: str, config: dict):
    """セッションディレクトリクリーンアップ"""
    try:
        upload_dir = os.path.join(config['UPLOAD_FOLDER'], session_id)
        output_dir = os.path.join(config['OUTPUT_FOLDER'], session_id)
        
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
    except Exception:
        pass

def _update_processing_status(upload_id: int, segment_size: int, split_type: str):
    """処理状態更新"""
    from models import FileUpload
    
    upload_record = FileUpload.query.get(upload_id)
    if upload_record:
        upload_record.segment_size = segment_size
        upload_record.split_type = split_type
        upload_record.status = 'processing'
        upload_record.processing_timestamp = datetime.utcnow()
        db.session.commit()
    
    return upload_record

def _process_output_files(output_files: list, output_dir: str, upload_id: int) -> int:
    """出力ファイル処理"""
    from models import AudioSegment
    
    total_size = 0
    for i, filename in enumerate(output_files):
        file_path = os.path.join(output_dir, filename)
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            total_size += file_size
            
            # セグメント記録作成
            segment_record = AudioSegment()
            segment_record.upload_id = upload_id
            segment_record.filename = filename
            segment_record.segment_number = i + 1
            segment_record.file_size = file_size
            segment_record.duration_ms = 0
            segment_record.start_time_ms = 0
            segment_record.end_time_ms = 0
            db.session.add(segment_record)
    
    db.session.commit()
    return total_size

def _update_error_status(upload_id: Optional[int], error_message: str):
    """エラー状態更新"""
    if upload_id:
        from models import FileUpload
        upload_record = FileUpload.query.get(upload_id)
        if upload_record:
            upload_record.status = 'error'
            upload_record.error_message = error_message
            db.session.commit()

# アプリケーション作成
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
