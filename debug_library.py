import asyncio
import os
from pathlib import Path
from core.database.mongo_manager import mongo_db

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
BOOKS_DIR = BASE_DIR / 'data' / 'books'

async def run_diagnostics():
    print("🔍 --- STARTING DIAGNOSTICS ---")
    
    # 1. CHECK FOLDERS
    print(f"\n📂 Checking physical folder: {BOOKS_DIR}")
    if not BOOKS_DIR.exists():
        print("❌ CRITICAL: 'data/books' directory does not exist!")
        return
    
    physical_books = [f.name for f in BOOKS_DIR.iterdir() if f.is_dir()]
    print(f"   > Found {len(physical_books)} book folders on disk.")
    if len(physical_books) == 0:
        print("⚠️  WARNING: Your data/books folder is empty. Upload a book first!")
    else:
        print(f"   > First 3 folders: {physical_books[:3]}")

    # 2. CHECK DATABASE
    print("\n💾 Checking MongoDB Connection...")
    try:
        await mongo_db.initialize()
        db_count = await mongo_db.db['books'].count_documents({})
        print(f"   > MongoDB 'books' collection has: {db_count} documents.")
    except Exception as e:
        print(f"❌ CRITICAL: Database connection failed: {e}")
        return

    # 3. REPAIR (If needed)
    if db_count == 0 and len(physical_books) > 0:
        print("\n🛠️  DATABASE IS EMPTY BUT FILES EXIST. STARTING REPAIR...")
        
        saved_count = 0
        for book_id in physical_books:
            print(f"   > Registering: {book_id}")
            
            # Create minimal metadata
            data = {
                "id": book_id,
                "title": book_id.replace('_', ' ').title(),
                "authors": "Unknown Author",
                "subjects": ["Uncategorized"],
                "added_at": 1700000000
            }
            
            success = await mongo_db.add_book_metadata(data)
            if success: saved_count += 1
        
        print(f"✅ REPAIR COMPLETE. Added {saved_count} books to DB.")
        
    elif db_count > 0:
        print("\n✅ Database seems healthy. The issue might be the UI.")

    print("\n🔍 --- DIAGNOSTICS FINISHED ---")

if __name__ == "__main__":
    asyncio.run(run_diagnostics())