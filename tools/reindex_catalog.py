import asyncio
import time
import sys
from pathlib import Path

# Ensure project root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.config import EMBEDDING_MODEL_NAME, EMBEDDING_MODEL_PATH
from core.database.mongo_manager import mongo_db
from core.ai_engine.rag_pipeline import tars_archive
from core.services.ingestion_service import ingestion_service


async def main():
    print("=" * 70)
    print("  LIBRE-LIBRARY: TARS AI FULL CATALOG RE-INDEXATION")
    print(f"  Active Embedding Model: {EMBEDDING_MODEL_NAME}")
    print(f"  Model Path / Source:   {EMBEDDING_MODEL_PATH}")
    print("=" * 70)

    print("\n[1/3] Initializing MongoDB connection...")
    await mongo_db.initialize()

    books = await mongo_db.get_all_books()
    total_books = len(books)
    print(f"  • Found {total_books} total books in catalog.")

    print("\n[2/3] Re-vectorizing catalog with BGE-Small & Contextual Headers...")
    t0 = time.time()

    async def progress_report(idx, total, title, stage):
        pct = (idx / total) * 100
        print(f"  [{idx:03d}/{total:03d}] ({pct:5.1f}%) Vectorizing: {title[:45]}...")

    res = await ingestion_service.reindex_failed_books(
        progress_callback=progress_report,
        force_all=True
    )

    elapsed = time.time() - t0
    reindexed = res.get("reindexed", 0)
    failed = res.get("failed", 0)

    print("\n[3/3] Synchronizing BM25 in-memory keyword index...")
    tars_archive.refresh_bm25_index()

    stats = tars_archive.get_collection_stats()
    print("=" * 70)
    print(f"  RE-INDEX COMPLETE in {elapsed:.1f}s ({elapsed/60:.1f} mins)")
    print(f"  • Successfully Indexed: {reindexed}/{total_books}")
    print(f"  • Failed / Missing Files: {failed}")
    print(f"  • Total ChromaDB Vector Chunks: {stats.get('total_chunks', 0):,}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
