import os
from datetime import timedelta

class Config:
    """基本設定クラス"""
    # セキュリティ設定
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32)
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    
    # データベース設定
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # ファイルアップロード設定
    MAX_CONTENT_LENGTH = int(os.environ.get('FLASK_MAX_CONTENT_LENGTH', 200 * 1024 * 1024))
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
    OUTPUT_FOLDER = os.path.join(os.getcwd(), 'splits')
    
    # セキュリティヘッダー
    SEND_FILE_MAX_AGE_DEFAULT = 0
    
    # ログ設定
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    
    @staticmethod
    def init_app(app):
        """アプリケーション初期化時の処理"""
        # ディレクトリ作成
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.OUTPUT_FOLDER, exist_ok=True)

class DevelopmentConfig(Config):
    """開発環境設定"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'

class ProductionConfig(Config):
    """本番環境設定"""
    DEBUG = False
    LOG_LEVEL = 'WARNING'
    
    # 本番環境でのセキュリティ強化
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

class TestingConfig(Config):
    """テスト環境設定"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
