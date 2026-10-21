import gc
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.ai_engine.fast_chunker import (
    compute_fast_file_signature,
    fast_chunk_book,
)
from core.ai_engine.rag_pipeline import CHROMA_LOCK, resolve_missing_book_path

logger = logging.getLogger("BACKGROUND_INDEXER")


class BackgroundRAGIndexer:
    """
    Non-blocking background daemon worker that chunks and vectorizes unindexed books
    without ever freezing the application startup sequence or main UI thread.
    Operates with cooperative GIL yielding (time.sleep(0.005)) and zero UI framework locks.
    """

    def __init__(self, rag_pipeline, books_collection=None) -> None:
        self.rag = rag_pipeline
        self.books_col = books_collection
        self._lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None

        # Live thread-safe telemetry readable by the UI at any time
        self.is_running: bool = False
        self.stop_requested: bool = False
        self.current_book_idx: int = 0
        self.total_books: int = 0
        self.current_book_title: str = ""
        self.status_message: str = "Idle"
        self.completed_books: int = 0
        self.chunks_added: int = 0

    def start_non_blocking(self, embed_batch_size: int = 128) -> bool:
        """
        Starts the background RAG chunking worker if it is not already running.
        Returns immediately (< 1ms) so system startup never freezes.
        """
        with self._lock:
            if self.is_running and self._worker_thread and self._worker_thread.is_alive():
                return False

            self.is_running = True
            self.stop_requested = False
            self._worker_thread = threading.Thread(
                target=self._run_worker,
                args=(embed_batch_size,),
                name="TarsBackgroundIndexer",
                daemon=True,
            )
            self._worker_thread.start()
            return True

    def request_stop(self) -> None:
        """Requests graceful termination after the currently processing book or batch."""
        self.stop_requested = True
        self.status_message = "Stopping after current batch..."

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns instantaneous snapshot of worker state for UI banners and progress bars."""
        progress = (
            self.current_book_idx / self.total_books
            if self.total_books > 0
            else 0.0
        )
        return {
            "is_running": self.is_running,
            "current_book_idx": self.current_book_idx,
            "total_books": self.total_books,
            "current_book_title": self.current_book_title,
            "status_message": self.status_message,
            "completed_books": self.completed_books,
            "chunks_added": self.chunks_added,
            "progress_ratio": min(1.0, max(0.0, progress)),
        }

    def _resolve_collection(self):
        """Resolves MongoDB books collection safely for worker threads (prefers synchronous pymongo)."""
        if self.books_col is not None:
            # If Motor collection, extract synchronous pymongo delegate for thread safety
            if hasattr(self.books_col, "delegate"):
                return self.books_col.delegate
            if hasattr(self.books_col, "db") and self.books_col.db is not None:
                if hasattr(self.books_col.db, "client") and hasattr(self.books_col.db.client, "delegate"):
                    return self.books_col.db.client.delegate[self.books_col.db.name]["books"]
                if hasattr(self.books_col.db, "delegate"):
                    return self.books_col.db.delegate["books"]
            if hasattr(self.books_col, "find"):
                return self.books_col

        try:
            from core.database.mongo_manager import mongo_db
            if hasattr(mongo_db, "db") and mongo_db.db is not None:
                # Use synchronous pymongo client delegate in worker thread
                if hasattr(mongo_db.client, "delegate"):
                    return mongo_db.client.delegate[mongo_db.db.name]["books"]
                if hasattr(mongo_db.db, "delegate"):
                    return mongo_db.db.delegate["books"]
                return mongo_db.db["books"]
        except Exception as exc:
            logger.warning("Could not resolve books collection via mongo_db: %s", exc)
        return None

    def _run_worker(self, embed_batch_size: int) -> None:
        try:
            col = self._resolve_collection()
            if col is None:
                self.status_message = "Error: Database collection unavailable."
                return

            # Query books that are not indexed or failed
            query = {
                "$or": [
                    {"is_indexed": {"$ne": True}},
                    {"chunk_count": {"$in": [0, None]}},
                    {"indexing_status": "failed"},
                ]
            }
            projection = {
                "_id": 1,
                "id": 1,
                "title": 1,
                "author": 1,
                "authors": 1,
                "display_author": 1,
                "category": 1,
                "subjects": 1,
                "isbn": 1,
                "description": 1,
                "synopsis": 1,
                "local_path": 1,
                "file_path": 1,
                "file_signature": 1,
                "is_indexed": 1,
                "chunk_count": 1,
            }

            find_res = col.find(query, projection)
            if hasattr(find_res, "to_list"):
                # Fallback to sync delegate if async cursor was returned
                if hasattr(col, "delegate"):
                    pending_books = list(col.delegate.find(query, projection))
                else:
                    pending_books = []
            else:
                pending_books = list(find_res)

            self.total_books = len(pending_books)
            self.completed_books = 0
            self.chunks_added = 0

            if self.total_books == 0:
                self.status_message = "All catalog books are indexed and ready."
                return

            for idx, book_doc in enumerate(pending_books, start=1):
                if self.stop_requested:
                    self.status_message = "Indexing paused by user."
                    break

                raw_id = book_doc.get("id") or book_doc.get("_id")
                book_id = str(raw_id)
                title = book_doc.get("title") or f"Book #{idx}"
                local_path = resolve_missing_book_path(book_doc)

                self.current_book_idx = idx
                self.current_book_title = title
                self.status_message = f"Scanning [{idx}/{self.total_books}]: {title}"

                # 1. Idempotent File-Hash Fingerprinting (Skip Already-Indexed Books in 0ms)
                sig = compute_fast_file_signature(local_path)
                if (
                    book_doc.get("is_indexed") is True
                    and book_doc.get("file_signature") == sig
                    and book_doc.get("chunk_count", 0) > 0
                ):
                    self.completed_books += 1
                    continue

                # 2. Fast parallel digital chunking (OCR bypassed during background run)
                self.status_message = f"Chunking [{idx}/{self.total_books}]: {title}"
                chunks = fast_chunk_book(book_doc, local_path)
                if not chunks:
                    continue

                # Yield GIL briefly so UI clicks remain completely lag-free
                time.sleep(0.005)

                # 3. Vectorize and upsert in batches
                total_c = len(chunks)
                persisted = 0
                for start in range(0, total_c, embed_batch_size):
                    if self.stop_requested:
                        break
                    batch = chunks[start : start + embed_batch_size]
                    self.status_message = (
                        f"Embedding [{idx}/{self.total_books}] {title}: "
                        f"{min(start + len(batch), total_c)}/{total_c} chunks"
                    )

                    texts = [c["text"] for c in batch]
                    vectors = self.rag.embedder.encode(
                        texts,
                        batch_size=min(128, len(batch)),
                        normalize_embeddings=True,
                        show_progress_bar=False,
                    ).tolist()

                    ids = [f"{book_id}_chunk_{start + i}" for i in range(len(batch))]
                    metas = [
                        {
                            "book_id": book_id,
                            "title": title,
                            "author": book_doc.get("author") or book_doc.get("display_author") or "Unknown Author",
                            "page": int(c.get("page_number", 1)),
                            "source": str(c.get("source", "digital")),
                            "index_mode": "catalog_metadata_fallback" if c.get("source") == "catalog_metadata_fallback" else "full_text",
                        }
                        for c in batch
                    ]

                    with CHROMA_LOCK:
                        if self.rag.collection:
                            self.rag.collection.upsert(
                                ids=ids, documents=texts, embeddings=vectors, metadatas=metas
                            )
                    persisted += len(batch)
                    self.chunks_added += len(batch)
                    # Yield GIL between embedding batches
                    time.sleep(0.005)

                # 4. Mark book as indexed with its file signature
                update_fields = {
                    "is_indexed": True,
                    "chunk_count": persisted,
                    "vector_chunks_count": persisted,
                    "file_signature": sig,
                    "indexing_status": "indexed",
                    "indexing_error": None,
                    "last_indexed_at": datetime.now(timezone.utc),
                }
                if local_path and local_path != book_doc.get("local_path"):
                    update_fields["local_path"] = local_path

                try:
                    q = {"_id": book_doc["_id"]} if "_id" in book_doc else {"id": book_id}
                    if hasattr(col, "update_one"):
                        col.update_one(q, {"$set": update_fields})
                except Exception as up_err:
                    logger.debug("Notice updating index status for %s: %s", book_id, up_err)

                self.completed_books += 1
                gc.collect()

            # 5. Single-pass BM25 refresh at the very end of the background run
            if self.completed_books > 0 and not self.stop_requested:
                self.status_message = "Updating BM25 keyword cache..."
                if hasattr(self.rag, "refresh_bm25_index"):
                    self.rag.refresh_bm25_index()
                self.status_message = (
                    f"Completed! Indexed {self.completed_books} books ({self.chunks_added:,} chunks)."
                )

        except Exception as exc:
            logger.error("Background RAG indexer exception: %s", exc, exc_info=True)
            self.status_message = f"Background indexing error: {exc}"
        finally:
            self.is_running = False


_background_indexer_instance: Optional[BackgroundRAGIndexer] = None
_indexer_lock = threading.Lock()


def get_background_indexer(rag_pipeline=None, books_collection=None) -> BackgroundRAGIndexer:
    """Singleton accessor so only one background indexer exists across the application."""
    global _background_indexer_instance
    with _indexer_lock:
        if _background_indexer_instance is None:
            if rag_pipeline is None:
                from core.ai_engine.rag_pipeline import tars_archive
                rag_pipeline = tars_archive
            _background_indexer_instance = BackgroundRAGIndexer(rag_pipeline, books_collection)
        elif books_collection is not None and _background_indexer_instance.books_col is None:
            _background_indexer_instance.books_col = books_collection
    return _background_indexer_instance
