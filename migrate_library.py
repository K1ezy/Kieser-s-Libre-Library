import asyncio
import json
import os
from pathlib import Path
from core.database.mongo_manager import mongo_db

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
BOOKS_DIR = BASE_DIR / 'data' / 'books'

async def migrate_library():
    print(f"📂 Scanning library at: {BOOKS_DIR}")
    
    if not BOOKS_DIR.exists():
        print("❌ 'data/books' folder not found!")
        return

    # 1. Initialize DB Connection
    await mongo_db.initialize()
    
    count = 0
    updated = 0
    
    # 2. Iterate through every book folder
    for book_folder in BOOKS_DIR.iterdir():
        if not book_folder.is_dir():
            continue
            
        book_id = book_folder.name
        metadata_path = book_folder / 'metadata.json'
        
        if metadata_path.exists():
            try:
                # Read the JSON file
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Ensure the ID matches the folder name
                data['id'] = book_id
                
                # Add extra fields if missing
                if 'added_at' not in data:
                    data['added_at'] = book_folder.stat().st_mtime
                
                # Save to MongoDB
                success = await mongo_db.add_book_metadata(data)
                
                if success:
                    print(f"✅ Registered: {data.get('title', 'Unknown Title')}")
                    count += 1
                else:
                    print(f"⚠️  Skipped (DB Error): {book_id}")
                    
            except Exception as e:
                print(f"❌ Error reading {book_id}: {e}")
        else:
            print(f"⚠️  No metadata.json found for {book_id}, skipping.")

    print(f"\n🎉 MIGRATION COMPLETE!")
    print(f"   Processed: {count} books")

if __name__ == "__main__":
    asyncio.run(migrate_library())