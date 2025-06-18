import unittest
import tempfile
import os
from security import (
    validate_audio_file,
    generate_secure_session_id,
    sanitize_path,
    validate_segment_parameters
)

class TestSecurity(unittest.TestCase):
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_validate_audio_file_valid_extension(self):
        # 有効な拡張子のテスト
        test_file = os.path.join(self.temp_dir, 'test.mp3')
        with open(test_file, 'wb') as f:
            f.write(b'dummy audio data')
        
        is_valid, error = validate_audio_file(test_file, 'test.mp3')
        self.assertTrue(is_valid)
        self.assertIsNone(error)
    
    def test_validate_audio_file_invalid_extension(self):
        # 無効な拡張子のテスト
        test_file = os.path.join(self.temp_dir, 'test.txt')
        with open(test_file, 'wb') as f:
            f.write(b'dummy data')
        
        is_valid, error = validate_audio_file(test_file, 'test.txt')
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)
    
    def test_validate_audio_file_empty_file(self):
        # 空ファイルのテスト
        test_file = os.path.join(self.temp_dir, 'empty.mp3')
        with open(test_file, 'wb') as f:
            pass  # 空ファイル作成
        
        is_valid, error = validate_audio_file(test_file, 'empty.mp3')
        self.assertFalse(is_valid)
        self.assertIn('空です', error)
    
    def test_generate_secure_session_id(self):
        # セッションID生成のテスト
        session_id1 = generate_secure_session_id()
        session_id2 = generate_secure_session_id()
        
        self.assertNotEqual(session_id1, session_id2)
        self.assertGreater(len(session_id1), 20)
        self.assertIsInstance(session_id1, str)
    
    def test_sanitize_path(self):
        # パス正規化のテスト
        dangerous_path = "../../../etc/passwd"
        safe_path = sanitize_path(dangerous_path)
        self.assertNotIn('..', safe_path)
        
        # 絶対パスのテスト
        abs_path = "/absolute/path/file.txt"
        safe_path = sanitize_path(abs_path)
        self.assertFalse(os.path.isabs(safe_path))
    
    def test_validate_segment_parameters_valid(self):
        # 有効なパラメータのテスト
        is_valid, error = validate_segment_parameters(60, 'seconds')
        self.assertTrue(is_valid)
        self.assertIsNone(error)
        
        is_valid, error = validate_segment_parameters(10, 'megabytes')
        self.assertTrue(is_valid)
        self.assertIsNone(error)
    
    def test_validate_segment_parameters_invalid(self):
        # 無効なパラメータのテスト
        is_valid, error = validate_segment_parameters(-1, 'seconds')
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)
        
        is_valid, error = validate_segment_parameters(5000, 'seconds')
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)
        
        is_valid, error = validate_segment_parameters(10, 'invalid_type')
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)

if __name__ == '__main__':
    unittest.main()
