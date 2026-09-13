import sys
from pathlib import Path
import json

# Setup path
BASE_DIR = Path(__file__).resolve().parent.parent
BOOKS_DIR = BASE_DIR / 'data' / 'books'

def fix_authors():
    print(f"🔧 Scanning {BOOKS_DIR}...")
    count = 0
    for folder in BOOKS_DIR.iterdir():
        if not folder.is_dir(): continue
        
        meta_path = folder / "metadata.json"
        if not meta_path.exists(): continue
        
        with open(meta_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Check if needs fixing
        title = data.get('title', '')
        authors = data.get('authors', [])
        
        # If author is unknown AND title has " By "
        if (authors == ["Unknown"] or authors == "Unknown") and " By " in title:
            print(f"   > Fixing: {title}")
            parts = title.split(" By ")
            new_title = parts[0].replace("_", " ").strip()
            new_author = parts[1].replace("_", " ").strip()
            
            data['title'] = new_title
            data['authors'] = [new_author]
            
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            count += 1

    print(f"✅ Fixed {count} books.")

if __name__ == "__main__":
    fix_authors()