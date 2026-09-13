import os
import json
from pathlib import Path

# Paths
DATA_BOOKS_DIR = Path("data/books").resolve()
LEGACY_BOOKS_DIR = Path("E-Books").resolve()

def scan_library():
    """Robust scanner: Handles both new folders and old legacy files."""
    books = []
    
    # 1. SCAN NEW STRUCTURE (data/books/Title/...)
    if DATA_BOOKS_DIR.exists():
        for folder in DATA_BOOKS_DIR.iterdir():
            if folder.is_dir():
                book_file = None
                # Find the book file
                for ext in ['.pdf', '.epub', '.mobi', '.docx', '.pptx', '.txt']: 
                    found = list(folder.glob(f"*{ext}"))
                    if found:
                        book_file = found[0]
                        break
                
                if book_file:
                    # Metadata
                    meta_path = folder / "metadata.json"
                    cover_path = folder / "cover.jpg"
                    
                    title = folder.name.replace('_', ' ').title()
                    author = "Unknown"
                    
                    if meta_path.exists():
                        try:
                            with open(meta_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                title = data.get('title', title)
                                author = data.get('author', author)
                        except: pass

                    books.append({
                        "title": title,
                        "author": author,
                        "format": book_file.suffix.upper().replace('.', ''),
                        # CRITICAL: We explicitly say this is in the 'books' mount
                        "path_id": f"books/{folder.name}/{book_file.name}", 
                        "cover_url": f"/books/{folder.name}/cover.jpg" if cover_path.exists() else None,
                        "is_legacy": False
                    })

    # 2. SCAN LEGACY STRUCTURE (E-Books/*.pdf)
    if LEGACY_BOOKS_DIR.exists():
        for file_path in LEGACY_BOOKS_DIR.glob('*.*'):
            if file_path.suffix.lower() in ['.pdf', '.epub', '.mobi']:
                clean_name = file_path.stem.replace('_', ' ').replace('-', ' ').title()
                
                books.append({
                    "title": clean_name,
                    "author": "Legacy Collection",
                    "format": file_path.suffix.upper().replace('.', ''),
                    # CRITICAL: We explicitly say this is in the 'legacy' mount
                    "path_id": f"legacy/{file_path.name}", 
                    "cover_url": None, # No cover for legacy
                    "is_legacy": True
                })
    
    return books

def get_stats():
    books = scan_library()
    authors = set(b['author'] for b in books)
    return {
        "total_books": len(books),
        "total_authors": len(authors),
        "reading_streak": 5
    }