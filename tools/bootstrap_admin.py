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


async def bootstrap_admin(username: str, email: str, password: str, setup_secret: str = None, role: str = "admin") -> bool:
    # Optional setup-secret check if configured
    configured_secret = getattr(settings, 'ADMIN_SETUP_SECRET', None)
    if configured_secret and setup_secret != configured_secret:
        print("❌ Error: Invalid setup secret.")
        return False

    clean_user = username.strip()
    clean_email = email.strip().lower()
    target_role = (role or "admin").strip().lower()

    if target_role not in ('admin', 'librarian', 'faculty', 'student'):
        print(f"❌ Error: Invalid role '{target_role}'. Must be admin, librarian, faculty, or student.")
        return False

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
        # Update user role and password safely
        await mongo_db.db['users'].update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "role": target_role,
                "hashed_password": hashed,
                "email": clean_email,
                "username": clean_user,
                "updated_at": time.time()
            }}
        )
        print(f"✅ Existing user '{clean_user}' ({clean_email}) updated and role set to {target_role.upper()}.")
        return True
    else:
        # Create fresh user account with target role
        user_doc = {
            "id": str(uuid.uuid4()),
            "username": clean_user,
            "email": clean_email,
            "hashed_password": hashed,
            "role": target_role,
            "type": "account",
            "created_at": time.time(),
            "last_login": None
        }
        await mongo_db.db['users'].insert_one(user_doc)
        print(f"✅ Created fresh account: '{clean_user}' ({clean_email}) [Role: {target_role.upper()}].")
        return True


def main():
    parser = argparse.ArgumentParser(description="Libre-Library Account Bootstrap & Provisioning Tool")
    parser.add_argument("--username", help="Account username")
    parser.add_argument("--email", help="Account email address")
    parser.add_argument("--password", help="Account password (leave blank for interactive prompt)")
    parser.add_argument("--role", default="admin", choices=["admin", "librarian", "faculty", "student"], help="Role to assign (default: admin)")
    parser.add_argument("--setup-secret", help="Optional setup secret")

    args = parser.parse_args()

    username = args.username
    if not username:
        username = input("Enter Username: ").strip()

    email = args.email
    if not email:
        email = input("Enter Email: ").strip()

    password = args.password
    if not password:
        password = getpass.getpass("Enter Password (min 8 chars): ").strip()
        confirm = getpass.getpass("Confirm Password: ").strip()
        if password != confirm:
            print("❌ Error: Passwords do not match.")
            sys.exit(1)

    import asyncio
    success = asyncio.run(bootstrap_admin(username, email, password, args.setup_secret, role=args.role))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
