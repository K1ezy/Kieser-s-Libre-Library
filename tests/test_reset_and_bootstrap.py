import unittest
import asyncio
import json
from pathlib import Path
import bcrypt

from core.database.mongo_manager import mongo_db
from tools.reset_dev_data import RESET_COLLECTIONS, PROTECTED_COLLECTIONS
from tools.bootstrap_admin import bootstrap_admin

class TestResetAndBootstrap(unittest.TestCase):
    """
    Validates the controlled development data reset safeguards,
    academic catalog preservation, and administrative bootstrap utility.
    """

    def test_reset_allowlist_and_protections(self):
        """Verifies that protected collections (books, vectors) are never in RESET_COLLECTIONS."""
        for protected in PROTECTED_COLLECTIONS:
            self.assertNotIn(protected, RESET_COLLECTIONS, f"Collection '{protected}' must NEVER be in RESET_COLLECTIONS!")
            
        # Ensure mandatory reset collections are tracked
        self.assertIn("users", RESET_COLLECTIONS)
        self.assertIn("chat_history", RESET_COLLECTIONS)
        self.assertIn("reading_progress", RESET_COLLECTIONS)

    def test_backup_manifest_integrity(self):
        """Verifies that at least one backup exists and contains a valid manifest and book records."""
        backup_root = Path(__file__).resolve().parent.parent / "backups"
        self.assertTrue(backup_root.exists(), "Backups directory must exist.")
        
        backup_dirs = sorted(list(backup_root.glob("backup_*")))
        self.assertGreater(len(backup_dirs), 0, "At least one backup must exist.")
        
        latest_backup = backup_dirs[-1]
        manifest_file = latest_backup / "manifest.json"
        self.assertTrue(manifest_file.exists(), "Backup must contain manifest.json")
        
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)
            
        self.assertIn("collections", manifest)
        self.assertIn("books", manifest["collections"])
        self.assertEqual(manifest["collections"]["books"]["count"], 97)
        self.assertIn("vectors", manifest["collections"])
        self.assertEqual(manifest["collections"]["vectors"]["count"], 695)

    def test_bootstrap_admin_validation(self):
        """Verifies input validation on the bootstrap utility."""
        loop = asyncio.new_event_loop()
        try:
            # Short username (< 3 chars)
            res1 = loop.run_until_complete(bootstrap_admin("ab", "admin@nemsu.edu.ph", "ValidPass123!"))
            self.assertFalse(res1)
            
            # Invalid email
            res2 = loop.run_until_complete(bootstrap_admin("admin_test", "not-an-email", "ValidPass123!"))
            self.assertFalse(res2)
            
            # Short password (< 8 chars)
            res3 = loop.run_until_complete(bootstrap_admin("admin_test", "admin@nemsu.edu.ph", "short"))
            self.assertFalse(res3)
        finally:
            loop.close()

    def test_database_preservation_and_bootstrapped_admin(self):
        """Verifies MongoDB contains 97 books, 695 vectors, and the bootstrapped admin account."""
        async def verify_db():
            await mongo_db.initialize()
            if mongo_db.db is None:
                self.skipTest("MongoDB not available")

            # Verify Academic Catalog Preservation
            book_count = await mongo_db.db['books'].count_documents({})
            self.assertGreaterEqual(book_count, 97, f"Official books collection must have at least 97 items, found {book_count}")

            vector_count = await mongo_db.db['vectors'].count_documents({})
            self.assertGreaterEqual(vector_count, 695, f"Vector embeddings collection must have at least 695 items, found {vector_count}")

            # Verify Bootstrapped Administrator Account
            admin_users = await mongo_db.get_users_by_identifier("admin")
            self.assertGreaterEqual(len(admin_users), 1, "Admin user must exist after bootstrap.")
            
            admin_user = admin_users[0]
            self.assertEqual(admin_user.get("role"), "admin")
            self.assertEqual(admin_user.get("email"), "admin@nemsu.edu.ph")
            
            # Verify password hash (supports LibreAdmin2026! or custom admin123)
            hashed_pwd = admin_user.get("hashed_password")
            is_valid = (
                bcrypt.checkpw("LibreAdmin2026!".encode('utf-8'), hashed_pwd.encode('utf-8')) or
                bcrypt.checkpw("admin123".encode('utf-8'), hashed_pwd.encode('utf-8'))
            )
            self.assertTrue(is_valid, "Password hash must match standard administrator password.")

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(verify_db())
        finally:
            loop.close()

if __name__ == '__main__':
    unittest.main()
