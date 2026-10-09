"""
Tools: Universal Cover Extraction & Optimization Utility for Libre-Library
Generates front page covers and thumbnails for all PDF, EPUB, PPTX, DOCX, and TXT books.
Synchronizes MongoDB with generated cover URLs and metadata.
"""

import sys
import asyncio
from pathlib import Path

# Force UTF-8 stdout if needed on Windows
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.database.mongo_manager import mongo_db
from core.utils.cover_manager import cover_manager

async def main():
    print("=" * 65)
    print(" [LIBRE-LIBRARY] UNIVERSAL COVER GENERATOR & SYNC")
    print("=" * 65)
    
    print("\n[1/2] Connecting to MongoDB...")
    await mongo_db.initialize()
    print("      MongoDB connected.")

    print("\n[2/2] Scanning books and extracting/generating missing covers...")
    stats = await cover_manager.batch_generate_missing_covers(sync_mongodb=True)
    
    print("\n" + "=" * 65)
    print(" COVER GENERATION REPORT:")
    print(f"    - Total missing candidates processed: {stats['total']}")
    print(f"    - Successfully generated & saved:     {stats['success']}")
    print(f"    - Failed / corrupt source files:       {stats['failed']}")
    print(f"    - Previously existing / skipped:       {stats['skipped']}")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())
