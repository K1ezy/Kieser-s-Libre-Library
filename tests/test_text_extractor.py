import unittest
import tempfile
from pathlib import Path
from core.utils.text_extractor import extract_text_from_file

class TestTextExtractor(unittest.TestCase):
    """Verifies document parsing and safe fallbacks for missing or empty files."""

    def test_nonexistent_file_returns_empty(self):
        """Non-existent file should gracefully return an empty string without raising an exception."""
        result = extract_text_from_file("non_existent_file_12345.pdf")
        self.assertEqual(result, "")

    def test_empty_file_returns_empty(self):
        """Zero-byte file should return an empty string."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            temp_path = f.name
        try:
            result = extract_text_from_file(temp_path)
            self.assertEqual(result, "")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_plain_text_extraction(self):
        """Extracts content cleanly from a UTF-8 text file."""
        sample_content = "Hello, Libre-Library!\nThis is a unit test text sample."
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
            f.write(sample_content)
            temp_path = f.name
        try:
            result = extract_text_from_file(temp_path)
            self.assertEqual(result, sample_content)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_markdown_extraction(self):
        """Extracts content cleanly from a Markdown file."""
        sample_content = "# Header 1\n\nSome bullet points:\n- Point A\n- Point B"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False) as f:
            f.write(sample_content)
            temp_path = f.name
        try:
            result = extract_text_from_file(temp_path)
            self.assertEqual(result, sample_content)
        finally:
            Path(temp_path).unlink(missing_ok=True)

if __name__ == "__main__":
    unittest.main()
