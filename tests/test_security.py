import unittest
import re
from pathlib import Path
from core.config import settings
from core.services.ingestion_service import IngestionService

class TestSecurity(unittest.TestCase):
    """Verifies security controls against path traversal, file manipulation, and privilege escalation."""

    def setUp(self):
        self.id_regex = re.compile(r"^[a-zA-Z0-9_-]+$")
        self.books_dir = settings.BOOKS_INFO_DIR

    def test_book_id_regex_blocks_path_traversal(self):
        """Malicious book IDs with directory navigation sequences must fail validation."""
        malicious_ids = [
            "../../etc/passwd",
            "../secret.txt",
            "..\\..\\windows\\system32",
            "/absolute/root/path",
            "book_id/subfolder",
            "book;rm -rf /",
            "book`whoami`",
            "book\x00nullbyte"
        ]
        for bad_id in malicious_ids:
            self.assertIsNone(
                self.id_regex.match(bad_id),
                f"Malicious ID '{bad_id}' must be rejected by ID regex."
            )

    def test_book_id_regex_accepts_valid_ids(self):
        """Valid book IDs containing alphanumerics, underscores, and dashes must pass."""
        valid_ids = [
            "book_123",
            "Clean-Code-99",
            "python_guide",
            "42",
            "ABC_def-123_XYZ"
        ]
        for good_id in valid_ids:
            self.assertIsNotNone(
                self.id_regex.match(good_id),
                f"Valid ID '{good_id}' should be accepted by ID regex."
            )

    def test_path_confinement_under_books_dir(self):
        """Ensures Path.is_relative_to correctly prevents paths escaping the books directory."""
        valid_target = (self.books_dir / "valid_book_folder").resolve()
        self.assertTrue(
            valid_target.is_relative_to(self.books_dir),
            "Target folder inside books_dir must pass is_relative_to check."
        )

        escaped_target = (self.books_dir / ".." / "system_file").resolve()
        self.assertFalse(
            escaped_target.is_relative_to(self.books_dir),
            "Escaped path outside books_dir must fail is_relative_to check."
        )

    def test_filename_sanitization(self):
        """IngestionService._sanitize_filename must strip directory separators."""
        service = IngestionService()
        dirty_names = [
            "../../malicious.pdf",
            "..\\..\\system32\\calc.exe",
            "foo/bar/baz.epub",
            "safe_book.pdf"
        ]
        for dirty in dirty_names:
            clean = service._sanitize_filename(dirty)
            self.assertNotIn("/", clean, "Sanitized filename must not contain forward slash.")
            self.assertNotIn("\\", clean, "Sanitized filename must not contain backslash.")
            self.assertNotIn("..", clean, "Sanitized filename must not contain '..'.")

if __name__ == "__main__":
    unittest.main()
