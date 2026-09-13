import shutil
import json
from pathlib import Path

DATA_DIR = Path("data/books").resolve()

def clean_library():
    print("🧹 LIBRARY CLEANER: INITIALIZED")
    
    if not DATA_DIR.exists():
        print("❌ Data directory not found.")
        return

    deleted_count = 0
    
    # Iterate through all book folders
    for book_folder in DATA_DIR.iterdir():
        if not book_folder.is_dir():
            continue
            
        metadata_file = book_folder / "metadata.json"
        
        # Check if metadata exists
        if metadata_file.exists():
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # GET THE SYNOPSIS
                summaries = data.get("summaries", [])
                synopsis = summaries[0] if summaries else ""
                
                # 🚩 BAD DATA DETECTION FLAGS 🚩
                is_bad = False
                
                # Flag 1: The "Old Script" signature
                if "automatically generated summary from the book's opening text" in synopsis:
                    is_bad = True
                
                # Flag 2: It's just the License Text
                if "Project Gutenberg License" in synopsis:
                    is_bad = True
                    
                # Flag 3: Empty or "Unknown" placeholder
                if synopsis == "No description available." or synopsis == "Local file import.":
                    is_bad = True

                if is_bad:
                    print(f"   🗑️  Deleting Bad Metadata: {book_folder.name}")
                    shutil.rmtree(book_folder) # Delete the whole folder
                    deleted_count += 1
                    
            except Exception as e:
                print(f"   ⚠️ Error reading {book_folder.name}: {e}")

    print(f"\n✨ Cleanup Complete. Deleted {deleted_count} folders with bad data.")
    print("👉 Now run 'python smart_librarian.py' to re-fetch them correctly!")

if __name__ == "__main__":
    clean_library()