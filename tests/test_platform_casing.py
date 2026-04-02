import unittest
from unittest.mock import patch
import sys
import os
import pathlib
from file_cortex_core.security import PathValidator

class TestPlatformCasing(unittest.TestCase):
    def test_norm_path_windows(self):
        with patch('sys.platform', 'win32'):
            # In Windows mode, it should lowercase
            p = "C:/Users/Test/Documents"
            norm = PathValidator.norm_path(p)
            self.assertEqual(norm, "c:/users/test/documents")
            
            # Test with backslashes
            p2 = "C:\\Users\\Test\\Documents"
            norm2 = PathValidator.norm_path(p2)
            self.assertEqual(norm2, "c:/users/test/documents")

    def test_norm_path_linux(self):
        with patch('sys.platform', 'linux'):
            # In Linux mode, it should preserve case
            p = "/home/User/Documents"
            norm = PathValidator.norm_path(p)
            # abspath might change current relative path, but for absolute it stays same
            # We use abspath in norm_path so we expect it to be absolute
            expected = os.path.abspath(p).replace('\\', '/')
            self.assertEqual(norm, expected)
            self.assertIn("User", norm) # Casing preserved

    def test_norm_path_macos(self):
        with patch('sys.platform', 'darwin'):
            p = "/Users/User/Desktop"
            norm = PathValidator.norm_path(p)
            expected = os.path.abspath(p).replace('\\', '/')
            self.assertEqual(norm, expected)
            self.assertIn("Desktop", norm)

if __name__ == '__main__':
    unittest.main()
