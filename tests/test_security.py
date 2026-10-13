import unittest
import re
from pathlib import Path
from core.config import settings
from core.services.ingestion_service import IngestionService
from core.utils.security_utils import is_valid_book_id, SAFE_BOOK_ID_PATTERN

class TestSecurity(unittest.TestCase):
    """Verifies security controls against path traversal, file manipulation, and privilege escalation."""

    def setUp(self):
        self.id_regex = SAFE_BOOK_ID_PATTERN
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
            "book\x00nullbyte",
            "..",
            ".",
            "book/../other",
            "   ",
            ""
        ]
        for bad_id in malicious_ids:
            self.assertFalse(
                is_valid_book_id(bad_id),
                f"Malicious ID '{bad_id}' must be rejected by ID validator."
            )

    def test_book_id_regex_accepts_valid_ids(self):
        """Valid book IDs containing alphanumerics, underscores, dashes, and catalog formatting must pass."""
        valid_ids = [
            "book_123",
            "Clean-Code-99",
            "python_guide",
            "42",
            "ABC_def-123_XYZ",
            "The_Complete_Witcher__The_Last___Andrzej_Sapkowski_(1)_ba93",
            "inventwithpython_3rd_(1)_6c1d",
            "Moby_Dick;_Or,_The_Whale_by_Herman_Melville_5da7",
            "The_Little_Prince_Antoine-de-Saint-Exupér-y_e635",
            "Wuthering-Heights_Emily_Brontë_dfcd"
        ]
        for good_id in valid_ids:
            self.assertTrue(
                is_valid_book_id(good_id),
                f"Valid ID '{good_id}' should be accepted by ID validator."
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
