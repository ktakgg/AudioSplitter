import os
import hashlib
import secrets
from werkzeug.utils import secure_filename
from typing import Optional, Tuple

# python-magicが利用できない場合のフォールバック
try:
    import magic
    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False

# 許可されたファイル形式とMIMEタイプのマッピング
ALLOWED_AUDIO_FORMATS = {
    'mp3': ['audio/mpeg', 'audio/mp3'],
    'wav': ['audio/wav', 'audio/wave', 'audio/x-wav'],
    'ogg': ['audio/ogg', 'application/ogg'],
    'm4a': ['audio/mp4', 'audio/x-m4a', 'audio/m4a'],
    'flac': ['audio/flac', 'audio/x-flac'],
    'aac': ['audio/aac', 'audio/x-aac'],
    'wma': ['audio/x-ms-wma']
}

def validate_audio_file(file_path: str, original_filename: str) -> Tuple[bool, Optional[str]]:
    """
    音声ファイルの詳細検証を行う
    
    Args:
        file_path: アップロードされたファイルのパス
        original_filename: 元のファイル名
    
    Returns:
        (is_valid, error_message)
    """
    try:
        # ファイル拡張子チェック
        if '.' not in original_filename:
            return False, "ファイル拡張子がありません"
        
        extension = original_filename.rsplit('.', 1)[1].lower()
        if extension not in ALLOWED_AUDIO_FORMATS:
            return False, f"サポートされていないファイル形式: {extension}"
        
        # ファイルサイズチェック（空ファイル）
        if os.path.getsize(file_path) == 0:
            return False, "ファイルが空です"
        
        # MIMEタイプ検証（python-magicが利用可能な場合のみ）
        if HAS_MAGIC:
            try:
                mime_type = magic.from_file(file_path, mime=True)
                allowed_mimes = ALLOWED_AUDIO_FORMATS[extension]
                
                if mime_type not in allowed_mimes:
                    return False, f"ファイル内容が拡張子と一致しません。検出されたタイプ: {mime_type}"
            except Exception as e:
                # MIMEタイプ検証に失敗した場合はスキップ
                pass
        
        # ファイル名の安全性チェック
        safe_filename = secure_filename(original_filename)
        if not safe_filename or safe_filename != original_filename:
            return False, "ファイル名に無効な文字が含まれています"
        
        return True, None
        
    except Exception as e:
        return False, f"ファイル検証中にエラーが発生しました: {str(e)}"

def generate_secure_session_id() -> str:
    """セキュアなセッションIDを生成"""
    return secrets.token_urlsafe(32)

def generate_file_hash(file_path: str) -> str:
    """ファイルのハッシュ値を生成（重複チェック用）"""
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()

def sanitize_path(path: str) -> str:
    """パストラバーサル攻撃を防ぐためのパス正規化"""
    # 危険な文字列を除去
    dangerous_patterns = ['..', '~', '$', '|', ';', '&', '`']
    for pattern in dangerous_patterns:
        path = path.replace(pattern, '')
    
    # 絶対パスを相対パスに変換
    if os.path.isabs(path):
        path = os.path.relpath(path)
    
    return secure_filename(path)

def validate_segment_parameters(segment_size: int, split_type: str) -> Tuple[bool, Optional[str]]:
    """分割パラメータの検証"""
    if split_type not in ['seconds', 'megabytes']:
        return False, "無効な分割タイプです"
    
    if segment_size <= 0:
        return False, "セグメントサイズは正の値である必要があります"
    
    if split_type == 'seconds' and segment_size > 3600:
        return False, "セグメントサイズは1時間以下である必要があります"
    
    if split_type == 'megabytes' and segment_size > 100:
        return False, "セグメントサイズは100MB以下である必要があります"
    
    return True, None
