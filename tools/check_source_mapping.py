import sys
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database.mongo_manager import mongo_db
from core.ai_engine.rag_pipeline import tars_archive

async def map_books():
    await mongo_db.initialize()
    books = await mongo_db.get_all_books()
    data = tars_archive.collection.get(include=['metadatas'])
    all_sources = set(m.get('source') for m in data['metadatas'] if m)
    print(f"Total Books in MongoDB: {len(books)}")
    print(f"Total Distinct Sources in ChromaDB: {len(all_sources)}")
    
    matched = 0
    unmatched = 0
    for b in books:
        title = b.get('title', '')
        bid = str(b.get('_id'))
        local_p = b.get('local_path', '')
        filename = Path(local_p).name if local_p else ''
        formats = b.get('formats', {})
        format_filenames = [Path(p).name for p in formats.values() if isinstance(p, str)]
        
        candidates = {title, filename} | set(format_filenames)
        found = [c for c in candidates if c in all_sources]
        
        if found:
            matched += 1
            print(f"MATCH: '{title}' -> Chroma source: {found}")
        else:
            unmatched += 1
            print(f"UNMATCHED: '{title}' (file: '{filename}', formats: {format_filenames})")

    print(f"\nSummary: Matched={matched}, Unmatched={unmatched}")

if __name__ == "__main__":
    asyncio.run(map_books())
