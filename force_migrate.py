import asyncio
import os
import uuid
import json
from pathlib import Path
from core.database.mongo_manager import mongo_db

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
BOOKS_DIR = BASE_DIR / 'data' / 'books'

async def force_migrate():
    print(f"📂 Scanning library at: {BOOKS_DIR}")
    
    if not BOOKS_DIR.exists():
        print("❌ 'data/books' folder not found!")
        return

    # 1. Initialize DB Connection
    await mongo_db.initialize()
    
    count = 0
    
    # 2. Iterate through every folder in data/books
    for book_folder in BOOKS_DIR.iterdir():
        if not book_folder.is_dir():
            continue
            
        book_id = book_folder.name
        print(f"   > Found folder: {book_id}")

        # Check for metadata, OR create it if missing
        metadata_path = book_folder / 'metadata.json'
        
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except:
                print(f"     ⚠️ Corrupt metadata for {book_id}, regenerating...")
                data = {}
        else:
            print(f"     ⚠️ No metadata for {book_id}, creating default...")
            data = {}

        # 3. FILL MISSING DATA (The Fix)
        # If data is missing, we use the folder name as the title
        if 'id' not in data: data['id'] = book_id
        if 'title' not in data: data['title'] = book_id.replace('_', ' ').title()
        if 'authors' not in data: data['authors'] = "Unknown Author"
        if 'subjects' not in data: data['subjects'] = ["Uncategorized"]
        if 'added_at' not in data: data['added_at'] = book_folder.stat().st_mtime
        
        # 4. Save to MongoDB
        success = await mongo_db.add_book_metadata(data)
        
        if success:
            print(f"     ✅ SAVED: {data['title']}")
            count += 1
        else:
            print(f"     ❌ Failed to save {book_id}")

    print(f"\n🎉 DONE! Registered {count} books into MongoDB.")

if __name__ == "__main__":
    try:
        asyncio.run(force_migrate())
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")