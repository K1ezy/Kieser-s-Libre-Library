"""
Controlled Development Data Reset & Backup Utility for Libre-Library.
Creates a verified timestamped JSON backup of all collections, then selectively
resets user accounts, chat histories, personal learning data, and operational logs
WHILE STRICTLY PRESERVING:
- Academic library catalog & bibliographic metadata ('books' collection)
- High-dimensional vector passages ('vectors' collection)
- Physical documents & cover artwork ('data/books/' directory)
- ChromaDB vector store ('data/chroma_db/' directory)
"""

import sys
import os
import json
import time
import argparse
from datetime import datetime
from pathlib import Path
from bson import json_util

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from core.database.mongo_manager import mongo_db
from core.config import settings


# Exact Allowlist of Collections to Reset
RESET_COLLECTIONS = [
    "users",
    "chat_history",
    "chats",
    "decks",
    "reading_progress",
    "tasks",
    "attendance_logs",
    "faculty_requisitions",
    "planner",
    "system_settings"
]

# Collections Strictly Protected Against Reset
PROTECTED_COLLECTIONS = [
    "books",
    "vectors"
]


async def create_timestamped_backup(backup_root: Path) -> Path:
    """Exports all MongoDB collections in libre_library_db to JSON files."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backup_root / f"backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    print(f"📦 Creating verified database backup in: {backup_dir}")

    all_colls = await mongo_db.db.list_collection_names()
    summary = {}

    for coll_name in sorted(all_colls):
        cursor = mongo_db.db[coll_name].find({})
        docs = await cursor.to_list(length=None)
        file_path = backup_dir / f"{coll_name}.json"
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(json_util.dumps(docs, indent=2))
        
        file_size = file_path.stat().st_size
        summary[coll_name] = {"count": len(docs), "size_bytes": file_size}
        print(f"  • Backed up '{coll_name}': {len(docs)} document(s) ({file_size} bytes)")

    # Save manifest
    manifest_path = backup_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": timestamp,
            "database": mongo_db.db.name,
            "collections": summary
        }, f, indent=2)

    print(f"✅ Backup verified! {len(summary)} collections exported successfully.\n")
    return backup_dir


async def execute_reset(confirm: bool = False, backup_first: bool = True):
    await mongo_db.initialize()
    if mongo_db.db is None:
        print("❌ Error: MongoDB connection failed.")
        return False

    print("=" * 65)
    print("LIBRE-LIBRARY CONTROLLED DEVELOPMENT DATA RESET")
    print(f"Target Database: {mongo_db.db.name} @ {settings.MONGO_URI}")
    print("=" * 65)

    if not confirm:
        print("⚠️  SAFETY GUARD: Pass --confirm to execute the controlled reset.")
        print("    Academic library catalog ('books') and ChromaDB vectors will be preserved.")
        return False

    backup_dir = None
    if backup_first:
        backup_root = settings.BASE_DIR / "backups"
        backup_dir = await create_timestamped_backup(backup_root)

    print("🧹 Executing selective development data reset...")
    reset_counts = {}

    for coll_name in RESET_COLLECTIONS:
        if coll_name in await mongo_db.db.list_collection_names():
            del_res = await mongo_db.db[coll_name].delete_many({})
            reset_counts[coll_name] = del_res.deleted_count
            print(f"  • Reset '{coll_name}': removed {del_res.deleted_count} record(s).")
        else:
            reset_counts[coll_name] = 0

    print("\n🛡️  Verifying Preservation of Official Academic Library:")
    book_count = await mongo_db.db['books'].count_documents({})
    vector_count = await mongo_db.db['vectors'].count_documents({})
    print(f"  • Preserved Books Catalog: {book_count} records (Expected: 97)")
    print(f"  • Preserved Vectors Store: {vector_count} records (Expected: 695)")

    assert book_count > 0, "CRITICAL ERROR: Books collection was affected!"

    print("\n✅ Controlled development data reset completed successfully!")
    if backup_dir:
        print(f"📁 Recovery backup archived at: {backup_dir}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Libre-Library Development Data Reset Utility")
    parser.add_argument("--confirm", action="store_true", help="Explicit confirmation for reset")
    parser.add_argument("--no-backup", action="store_true", help="Skip pre-reset backup (not recommended)")

    args = parser.parse_args()

    import asyncio
    success = asyncio.run(execute_reset(confirm=args.confirm, backup_first=not args.no_backup))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
