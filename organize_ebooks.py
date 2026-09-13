import asyncio
import os
import shutil
import uuid
import urllib.parse
import json
from pathlib import Path
from core.database.mongo_manager import mongo_db

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
# 1. Source: Where your files are stuck (The old folder)
SOURCE_DIR = BASE_DIR / 'E-Books'
# 2. Destination: Where the app actually looks (The new folder)
TARGET_DIR = BASE_DIR / 'data' / 'books'

async def full_migration_and_repair():
    print(f"🚀 STARTING MIGRATION: {SOURCE_DIR} -> {TARGET_DIR}")
    
    # Ensure directories exist
    if not SOURCE_DIR.exists():
        print(f"⚠️  Source folder '{SOURCE_DIR}' not found. Creating it...")
        SOURCE_DIR.mkdir(parents=True, exist_ok=True)
        
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize Database
    print("💾 Connecting to Database...")
    await mongo_db.initialize()
    
    # Clear old records to prevent duplicates/ghosts
    await mongo_db.db['books'].delete_many({})
    print("🧹 Database cleared. Re-indexing fresh.")

    count_moved = 0
    count_indexed = 0

    # ==========================================
    # PHASE 1: MIGRATE FROM E-BOOKS (The Fix)
    # ==========================================
    print("\n📦 PHASE 1: Migrating files from E-Books...")
    
    # Iterate over everything in E-Books
    for item in SOURCE_DIR.iterdir():
        # Skip hidden files
        if item.name.startswith('.'): continue
        
        # A. Handle Loose Files (e.g., "Romeo.pdf")
        if item.is_file() and item.suffix.lower() in ['.pdf', '.epub', '.docx', '.pptx', '.txt', '.md']:
            print(f"   > Moving File: {item.name}")
            
            # Create a clean ID
            safe_name = item.stem.replace(" ", "_").replace(".", "_").replace("-", "_")
            book_id = f"{safe_name}_{str(uuid.uuid4())[:4]}"
            
            # Create Destination Folder
            dest_folder = TARGET_DIR / book_id
            dest_folder.mkdir(parents=True, exist_ok=True)
            
            # MOVE the file
            shutil.move(str(item), str(dest_folder / item.name))
            count_moved += 1
            
            # Generate Metadata immediately
            await register_book(dest_folder, item.name, book_id)
            count_indexed += 1

        # B. Handle Existing Folders in E-Books (e.g., "E-Books/Romeo/")
        elif item.is_dir():
            print(f"   > Moving Folder: {item.name}")
            
            # Generate ID (use folder name if clean, else new ID)
            book_id = item.name
            dest_folder = TARGET_DIR / book_id
            
            # Handle collision
            if dest_folder.exists():
                book_id = f"{item.name}_{str(uuid.uuid4())[:4]}"
                dest_folder = TARGET_DIR / book_id
            
            # MOVE the folder
            shutil.move(str(item), str(dest_folder))
            count_moved += 1
            
            # Find the content file inside to register it
            content_file = find_main_file(dest_folder)
            if content_file:
                await register_book(dest_folder, content_file.name, book_id)
                count_indexed += 1

    # ==========================================
    # PHASE 2: INDEX DATA/BOOKS (Re-indexing)
    # ==========================================
    print("\n🔍 PHASE 2: Scanning data/books for existing content...")
    
    for folder in TARGET_DIR.iterdir():
        if not folder.is_dir(): continue
        
        # Check if we already indexed this in Phase 1 (optimization)
        # But for safety, we just check if metadata exists, if not, create it.
        if not (folder / 'metadata.json').exists():
            content_file = find_main_file(folder)
            if content_file:
                print(f"   > Repairing metadata for: {folder.name}")
                await register_book(folder, content_file.name, folder.name)
                count_indexed += 1
        else:
            # Load existing metadata and ensure it's in DB
            try:
                with open(folder / 'metadata.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                await mongo_db.add_book_metadata(data)
                # Don't increment count_indexed here to avoid double counting Phase 1
            except:
                pass

    print(f"\n🎉 DONE! Moved {count_moved} items. Index contains {count_indexed} books.")
    print("👉 NOW: Restart your app ('python main.py') and the Reader will work.")

def find_main_file(folder_path):
    """Helper to find the first readable book file in a folder."""
    for f in folder_path.iterdir():
        if f.suffix.lower() in ['.pdf', '.epub', '.docx', '.pptx', '.txt', '.md']:
            return f
    return None

async def register_book(folder_path, filename, book_id):
    """Creates metadata.json and saves to MongoDB."""
    
    # 1. Smart Title/Author Extraction
    clean_name = filename.rsplit('.', 1)[0].replace("_", " ").replace("-", " ").title()
    title = clean_name
    author = "Unknown"
    
    # Try to parse "Title by Author"
    if " By " in clean_name:
        parts = clean_name.split(" By ")
        title = parts[0].strip()
        author = parts[1].strip()
    
    # 2. Build Metadata
    metadata = {
        "id": book_id,
        "title": title,
        "authors": [author],
        "subjects": ["Uncategorized"],
        "added_at": os.path.getctime(folder_path / filename),
        "formats": {
            # This path format matches what main.py and reader_interface.py expect
            Path(filename).suffix.lower().replace('.', ''): f"/static_books/{book_id}/{urllib.parse.quote(filename)}"
        }
    }
    
    # 3. Save JSON
    with open(folder_path / 'metadata.json', 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
        
    # 4. Save to DB
    await mongo_db.add_book_metadata(metadata)

if __name__ == "__main__":
    asyncio.run(full_migration_and_repair())