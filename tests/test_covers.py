import unittest
import tempfile
import os
from pathlib import Path
from PIL import Image

from core.utils.cover_manager import CoverManager

class TestCoverManager(unittest.TestCase):
    """Verifies universal cover generation, optimization, and fallback behaviors."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generate_typographic_cover(self):
        """Validates that typographic cover creates a valid, optimized 600x900 progressive JPEG."""
        output_file = self.temp_path / "test_cover.jpg"
        success = CoverManager._generate_typographic_cover(
            output_path=output_file,
            title="Clean Architecture in Modern Python",
            author="Robert C. Martin",
            file_type="DOCUMENT"
        )
        self.assertTrue(success, "Typographic cover generation should succeed.")
        self.assertTrue(output_file.exists(), "Output cover image file should exist on disk.")
        self.assertGreater(output_file.stat().st_size, 5000, "Cover image must have content.")

        # Validate image properties
        with Image.open(output_file) as img:
            self.assertEqual(img.format, "JPEG")
            self.assertEqual(img.size, (CoverManager.TARGET_WIDTH, CoverManager.TARGET_HEIGHT))

    def test_optimize_and_save_image(self):
        """Ensures that arbitrary PIL images (RGBA, large dimensions) are standardized and constrained."""
        # Create arbitrary large RGBA image
        large_rgba = Image.new("RGBA", (1600, 2400), (255, 0, 0, 128))
        output_file = self.temp_path / "optimized_cover.jpg"

        saved = CoverManager._optimize_and_save_image(large_rgba, output_file)
        self.assertTrue(saved)
        self.assertTrue(output_file.exists())

        with Image.open(output_file) as img:
            self.assertEqual(img.format, "JPEG")
            self.assertLessEqual(img.width, CoverManager.TARGET_WIDTH)
            self.assertLessEqual(img.height, CoverManager.TARGET_HEIGHT)

    def test_extract_or_generate_cover_text_file(self):
        """Verifies that plain text or markdown files automatically receive an elegant front cover."""
        sample_txt = self.temp_path / "sample.txt"
        sample_txt.write_text("Introduction to Machine Learning Lecture Notes", encoding="utf-8")

        output_cover = self.temp_path / "cover.jpg"
        result = CoverManager.extract_or_generate_cover(
            file_path=sample_txt,
            output_path=output_cover,
            title="Intro to ML",
            author="Prof. Alan Turing",
            file_type="TXT"
        )
        self.assertTrue(result)
        self.assertTrue(output_cover.exists())
        self.assertGreater(output_cover.stat().st_size, 5000)

if __name__ == "__main__":
    unittest.main()
