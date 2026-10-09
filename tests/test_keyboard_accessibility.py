import unittest
from pathlib import Path
from core.config import settings
from ui.theme import GLOBAL_THEME_STYLES

class TestKeyboardAccessibility(unittest.TestCase):
    """Verifies keyboard navigation script, styles, shortcuts, and accessibility hooks."""

    def test_keyboard_script_exists_on_disk(self):
        """Verifies that static/js/keyboard_navigation.js exists and has content."""
        js_path = settings.BASE_DIR / "static" / "js" / "keyboard_navigation.js"
        self.assertTrue(js_path.exists(), "keyboard_navigation.js must exist on disk.")
        self.assertGreater(js_path.stat().st_size, 2000, "Script must contain complete accessibility engine.")

    def test_theme_includes_accessibility_assets(self):
        """Ensures that global theme imports the script and high-contrast accessibility styles."""
        self.assertIn("keyboard_navigation.js", GLOBAL_THEME_STYLES, "Theme must load keyboard navigation script.")
        self.assertIn(":focus-visible", GLOBAL_THEME_STYLES, "Theme must include WCAG :focus-visible rules.")
        self.assertIn("libre-chord-indicator", GLOBAL_THEME_STYLES, "Theme must style chord navigation pill.")
        self.assertIn("libre-shortcuts-modal", GLOBAL_THEME_STYLES, "Theme must style shortcuts cheat sheet modal.")

    def test_script_contains_vital_shortcuts(self):
        """Validates that key shortcuts and scroll bindings are registered in the JS engine."""
        js_path = settings.BASE_DIR / "static" / "js" / "keyboard_navigation.js"
        content = js_path.read_text(encoding="utf-8")
        
        # Scrolling keys
        self.assertIn("scrollContainerBy", content)
        self.assertIn("scrollToPosition", content)
        self.assertIn("ArrowDown", content)
        self.assertIn("ArrowUp", content)
        self.assertIn("PageDown", content)
        self.assertIn("PageUp", content)

        # Chords & Navigation
        self.assertIn("showChordIndicator", content)
        self.assertIn("focusSearchInput", content)
        self.assertIn("toggleHelpModal", content)
        self.assertIn("Escape", content)

if __name__ == "__main__":
    unittest.main()
