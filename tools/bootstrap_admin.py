"""
Secure Administrator Bootstrap Utility for Libre-Library.
Allows authorized administrators to initialize or restore administrator credentials
following a controlled development-data reset.

Usage:
    python tools/bootstrap_admin.py --username admin --email admin@nemsu.edu.ph --password <SECURE_PASSWORD>
    or interactively:
    python tools/bootstrap_admin.py
"""

import sys
import argparse
import getpass
import re
import time
import uuid
from pathlib import Path
import bcrypt

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from core.database.mongo_manager import mongo_db
from core.config import settings


async def bootstrap_admin(username: str, email: str, password: str, setup_secret: str = None) -> bool:
    # Optional setup-secret check if configured
    configured_secret = getattr(settings, 'ADMIN_SETUP_SECRET', None)
    if configured_secret and setup_secret != configured_secret:
        print("❌ Error: Invalid setup secret.")
        return False

    clean_user = username.strip()
    clean_email = email.strip().lower()

    if len(clean_user) < 3:
        print("❌ Error: Username must be at least 3 characters.")
        return False

    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", clean_email):
        print("❌ Error: Invalid email format.")
        return False

    if len(password) < 8:
        print("❌ Error: Password must be at least 8 characters.")
        return False

    await mongo_db.initialize()
    if mongo_db.db is None:
        print("❌ Error: Could not connect to MongoDB.")
        return False

    # Check if user already exists
    existing = await mongo_db.db['users'].find_one({
        "$or": [
            {"username": clean_user},
            {"email": clean_email}
        ]
    })

    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')

    if existing:
        # Promote and update password safely
        user_id = existing.get("id") or str(existing.get("_id"))
        await mongo_db.db['users'].update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "role": "admin",
                "hashed_password": hashed,
                "email": clean_email,
                "username": clean_user,
                "updated_at": time.time()
            }}
        )
        print(f"✅ Existing user '{clean_user}' ({clean_email}) updated and promoted to ADMIN.")
        return True
    else:
        # Create fresh admin user
        user_doc = {
            "id": str(uuid.uuid4()),
            "username": clean_user,
            "email": clean_email,
            "hashed_password": hashed,
            "role": "admin",
            "type": "account",
            "created_at": time.time(),
            "last_login": None
        }
        await mongo_db.db['users'].insert_one(user_doc)
        print(f"✅ Created fresh Administrator account: '{clean_user}' ({clean_email}) [Role: ADMIN].")
        return True


def main():
    parser = argparse.ArgumentParser(description="Libre-Library Secure Admin Bootstrap Tool")
    parser.add_argument("--username", help="Admin username")
    parser.add_argument("--email", help="Admin email address")
    parser.add_argument("--password", help="Admin password (leave blank for interactive prompt)")
    parser.add_argument("--setup-secret", help="Optional setup secret")

    args = parser.parse_args()

    username = args.username
    if not username:
        username = input("Enter Admin Username: ").strip()

    email = args.email
    if not email:
        email = input("Enter Admin Email: ").strip()

    password = args.password
    if not password:
        password = getpass.getpass("Enter Admin Password (min 8 chars): ").strip()
        confirm = getpass.getpass("Confirm Admin Password: ").strip()
        if password != confirm:
            print("❌ Error: Passwords do not match.")
            sys.exit(1)

    import asyncio
    success = asyncio.run(bootstrap_admin(username, email, password, args.setup_secret))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
