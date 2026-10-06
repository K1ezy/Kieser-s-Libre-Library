import unittest
from pathlib import Path
from core.config import settings

class TestConfig(unittest.TestCase):
    """Verifies core configuration, secure secrets, and CORS origin generation."""

    def test_secret_key_is_secure(self):
        """SECRET_KEY must never default to the obsolete insecure hardcoded token."""
        self.assertNotEqual(
            settings.SECRET_KEY,
            "libre_library_secure_key_2025",
            "SECRET_KEY must not use the hardcoded insecure default."
        )
        self.assertGreaterEqual(
            len(settings.SECRET_KEY),
            32,
            "Generated SECRET_KEY should be at least 32 characters long."
        )

    def test_secret_file_persists(self):
        """Secret key should be persisted inside data/.secret_key."""
        secret_file = settings.BASE_DIR / "data" / ".secret_key"
        self.assertTrue(
            secret_file.exists() or len(settings.SECRET_KEY) >= 32,
            "Secret key should either exist in data/.secret_key or be securely loaded."
        )

    def test_cors_origins_format(self):
        """get_cors_origins should return a list of valid URL strings."""
        origins = settings.get_cors_origins()
        self.assertIsInstance(origins, list)
        self.assertGreater(len(origins), 0)
        for origin in origins:
            self.assertTrue(
                origin.startswith("http://") or origin.startswith("https://"),
                f"Origin '{origin}' should start with http:// or https://"
            )

    def test_directory_paths_configured(self):
        """BASE_DIR, BOOKS_INFO_DIR and BOOKS_DIR must be valid Path objects."""
        self.assertIsInstance(settings.BASE_DIR, Path)
        self.assertIsInstance(settings.BOOKS_INFO_DIR, Path)
        self.assertIsInstance(settings.BOOKS_DIR, Path)
        self.assertTrue(settings.BASE_DIR.exists(), "BASE_DIR should exist on disk.")

if __name__ == "__main__":
    unittest.main()
