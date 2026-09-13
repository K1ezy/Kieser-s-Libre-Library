import os
import json
import shutil
import re
import requests
import hashlib
import time
from pathlib import Path
from urllib.parse import quote
from difflib import SequenceMatcher

# Try to import local libraries for internal text analysis
try:
    from pypdf import PdfReader
    import ebooklib
    from ebooklib import epub
    LOCAL_LIBS_AVAILABLE = True
except ImportError:
    LOCAL_LIBS_AVAILABLE = False

# --- CONFIGURATION ---
SOURCE_DIR = Path("E-Books").resolve()
TARGET_DIR = Path("data/books").resolve()

# --- API ENDPOINTS ---
GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes?q={}"
GUTENDEX_SEARCH = "https://gutendex.com/books?search={}"
ARCHIVE_ORG_SEARCH = "https://archive.org/advancedsearch.php?q=title:({}) AND creator:({})&fl[]=identifier,title,creator,description,year,subject,licenseurl&output=json&rows=1"
ARCHIVE_ORG_META = "https://archive.org/metadata/{}"

class SmartLibrarian:
    def __init__(self):
        self.session = requests.Session()
        # Add HTTPAdapter for connection pooling and max retries for robustness
        adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=3)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        self.session.headers.update({'User-Agent': 'LibreLibrary/6.0 (Fast/Robust)'})
        self.library_hashes = set()

    def run(self):
        print("🔹 DIGITAL LIBRARIAN (v6.0 ULTIMATE): ONLINE")
        
        # 1. BUILD MEMORY (Index existing books to avoid re-scanning)
        self.index_existing_library()
        
        if not SOURCE_DIR.exists():
            print("❌ 'E-Books' folder not found.")
            return

        TARGET_DIR.mkdir(parents=True, exist_ok=True)
        files = list(SOURCE_DIR.glob('*.*'))

        for file_path in files:
            if file_path.suffix.lower() not in ['.pdf', '.epub']:
                continue
            self.process_book(file_path)

        print("✔ LIBRARY UPDATE COMPLETE")

    # --- MEMORY & EFFICIENCY ---
    def get_file_hash(self, file_path):
        """Generates a unique digital fingerprint (MD5)."""
        hasher = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except:
            return None

    def index_existing_library(self):
        """Scans the current library to memorize what we already have."""
        print("   🧠 Building Library Memory...", end="", flush=True)
        if not TARGET_DIR.exists():
            print(" Done (Empty).")
            return

        count = 0
        for folder in TARGET_DIR.iterdir():
            if folder.is_dir():
                for file in folder.glob('*.*'):
                    if file.suffix.lower() in ['.pdf', '.epub']:
                        file_hash = self.get_file_hash(file)
                        if file_hash:
                            self.library_hashes.add(file_hash)
                            count += 1
        print(f" Done. Remembered {count} books.")

    # --- MAIN PROCESSING ---
    def process_book(self, file_path):
        print(f"\n📘 Processing: {file_path.name}")
        
        # 1. DUPLICATE CHECK
        current_hash = self.get_file_hash(file_path)
        if current_hash in self.library_hashes:
            print("   ⏩ Skipping (Duplicate Content Detected)")
            return

        # 2. IDENTIFY
        clean_title, clean_author = self.parse_filename(file_path.stem)
        print(f"   🎯 Target: '{clean_title}' by '{clean_author}'")
        
        # 3. FETCH METADATA (Gutenberg -> Google -> Archive.org)
        meta = self.fetch_metadata(clean_title, clean_author)
        
        # 4. SAVE
        if meta:
            self.save_to_library(meta, file_path, current_hash)
        else:
            self.save_local_fallback(clean_title, clean_author, file_path, current_hash)

    def parse_filename(self, filename):
        clean = filename.replace('_', ' ').replace('-', ' ')
        clean = re.sub(r'\(.*?\)|\[.*?\]', '', clean) 
        
        # Heuristic: "Title by Author"
        if " by " in clean.lower():
            parts = re.split(r' by ', clean, flags=re.IGNORECASE)
            return parts[0].strip(), parts[1].strip()
        
        # Heuristic: Known Authors
        known_authors = ["Orwell", "Salinger", "Lee", "Nabokov", "Tolstoy", "Austen", "Dickens", "Dostoyevsky", "Tolkien", "Melville", "Proust", "Joyce", "Faulkner", "Dante", "Carroll", "Fitzgerald", "Cervantes", "Homer", "Shakespeare"]
        
        for author in known_authors:
            if author.lower() in clean.lower():
                return clean.strip(), author 
        
        return clean.strip(), ""

    def fetch_metadata(self, title, author):
        # Strategy A: Gutenberg (Best for Classics)
        g_data = self.search_gutenberg(title, author)
        if g_data: return g_data
        
        # Strategy B: Google Books (Best for Modern)
        gb_data = self.search_google_books(title, author)
        if gb_data: return gb_data

        # Strategy C: Archive.org (Fallback for obscure books)
        # We re-enabled this but added Strict Filtering so it doesn't return junk.
        ao_data = self.search_archive_org(title, author)
        if ao_data: return ao_data
        
        return None

    # --- SEARCH ENGINES ---
    def search_gutenberg(self, title, author):
        try:
            query = f"{title} {author}".strip()
            res = self.session.get(GUTENDEX_SEARCH.format(quote(query)), timeout=5)
            data = res.json()
            if data['count'] > 0:
                print("   ✅ Gutenberg Match Found")
                result = data['results'][0]
                return self.normalize_gutenberg(result)
        except: pass
        return None

    def search_google_books(self, title, author_hint):
        try:
            query = f"{title} {author_hint}".strip()
            res = self.session.get(GOOGLE_BOOKS_API.format(quote(query)), timeout=5)
            data = res.json()
            
            if 'items' not in data: return None
            
            for item in data['items']:
                info = item['volumeInfo']
                if self.validate_match(info.get('title', ''), info.get('authors', []), author_hint):
                    print(f"   ✅ Google Books Match: {info.get('title')}")
                    return self.normalize_google(info)
        except: pass
        return None

    def search_archive_org(self, title, author_hint):
        try:
            url = ARCHIVE_ORG_SEARCH.format(quote(title), quote(author_hint))
            res = self.session.get(url, timeout=5)
            data = res.json()
            
            if data['response']['numFound'] > 0:
                doc = data['response']['docs'][0]
                # STRICT VALIDATION FOR ARCHIVE.ORG TOO
                if self.validate_match(doc.get('title', ''), [doc.get('creator', '')], author_hint):
                    print(f"   ✅ Archive.org Match: {doc.get('identifier')}")
                    # Fetch full metadata safely
                    full_meta = self.session.get(ARCHIVE_ORG_META.format(doc['identifier'])).json()
                    doc['full_description'] = full_meta.get('metadata', {}).get('description', '')
                    return self.normalize_archive_org(doc)
        except: pass
        return None

    def validate_match(self, found_title, found_authors, hint_author):
        """Strict Filter: Returns False if result is junk or wrong author."""
        # 1. Junk Filter
        junk_words = ["summary", "analysis", "guide", "notes", "sparknotes", "idiot's", "nft"]
        if any(word in found_title.lower() for word in junk_words):
            return False

        # 2. Author Match (If we have a hint)
        if hint_author:
            for author in found_authors:
                # Fuzzy match > 40% similarity OR substring match
                similarity = SequenceMatcher(None, hint_author.lower(), author.lower()).ratio()
                if similarity > 0.4 or hint_author.lower() in author.lower(): 
                    return True
            return False # No author matched
        
        return True # If no hint, trust the title match

    # --- NORMALIZERS ---
    def normalize_gutenberg(self, raw):
        return {
            "id": str(raw['id']),
            "title": raw['title'],
            "authors": raw['authors'],
            "summaries": [f"A Project Gutenberg eBook of {raw['title']}."],
            "cover_url": raw['formats'].get('image/jpeg'),
            "copyright": False
        }

    def normalize_google(self, raw):
        safe_id = re.sub(r'[^a-zA-Z0-9]', '', raw['title'])[:20] + "_gb"
        return {
            "id": safe_id,
            "title": raw['title'],
            "authors": [{"name": a} for a in raw.get('authors', ['Unknown'])],
            "summaries": [raw.get('description', 'No description.')],
            "cover_url": raw.get('imageLinks', {}).get('thumbnail'),
            "copyright": True 
        }

    def normalize_archive_org(self, raw):
        # Fix List Crash (Robustness)
        desc = raw.get('full_description', '')
        if isinstance(desc, list): desc = " ".join(desc)
        desc = re.sub(r'<[^>]+>', '', str(desc))
        
        return {
            "id": raw['identifier'],
            "title": raw['title'],
            "authors": [{"name": raw.get('creator', 'Unknown')}],
            "summaries": [desc[:500] + "..." if desc else "No summary."],
            "cover_url": None, # Archive.org covers are tricky, skipping for stability
            "copyright": True
        }

    # --- STORAGE ---
    def save_to_library(self, record, original_file, file_hash):
        folder_name = record['id']
        book_folder = TARGET_DIR / folder_name
        
        if book_folder.exists():
            print(f"   ⏩ Skipping (Folder Exists): {folder_name}")
            if file_hash: self.library_hashes.add(file_hash)
            return

        book_folder.mkdir(parents=True, exist_ok=True)
        cover_url = record.pop('cover_url', None)

        final_meta = {
            "id": record['id'],
            "title": record['title'],
            "authors": record['authors'],
            "summaries": record['summaries'],
            "subjects": [], "bookshelves": [], "languages": ["en"],
            "copyright": record['copyright'],
            "media_type": "Text",
            "formats": {
                "application/pdf" if original_file.suffix == ".pdf" else "application/epub+zip": 
                f"/books/{record['id']}/{original_file.name}"
            }
        }

        with open(book_folder / 'metadata.json', 'w', encoding='utf-8') as f:
            json.dump(final_meta, f, indent=2)
            
        shutil.copy2(original_file, book_folder / original_file.name)
        if file_hash: self.library_hashes.add(file_hash)

        if cover_url:
            try:
                img_data = self.session.get(cover_url).content
                with open(book_folder / 'cover.jpg', 'wb') as f:
                    f.write(img_data)
                print("   🖼️  Cover Downloaded")
            except: pass
        print(f"   💾 Saved.")
        
if __name__ == "__main__":
    librarian = SmartLibrarian()
    librarian.run()