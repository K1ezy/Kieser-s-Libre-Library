import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database.mongo_manager import mongo_db
from core.ai_engine.rag_pipeline import tars_archive

async def sync_chroma_with_mongo():
    print("=" * 60)
    print(" Synchronizing ChromaDB Vector Chunks with MongoDB Books")
    print("=" * 60)
    
    await mongo_db.initialize()
    books = await mongo_db.get_all_books()
    print(f"[INFO] Loaded {len(books)} books from MongoDB.")
    
    if tars_archive.collection is None:
        print("[ERROR] ChromaDB collection is not available.")
        return False
        
    total_chunks = tars_archive.collection.count()
    print(f"[INFO] Total ChromaDB chunks in knowledge base: {total_chunks}")
    
    # 1. Map all known distinct sources in ChromaDB
    all_data = tars_archive.collection.get(include=['metadatas'])
    known_sources = set(m.get('source') for m in all_data['metadatas'] if m and m.get('source'))
    print(f"[INFO] Found {len(known_sources)} distinct source names in ChromaDB:")
    for s in sorted(known_sources):
        print(f"   - {s}")
        
    updated_total = 0
    matched_books = 0
    
    # 2. Correlate each Mongo book to its Chroma source
    for book in books:
        title = book.get('title', '').strip()
        bid = str(book.get('_id'))
        uuid_id = str(book.get('id', ''))
        local_p = book.get('local_path', '')
        filename = Path(local_p).name if local_p else ''
        formats = book.get('formats', {})
        format_filenames = [Path(p).name for p in formats.values() if isinstance(p, str)]
        
        # Build prioritized list of candidate identifiers
        candidates = []
        if filename:
            candidates.append(filename)
        for fn in format_filenames:
            if fn and fn not in candidates:
                candidates.append(fn)
        if title and title not in candidates:
            candidates.append(title)
            
        # Also check clean title variations
        clean_title = filename.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').strip()
        if clean_title and clean_title not in candidates:
            candidates.append(clean_title)
            
        # Find which candidate exists in ChromaDB
        matched_source = None
        for cand in candidates:
            if cand in known_sources:
                matched_source = cand
                break
                
        # If no exact match, try case-insensitive / normalized match
        if not matched_source:
            cand_lowers = {c.lower(): c for c in candidates}
            for ks in known_sources:
                if ks.lower() in cand_lowers or any(c.lower() in ks.lower() for c in candidates if len(c) > 5):
                    matched_source = ks
                    break
                    
        if not matched_source:
            continue
            
        matched_books += 1
        # Fetch all chunks for this source
        res = tars_archive.collection.get(where={"source": matched_source}, include=['metadatas'])
        chunk_ids = res.get('ids', [])
        metadatas = res.get('metadatas', [])
        
        if not chunk_ids:
            continue
            
        new_metas = []
        needs_update = False
        for m in metadatas:
            updated_m = dict(m)
            # Ensure book_id, book_uuid, and display title are set
            if updated_m.get('book_id') != bid or updated_m.get('title') != title:
                updated_m['book_id'] = bid
                updated_m['book_uuid'] = uuid_id
                updated_m['title'] = title
                updated_m['source'] = matched_source
                needs_update = True
            new_metas.append(updated_m)
            
        if needs_update:
            # Batch update in chunks of 500
            for i in range(0, len(chunk_ids), 500):
                b_ids = chunk_ids[i:i + 500]
                b_metas = new_metas[i:i + 500]
                tars_archive.collection.update(ids=b_ids, metadatas=b_metas)
            updated_total += len(chunk_ids)
            print(f"[SYNCED] '{title}' ({matched_source}) -> {len(chunk_ids)} chunks enriched with book_id={bid}")
        else:
            print(f"[ALREADY SYNCED] '{title}' ({matched_source}) -> {len(chunk_ids)} chunks")
            
    print("=" * 60)
    print(f" SYNC COMPLETE: {matched_books} books mapped | {updated_total} chunks updated.")
    print("=" * 60)
    tars_archive._clear_cache()
    return True

if __name__ == "__main__":
    asyncio.run(sync_chroma_with_mongo())
