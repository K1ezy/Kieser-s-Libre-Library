import unittest
from datetime import timedelta
import bcrypt
from core.auth.jwt_handler import create_access_token, verify_token

class TestAuth(unittest.TestCase):
    """Verifies JWT token issuance, verification, and expiration behavior."""

    def test_create_and_verify_token(self):
        """A freshly generated token should decode to the original payload claims."""
        payload = {"sub": "user_123", "username": "alice", "role": "admin"}
        token = create_access_token(payload)
        
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 20)

        decoded = verify_token(token)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.get("sub"), "user_123")
        self.assertEqual(decoded.get("username"), "alice")
        self.assertEqual(decoded.get("role"), "admin")
        self.assertIn("exp", decoded)

    def test_expired_token_rejected(self):
        """Tokens with negative expires_delta must fail verification."""
        payload = {"sub": "user_expired"}
        expired_token = create_access_token(payload, expires_delta=timedelta(seconds=-10))

        decoded = verify_token(expired_token)
        self.assertIsNone(decoded, "Expired token must return None upon verification.")

    def test_tampered_token_rejected(self):
        """Altering any character of the token signature must fail verification."""
        token = create_access_token({"sub": "user_legit"})
        tampered_token = token[:-4] + "xxxx"

        decoded = verify_token(tampered_token)
        self.assertIsNone(decoded, "Tampered token must return None upon verification.")

    def test_empty_or_malformed_token(self):
        """Empty or non-JWT strings should safely return None without throwing."""
        self.assertIsNone(verify_token(""))
        self.assertIsNone(verify_token("invalid.token.structure"))

    def test_bcrypt_password_hashing(self):
        """Validates that bcrypt passwords can be hashed and verified correctly."""
        password = "SuperSecretPassword123!"
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # Correct password
        self.assertTrue(bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8')))

        # Incorrect password
        self.assertFalse(bcrypt.checkpw("WrongPassword!".encode('utf-8'), hashed.encode('utf-8')))

    def test_get_current_user_role_and_has_role(self):
        """Validates role retrieval, normalization, and hierarchical permission checks."""
        from unittest.mock import patch
        from core.auth.jwt_handler import get_current_user_role, has_role

        mock_user_dict = {}
        with patch('core.auth.jwt_handler.app') as mock_app:
            mock_app.storage.user = mock_user_dict

            # 1. Default fallback when no role in storage
            self.assertEqual(get_current_user_role(), "student")
            self.assertTrue(has_role(["student"]))
            self.assertFalse(has_role(["admin", "librarian"]))

            # 2. Legacy 'user' maps to 'student'
            mock_user_dict['role'] = 'user'
            self.assertEqual(get_current_user_role(), "student")

            # 3. Faculty role
            mock_user_dict['role'] = 'Faculty'
            self.assertEqual(get_current_user_role(), "faculty")
            self.assertTrue(has_role(["faculty", "librarian", "admin"]))
            self.assertFalse(has_role(["admin"]))

            # 4. Librarian role
            mock_user_dict['role'] = 'LIBRARIAN'
            self.assertEqual(get_current_user_role(), "librarian")
            self.assertTrue(has_role(["librarian", "admin"]))

            # 5. Admin role
            mock_user_dict['role'] = 'admin'
            self.assertEqual(get_current_user_role(), "admin")
            self.assertTrue(has_role(["admin"]))

if __name__ == "__main__":
    unittest.main()

