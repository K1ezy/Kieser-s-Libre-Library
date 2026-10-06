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

if __name__ == "__main__":
    unittest.main()
