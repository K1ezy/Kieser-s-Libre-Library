import gc
import glob
import logging
import os
import re
import shutil
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import chromadb
from rank_bm25 import BM25Okapi

from core.ai_engine.text_extractor import extract_document_structure, extract_text_from_file
from core.config import (
    EMBEDDING_MODEL_PATH,
    EMBEDDING_MODEL_NAME,
    RERANKER_MODEL_NAME,
    ENABLE_RERANKER,
    ENABLE_HYBRID_BM25,
    BGE_QUERY_PREFIX,
    RAG_MAX_DISTANCE,
    settings as app_settings,
)

logger = logging.getLogger("TARS_ARCHIVE")

# Global re-entrant lock to prevent concurrent ChromaDB Rust binding access violations
CHROMA_LOCK = threading.RLock()

CACHE_MAX_SIZE = 256
CACHE_TTL_SECONDS = 180.0

SEARCH_DIRECTORIES = (
    "data/books",
    "uploads/books",
    "uploads",
    "storage/books",
    "assets/books",
)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def resolve_missing_book_path(book_doc: Dict[str, Any], base_dir: str = ".") -> Optional[str]:
    r"""
    Attempts to locate a book's PDF/EPUB/TXT file on disk if `local_path` in MongoDB
    is None, points to another drive/path (e.g. C:\Users\... vs D:\Libre-Library), or was moved.
    """
    raw_path = book_doc.get("local_path") or book_doc.get("file_path")
    if raw_path and isinstance(raw_path, str):
        if os.path.isfile(raw_path):
            return raw_path
        candidate_rel = os.path.join(base_dir, raw_path.lstrip("/\\"))
        if os.path.isfile(candidate_rel):
            return candidate_rel
        normalized = raw_path.replace("\\", "/")
        if "data/books/" in normalized:
            sub = normalized.split("data/books/", 1)[1]
            local_candidate = os.path.join(base_dir, "data", "books", *sub.split("/"))
            if os.path.isfile(local_candidate):
                return local_candidate

    title_slug = _slugify(book_doc.get("title", ""))
    isbn_slug = _slugify(str(book_doc.get("isbn", "")))
    if not title_slug and not isbn_slug:
        return None

    for folder in SEARCH_DIRECTORIES:
        search_root = os.path.join(base_dir, folder)
        if not os.path.isdir(search_root):
            continue
        for root, _, files in os.walk(search_root):
            for fname in files:
                if not fname.lower().endswith((".pdf", ".epub", ".docx", ".pptx", ".txt", ".md")):
                    continue
                file_slug = _slugify(os.path.splitext(fname)[0])
                if (title_slug and title_slug in file_slug) or (
                    isbn_slug and len(isbn_slug) >= 8 and isbn_slug in file_slug
                ):
                    return os.path.join(root, fname)
    return None


def build_catalog_fallback_chunks(book_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    When a physical PDF is missing or purely graphical (0 extractable text pages),
    synthesizes a rich bibliographic & synopsis chunk from MongoDB catalog metadata
    so TARS AI can still answer questions about the book.
    """
    title = book_doc.get("title") or "Untitled Library Book"
    authors = book_doc.get("authors") or []
    author = book_doc.get("display_author") or (authors[0] if authors else (book_doc.get("author") or "Unknown Author"))
    subjects = book_doc.get("subjects") or []
    category = subjects[0] if subjects else (book_doc.get("category") or book_doc.get("subject") or "General Collection")
    isbn = book_doc.get("isbn") or "N/A"
    publisher = book_doc.get("publisher") or "N/A"
    year = book_doc.get("publication_year") or book_doc.get("year") or "N/A"
    description = (
        book_doc.get("description")
        or book_doc.get("synopsis")
        or book_doc.get("summary")
        or "This title is part of the Libre-Library catalog collection."
    )
    call_number = book_doc.get("call_number") or book_doc.get("location") or "Main Stacks"

    fallback_text = (
        f"[Book: {title} | Author: {author} | Subject: {category} | Page: Catalog Record]\n"
        f"Title: {title}\n"
        f"Author: {author}\n"
        f"Category / Subject: {category}\n"
        f"ISBN: {isbn} | Publisher: {publisher} | Publication Year: {year}\n"
        f"Library Location / Call Number: {call_number}\n"
        f"Catalog Synopsis & Overview: {description}"
    )

    return [
        {
            "page": 1,
            "page_number": 1,
            "text": fallback_text,
            "source": "catalog_metadata_fallback",
            "type": "catalog_metadata_fallback",
        }
    ]


def chunk_pages_with_headers(
    pages: List[Dict[str, Any]],
    book_title: str,
    author: str,
    chunk_size: int = 900,
    chunk_overlap: int = 150,
) -> List[Dict[str, Any]]:
    """
    Splits extracted pages into overlapping semantic chunks and prepends
    [Book: ... | Author: ... | Page: ...] contextual headers.
    """
    chunks: List[Dict[str, Any]] = []
    step = max(100, chunk_size - chunk_overlap)

    for page in pages:
        page_num = page.get("page_number") or page.get("page") or 1
        source_type = page.get("source", "digital")
        text = page.get("text", "").strip()
        if not text:
            continue

        # If already formatted as a catalog fallback chunk, keep as-is
        if source_type == "catalog_metadata_fallback" or page.get("type") == "catalog_metadata_fallback":
            chunks.append(
                {
                    "page_number": page_num,
                    "page": page_num,
                    "text": text,
                    "source": "catalog_metadata_fallback",
                }
            )
            continue

        start = 0
        text_len = len(text)
        while start < text_len:
            segment = text[start : start + chunk_size].strip()
            if len(segment) >= 25:
                header = f"[Book: {book_title} | Author: {author} | Page: {page_num}]"
                chunks.append(
                    {
                        "page_number": page_num,
                        "page": page_num,
                        "text": f"{header}\n{segment}",
                        "source": source_type,
                    }
                )
            start += step

    return chunks


def tokenize_for_bm25(text: str) -> List[str]:
    """Lightweight alphanumeric tokenizer for BM25 keyword indexing."""
    if not text:
        return []
    return re.findall(r"\w+", text.lower())


def build_contextual_chunk(
    raw_text: str,
    book_title: str,
    author: str = "Unknown Author",
    category: str = "General",
    page_number: Optional[int] = None,
    section: Optional[str] = None,
) -> str:
    """
    Prepends structured bibliographic context to every chunk before embedding.
    Dramatically improves retrieval when users ask book-, author-, or page-specific questions.
    """
    clean_text = (raw_text or "").strip()
    if not clean_text:
        return ""
    meta_parts = [f"Book: {book_title}"]
    if author and author != "Unknown Author":
        meta_parts.append(f"Author: {author}")
    if category and category != "General":
        meta_parts.append(f"Subject: {category}")
    if section:
        meta_parts.append(f"Section: {section}")
    if page_number is not None:
        meta_parts.append(f"Page: {page_number}")

    header = "[" + " | ".join(meta_parts) + "]"
    return f"{header}\n{clean_text}"


class ResilientRAGPipeline:
    """
    Resilient, High-Accuracy Hybrid RAG Engine for Libre-Library (TARS AI):
    1. Thread-safe ChromaDB access with module-level RLock.
    2. Adaptive OCR and fast digital extraction.
    3. Auto-healing missing file resolver and catalog metadata fallback chunking.
    4. Deferred single-pass BM25 index rebuilding for batch operations.
    5. Memory-safe micro-batching (100 chunks) with explicit garbage collection.
    6. Dense Vector Search, BM25Okapi, Reciprocal Rank Fusion (RRF), and CrossEncoder reranking.
    """

    def __init__(
        self,
        persist_directory: str = "data/chroma_db",
        collection_name: str = "tars_knowledge_base",
        embedding_model_name: Optional[str] = None,
        enable_hybrid_bm25: Optional[bool] = None,
    ):
        self.persist_directory = str(persist_directory)
        self.persist_dir = self.persist_directory
        self.collection_name = str(collection_name)
        self.embedding_model_name = embedding_model_name or EMBEDDING_MODEL_PATH
        self.enable_hybrid_bm25 = ENABLE_HYBRID_BM25 if enable_hybrid_bm25 is None else bool(enable_hybrid_bm25)

        with CHROMA_LOCK:
            try:
                self.client = chromadb.PersistentClient(path=self.persist_directory)
                self.collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception as exc:
                logger.warning("ChromaDB persistent client init notice: %s", exc)
                self.client = None
                self.collection = None

        self._embedder = None
        self._reranker = None
        self._bm25_index: Optional[BM25Okapi] = None
        self._bm25_docs: List[Dict[str, Any]] = []
        self._bm25_lock = threading.Lock()
        self._query_cache: "OrderedDict[tuple, Tuple[float, List[dict]]]" = OrderedDict()
        self._cache_lock = threading.Lock()
        self._is_initialized = True

    @property
    def embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(self.embedding_model_name)
        return self._embedder

    @property
    def reranker(self):
        if self._reranker is None and ENABLE_RERANKER:
            try:
                from sentence_transformers import CrossEncoder
                self._reranker = CrossEncoder(RERANKER_MODEL_NAME)
                logger.info("Loaded CrossEncoder reranker: %s", RERANKER_MODEL_NAME)
            except Exception as e:
                logger.warning("Notice loading CrossEncoder reranker (%s); falling back to RRF rank order.", e)
                self._reranker = None
        return self._reranker

    def reset_corrupted_vector_store(self) -> None:
        """
        Safely recreates the ChromaDB collection if legacy HNSW binary segment files
        throw native Rust access violations.
        """
        with CHROMA_LOCK:
            try:
                if self.client:
                    self.client.delete_collection(self.collection_name)
            except Exception as del_err:
                logger.warning("Notice deleting collection during reset: %s", del_err)
                shutil.rmtree(self.persist_directory, ignore_errors=True)
                os.makedirs(self.persist_directory, exist_ok=True)
                self.client = chromadb.PersistentClient(path=self.persist_directory)

            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            with self._bm25_lock:
                self._bm25_index = None
                self._bm25_docs = []
            self._clear_cache()
            logger.info("ChromaDB vector store cleanly reset and re-initialized.")

    def refresh_bm25_index(self, book_id_filter: Optional[str] = None) -> int:
        """
        Rebuilds the global in-memory BM25 index in a single pass.
        Must ONLY be called once after a batch re-indexing run completes.
        """
        if not self.enable_hybrid_bm25 or self.collection is None:
            return 0

        try:
            where_clause = {"book_id": str(book_id_filter)} if book_id_filter else None
            with CHROMA_LOCK:
                stored = self.collection.get(
                    where=where_clause,
                    include=["documents", "metadatas"],
                )

            ids = stored.get("ids") or []
            docs = stored.get("documents") or []
            metas = stored.get("metadatas") or []

            new_bm25_docs: List[Dict[str, Any]] = []
            tokenized_corpus: List[List[str]] = []

            for cid, doc_text, meta in zip(ids, docs, metas):
                if not doc_text:
                    continue
                new_bm25_docs.append({
                    "id": cid,
                    "text": doc_text,
                    "metadata": meta or {},
                })
                tokenized_corpus.append(tokenize_for_bm25(doc_text))

            with self._bm25_lock:
                if tokenized_corpus:
                    self._bm25_docs = new_bm25_docs
                    self._bm25_index = BM25Okapi(tokenized_corpus)
                    logger.info("BM25 index synchronized with %d chunks.", len(tokenized_corpus))
                    self._save_bm25_cache_unlocked()
                    return len(self._bm25_docs)
                else:
                    self._bm25_docs = []
                    self._bm25_index = None
                    return 0
        except Exception as e:
            logger.warning("Notice building BM25 index: %s", e)
            return 0

    def _save_bm25_cache_unlocked(self) -> bool:
        """Serializes the BM25 in-memory index to disk cache in data/cache/bm25_cache.pkl."""
        try:
            import pickle
            cache_path = os.path.join("data", "cache", "bm25_cache.pkl")
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            data = {"docs": self._bm25_docs, "index": self._bm25_index}
            with open(cache_path, "wb") as f:
                pickle.dump(data, f)
            logger.info("BM25 index serialized to %s.", cache_path)
            return True
        except Exception as exc:
            logger.debug("Notice saving BM25 cache: %s", exc)
            return False

    def load_bm25_cache_if_available(self) -> bool:
        """Loads BM25 index from disk cache in under 50ms without querying ChromaDB."""
        cache_path = os.path.join("data", "cache", "bm25_cache.pkl")
        if not os.path.isfile(cache_path) or not self.enable_hybrid_bm25:
            return False
        try:
            import pickle
            with open(cache_path, "rb") as f:
                data = pickle.load(f)
            with self._bm25_lock:
                self._bm25_docs = data.get("docs", [])
                self._bm25_index = data.get("index")
            logger.info("BM25 index loaded from disk cache in <50ms (%d chunks).", len(self._bm25_docs))
            return True
        except Exception as exc:
            logger.debug("Notice loading BM25 cache: %s", exc)
            return False

    def ensure_initialized(self) -> bool:
        """Verifies or initializes ChromaDB collection and resources cleanly."""
        with CHROMA_LOCK:
            if self.client is None:
                self.client = chromadb.PersistentClient(path=self.persist_directory)
            if self.collection is None:
                self.collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
        if self._bm25_index is None and self.enable_hybrid_bm25:
            self.load_bm25_cache_if_available()
        return True

    def upsert_batch_threadsafe(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """Thread-safe batch upsert into ChromaDB."""
        with CHROMA_LOCK:
            if self.collection:
                self.collection.upsert(
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )

    def index_single_book(
        self,
        book_doc: Dict[str, Any],
        books_collection=None,
        enable_ocr: bool = False,
        max_ocr_pages: int = 12,
        enable_metadata_fallback: bool = True,
        rebuild_bm25: bool = True,
        embed_batch_size: int = 100,
        sub_progress_cb: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Indexes a single book safely:
        - Resolves missing file paths automatically across standard folders
        - Uses bounded OCR or fast digital extraction with live sub-progress callbacks
        - Falls back to Catalog Metadata Chunking so 0 books are left unindexed
        - Upserts in thread-safe micro-batches of 100 chunks
        - Defers BM25 rebuild when `rebuild_bm25=False`
        - Enforces explicit gc.collect()
        """
        raw_id = book_doc.get("_id") or book_doc.get("id") or book_doc.get("book_id") or ""
        book_id = str(raw_id)
        title = book_doc.get("title") or "Untitled"
        authors = book_doc.get("authors") or []
        author = book_doc.get("display_author") or (authors[0] if authors else (book_doc.get("author") or "Unknown Author"))

        # 1. Resolve file path (auto-heal if local_path is None or moved)
        resolved_path = resolve_missing_book_path(book_doc)
        if resolved_path and resolved_path != book_doc.get("local_path"):
            if books_collection is not None and "_id" in book_doc:
                try:
                    if hasattr(books_collection, "update_one"):
                        books_collection.update_one(
                            {"_id": book_doc["_id"]},
                            {"$set": {"local_path": resolved_path}},
                        )
                    elif hasattr(books_collection, "update_book"):
                        import asyncio
                        res = books_collection.update_book(book_id, {"local_path": resolved_path})
                        if asyncio.iscoroutine(res):
                            try:
                                loop = asyncio.get_event_loop()
                                if loop.is_running():
                                    asyncio.create_task(res)
                            except Exception:
                                pass
                except Exception as p_err:
                    logger.debug(f"Auto-heal local_path MongoDB update notice: {p_err}")

        # 2. Extract pages from PDF/text file if present
        pages: List[Dict[str, Any]] = []
        if resolved_path:
            pages = extract_document_structure(
                file_path=resolved_path,
                enable_ocr=enable_ocr,
                max_ocr_pages=max_ocr_pages,
                progress_callback=(
                    lambda cur, tot, msg: sub_progress_cb(f"Extracting Page {cur}/{tot}")
                    if sub_progress_cb
                    else None
                ),
            )
            if not pages:
                raw_text = extract_text_from_file(resolved_path)
                if raw_text and raw_text.strip():
                    pages = [{"page": 1, "page_number": 1, "text": raw_text.strip(), "source": "digital"}]

        # 3. Fallback to Catalog Metadata Chunking if file is missing or yielded 0 text
        used_fallback = False
        if not pages and enable_metadata_fallback:
            if sub_progress_cb:
                sub_progress_cb("Synthesizing catalog metadata fallback chunk...")
            pages = build_catalog_fallback_chunks(book_doc)
            used_fallback = True

        if not pages:
            return {
                "book_id": book_id,
                "title": title,
                "status": "failed",
                "chunks_persisted": 0,
                "reason": "No extractable text and metadata fallback disabled.",
            }

        # 4. Chunk pages with contextual headers
        chunks = chunk_pages_with_headers(pages, book_title=title, author=author)
        if not chunks:
            return {
                "book_id": book_id,
                "title": title,
                "status": "failed",
                "chunks_persisted": 0,
                "reason": "Zero valid chunks generated.",
            }

        # 5. Remove stale chunks for this book_id before inserting fresh ones
        with CHROMA_LOCK:
            try:
                self.collection.delete(where={"book_id": book_id})
            except Exception:
                pass

        # 6. Embed and upsert in thread-safe micro-batches of 100 chunks
        total_chunks = len(chunks)
        total_batches = (total_chunks + embed_batch_size - 1) // embed_batch_size
        persisted = 0

        for b_i, start_idx in enumerate(range(0, total_chunks, embed_batch_size), start=1):
            batch = chunks[start_idx : start_idx + embed_batch_size]
            end_idx = min(start_idx + len(batch), total_chunks)
            if sub_progress_cb:
                sub_progress_cb(
                    f"Embedding Batch {b_i}/{total_batches} ({start_idx + 1}–{end_idx} of {total_chunks})..."
                )

            texts = [c["text"] for c in batch]
            embeddings = self.embedder.encode(
                texts,
                batch_size=min(64, embed_batch_size),
                normalize_embeddings=True,
                show_progress_bar=False,
            ).tolist()

            ids = [f"{book_id}_chunk_{start_idx + i}" for i in range(len(batch))]
            metadatas = [
                {
                    "book_id": str(book_id),
                    "title": str(title),
                    "author": str(author),
                    "page": int(c.get("page_number") or c.get("page") or 1),
                    "source": str(c.get("source", "digital")),
                    "index_mode": "catalog_metadata_fallback" if used_fallback else "full_text",
                }
                for c in batch
            ]

            if sub_progress_cb:
                sub_progress_cb(
                    f"Persisting Batch {b_i}/{total_batches} ({len(batch)} chunks)..."
                )

            with CHROMA_LOCK:
                self.collection.upsert(
                    ids=ids,
                    documents=texts,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
            persisted += len(batch)

        # Update MongoDB catalog status
        if books_collection is not None and "_id" in book_doc:
            update_payload = {
                "is_indexed": True,
                "chunk_count": persisted,
                "vector_chunks_count": persisted,
                "indexing_status": "indexed",
                "indexing_error": None,
                "index_mode": "catalog_metadata_fallback" if used_fallback else "full_text",
                "last_indexed_at": datetime.now(timezone.utc),
            }
            try:
                if hasattr(books_collection, "update_one"):
                    books_collection.update_one(
                        {"_id": book_doc["_id"]},
                        {"$set": update_payload},
                    )
                elif hasattr(books_collection, "update_book"):
                    import asyncio
                    res = books_collection.update_book(book_id, update_payload)
                    if asyncio.iscoroutine(res):
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.create_task(res)
                        except Exception:
                            pass
            except Exception as m_err:
                logger.debug(f"Catalog MongoDB status update notice: {m_err}")

        # 7. Only rebuild BM25 if explicitly requested (False during batch loops!)
        if persisted > 0 and rebuild_bm25 and self.enable_hybrid_bm25:
            if sub_progress_cb:
                sub_progress_cb("Rebuilding BM25 keyword index...")
            self.refresh_bm25_index()

        self._clear_cache()
        gc.collect()

        return {
            "book_id": book_id,
            "title": title,
            "status": "indexed_fallback" if used_fallback else "indexed_full",
            "chunks_persisted": persisted,
        }

    def reindex_failed_books(
        self,
        unindexed_books: List[Dict[str, Any]],
        books_collection=None,
        enable_ocr: bool = False,
        max_ocr_pages: int = 10,
        enable_metadata_fallback: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Batch-indexes all unindexed/failed books with:
        - Deferred single BM25 index rebuild at the very end
        - Per-book and sub-chunk progress callbacks
        - Fault isolation so one bad file never aborts the batch
        """
        total = len(unindexed_books)
        indexed_full = 0
        indexed_fallback = 0
        failed = 0
        total_chunks_added = 0
        failure_details: List[str] = []

        try:
            for idx, book_doc in enumerate(unindexed_books, start=1):
                title = book_doc.get("title") or f"Book #{idx}"
                if progress_callback:
                    progress_callback(idx - 1, total, f"Vectorizing [{idx}/{total}]: {title}...")

                try:
                    res = self.index_single_book(
                        book_doc=book_doc,
                        books_collection=books_collection,
                        enable_ocr=enable_ocr,
                        max_ocr_pages=max_ocr_pages,
                        enable_metadata_fallback=enable_metadata_fallback,
                        rebuild_bm25=False,  # CRITICAL: Deferred until batch ends!
                        sub_progress_cb=(
                            lambda detail_msg, i=idx: progress_callback(
                                i - 1, total, f"[{i}/{total}] {detail_msg}"
                            )
                            if progress_callback
                            else None
                        ),
                    )
                    chunks_count = res.get("chunks_persisted", 0)
                    total_chunks_added += chunks_count

                    if res["status"] == "indexed_full":
                        indexed_full += 1
                    elif res["status"] == "indexed_fallback":
                        indexed_fallback += 1
                    else:
                        failed += 1
                        failure_details.append(f"{title}: {res.get('reason', 'Unknown error')}")
                except Exception as exc:
                    failed += 1
                    logger.error(f"Error indexing book '{title}': {exc}")
                    failure_details.append(f"{title}: {exc}")

        finally:
            # Rebuild the global BM25 index ONCE at the very end of the batch
            if (indexed_full + indexed_fallback) > 0 and self.enable_hybrid_bm25:
                if progress_callback:
                    progress_callback(
                        total,
                        total,
                        "Finalizing: Building global BM25 keyword index (single pass)...",
                    )
                self.refresh_bm25_index()

            if progress_callback:
                progress_callback(total, total, "Batch indexing complete!")

        return {
            "total_processed": total,
            "indexed_full": indexed_full,
            "indexed_fallback": indexed_fallback,
            "failed": failed,
            "total_chunks_added": total_chunks_added,
            "failures": failure_details,
        }

    def ingest_document(
        self,
        file_path: Optional[str],
        filename: str,
        book_id: Optional[str] = None,
        title: Optional[str] = None,
        force_reindex: bool = False,
        author: str = "Unknown Author",
        category: str = "General",
        rebuild_bm25: bool = True,
        enable_ocr: bool = True,
        max_ocr_pages: int = 15,
        enable_metadata_fallback: bool = True,
        sub_progress_cb: Optional[Callable[[str], None]] = None,
        book_doc: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Single document ingestion adapter for file upload pipelines."""
        b_doc = dict(book_doc or {})
        b_doc["_id"] = book_id or b_doc.get("_id") or str(uuid.uuid4())
        b_doc["title"] = title or b_doc.get("title") or filename
        b_doc["author"] = author or b_doc.get("author") or "Unknown Author"
        b_doc["category"] = category or b_doc.get("category") or "General"
        if file_path:
            b_doc["local_path"] = file_path

        res = self.index_single_book(
            book_doc=b_doc,
            enable_ocr=enable_ocr,
            max_ocr_pages=max_ocr_pages,
            enable_metadata_fallback=enable_metadata_fallback,
            rebuild_bm25=rebuild_bm25,
            sub_progress_cb=sub_progress_cb,
        )
        return res.get("chunks_persisted", 0)

    def reindex_document(
        self,
        file_path: Optional[str],
        filename: str,
        book_id: str,
        title: Optional[str] = None,
        author: str = "Unknown Author",
        category: str = "General",
        rebuild_bm25: bool = True,
        enable_ocr: bool = True,
        max_ocr_pages: int = 15,
        enable_metadata_fallback: bool = True,
        sub_progress_cb: Optional[Callable[[str], None]] = None,
        book_doc: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Single document re-index adapter for service pipelines."""
        b_doc = dict(book_doc or {})
        b_doc["_id"] = book_id or b_doc.get("_id")
        b_doc["title"] = title or b_doc.get("title") or filename
        b_doc["author"] = author or b_doc.get("author") or "Unknown Author"
        b_doc["category"] = category or b_doc.get("category") or "General"
        if file_path:
            b_doc["local_path"] = file_path

        res = self.index_single_book(
            book_doc=b_doc,
            enable_ocr=enable_ocr,
            max_ocr_pages=max_ocr_pages,
            enable_metadata_fallback=enable_metadata_fallback,
            rebuild_bm25=rebuild_bm25,
            sub_progress_cb=sub_progress_cb,
        )
        return res.get("chunks_persisted", 0)

    def delete_source(self, source_name: str, book_id: Optional[str] = None) -> bool:
        if self.collection is None:
            return False
        try:
            target_id = book_id or source_name
            with CHROMA_LOCK:
                try:
                    self.collection.delete(where={"book_id": str(target_id)})
                except Exception:
                    pass
                if source_name and source_name != target_id:
                    try:
                        self.collection.delete(where={"source": str(source_name)})
                    except Exception:
                        pass
            self._clear_cache()
            if self.enable_hybrid_bm25 and self._bm25_docs:
                self.refresh_bm25_index()
            return True
        except Exception as e:
            logger.error("Failed to delete source '%s': %s", source_name, e)
            return False

    @lru_cache(maxsize=128)
    def _encode_query(self, query_text: str) -> tuple:
        clean_q = query_text.strip()
        if "bge" in EMBEDDING_MODEL_NAME.lower():
            clean_q = f"{BGE_QUERY_PREFIX}{clean_q}"
        vec = self.embedder.encode(clean_q, normalize_embeddings=True)
        return tuple(vec.tolist())

    def _get_cached(self, key: tuple, now: float) -> Optional[List[dict]]:
        with self._cache_lock:
            if key in self._query_cache:
                timestamp, results = self._query_cache[key]
                if now - timestamp < CACHE_TTL_SECONDS:
                    self._query_cache.move_to_end(key)
                    return [dict(r) for r in results]
                else:
                    del self._query_cache[key]
        return None

    def _set_cached(self, key: tuple, now: float, results: List[dict]) -> None:
        with self._cache_lock:
            self._query_cache[key] = (now, [dict(r) for r in results])
            if len(self._query_cache) > CACHE_MAX_SIZE:
                self._query_cache.popitem(last=False)

    def _clear_cache(self) -> None:
        with self._cache_lock:
            self._query_cache.clear()

    def search_with_metadata(
        self,
        query: str,
        top_k: int = 3,
        filter_source: Optional[str] = None,
        book_id: Optional[str] = None,
        candidate_sources: Optional[List[str]] = None,
        candidate_book_ids: Optional[List[str]] = None,
        course_code_scope: Optional[str] = None,
        fallback_to_library: bool = False,
        max_distance: Optional[float] = RAG_MAX_DISTANCE,
    ) -> List[dict]:
        """
        Queries ChromaDB with metadata scoping, dynamic alias resolution, and strict distance filtering.
        Supports multi-book course syllabus scoping via native $in operator without premature loop breaks.
        """
        if not query or not query.strip():
            return []

        c_srcs = tuple(sorted(candidate_sources)) if candidate_sources else ()
        c_bids = tuple(sorted(candidate_book_ids)) if candidate_book_ids else ()
        cache_key = (
            query.strip().lower(),
            top_k,
            str(filter_source or ""),
            str(book_id or ""),
            c_srcs,
            c_bids,
            str(course_code_scope or ""),
            fallback_to_library,
            max_distance,
        )
        now = time.time()
        cached = self._get_cached(cache_key, now)
        if cached is not None:
            return cached

        if self.collection is None:
            return []

        effective_threshold = RAG_MAX_DISTANCE if max_distance is None else max_distance
        try:
            query_embedding = [list(self._encode_query(query.strip()))]
        except Exception as emb_err:
            logger.error("Failed to generate query embedding: %s", emb_err)
            return []

        matched_chunks: List[dict] = []

        all_book_ids = list(candidate_book_ids or [])
        if book_id and book_id not in all_book_ids:
            all_book_ids.append(book_id)

        all_sources = list(candidate_sources or [])
        if filter_source and filter_source not in all_sources:
            all_sources.append(filter_source)

        is_scoped = bool(all_book_ids or all_sources)
        candidate_pool_size = max(top_k * 3, 16) if (self.enable_hybrid_bm25 or ENABLE_RERANKER) else max(top_k, 1)

        if not is_scoped:
            try:
                with CHROMA_LOCK:
                    results = self.collection.query(
                        query_embeddings=query_embedding,
                        n_results=candidate_pool_size,
                        include=["documents", "metadatas", "distances"],
                    )
                matched_chunks = self._filter_results(results, effective_threshold)
            except Exception as exc:
                logger.error("Unscoped ChromaDB query failed: %s", exc)
        else:
            # 1. Native Multi-Book ChromaDB Filtering ($in operator across all syllabus textbooks)
            if all_book_ids:
                clean_bids = [str(bid).strip() for bid in all_book_ids if str(bid).strip()]
                if clean_bids:
                    where_clause = {"book_id": clean_bids[0]} if len(clean_bids) == 1 else {"book_id": {"$in": clean_bids}}
                    try:
                        with CHROMA_LOCK:
                            res = self.collection.query(
                                query_embeddings=query_embedding,
                                n_results=candidate_pool_size,
                                where=where_clause,
                                include=["documents", "metadatas", "distances"],
                            )
                        hits = self._filter_results(res, effective_threshold)
                        if hits:
                            matched_chunks.extend(hits)
                    except Exception as e:
                        logger.debug("ChromaDB multi-book query error (%s), attempting per-book fallback: %s", clean_bids, e)
                        for bid in clean_bids:
                            try:
                                with CHROMA_LOCK:
                                    res = self.collection.query(
                                        query_embeddings=query_embedding,
                                        n_results=candidate_pool_size,
                                        where={"book_id": str(bid)},
                                        include=["documents", "metadatas", "distances"],
                                    )
                                hits = self._filter_results(res, effective_threshold)
                                if hits:
                                    matched_chunks.extend(hits)
                            except Exception:
                                pass

            # 2. Try Candidate Sources / Filename Aliases if book_id yielded nothing
            if not matched_chunks and all_sources:
                resolved_source = self.resolve_source_name(all_sources)
                query_sources = [resolved_source] if resolved_source else all_sources
                clean_srcs = [str(src).strip() for src in query_sources if str(src).strip()]
                if clean_srcs:
                    where_src = {"source": clean_srcs[0]} if len(clean_srcs) == 1 else {"source": {"$in": clean_srcs}}
                    try:
                        with CHROMA_LOCK:
                            src_results = self.collection.query(
                                query_embeddings=query_embedding,
                                n_results=candidate_pool_size,
                                where=where_src,
                                include=["documents", "metadatas", "distances"],
                            )
                        hits = self._filter_results(src_results, effective_threshold)
                        if hits:
                            matched_chunks.extend(hits)
                    except Exception as exc:
                        logger.debug("Source query failed for %s: %s", clean_srcs, exc)

            # 3. Optional fallback to entire library only if scoped search yielded nothing and allowed
            if not matched_chunks and fallback_to_library:
                try:
                    with CHROMA_LOCK:
                        fallback_results = self.collection.query(
                            query_embeddings=query_embedding,
                            n_results=candidate_pool_size,
                            include=["documents", "metadatas", "distances"],
                        )
                    matched_chunks = self._filter_results(fallback_results, effective_threshold)
                except Exception as exc:
                    logger.error("Fallback ChromaDB query failed: %s", exc)

        # Stage 2: Sparse BM25 Keyword Search & Reciprocal Rank Fusion
        if self.enable_hybrid_bm25 and self._bm25_docs:
            bm25_hits = self._search_bm25(
                query=query.strip(),
                top_k=candidate_pool_size,
                candidate_book_ids=all_book_ids if is_scoped else None,
                candidate_sources=all_sources if is_scoped else None,
            )
            if bm25_hits:
                matched_chunks = self._reciprocal_rank_fusion(matched_chunks, bm25_hits)

        # Stage 3: Cross-Encoder Neural Reranking
        if ENABLE_RERANKER and self.reranker is not None and matched_chunks:
            matched_chunks = self._rerank_candidates(
                query=query.strip(),
                candidates=matched_chunks,
                top_k=top_k,
            )
        else:
            matched_chunks = matched_chunks[:top_k]

        self._set_cached(cache_key, now, matched_chunks)
        return matched_chunks

    def _search_bm25(
        self,
        query: str,
        top_k: int = 15,
        candidate_book_ids: Optional[List[str]] = None,
        candidate_sources: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        with self._bm25_lock:
            if self._bm25_index is None or not self._bm25_docs:
                self.load_bm25_cache_if_available()
            if self._bm25_index is None or not self._bm25_docs:
                return []
            index = self._bm25_index
            docs = self._bm25_docs

        tokens = tokenize_for_bm25(query)
        if not tokens:
            return []

        try:
            scores = index.get_scores(tokens)
            ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

            target_bids = set(str(b) for b in candidate_book_ids) if candidate_book_ids else None
            target_srcs = set(str(s).lower() for s in candidate_sources) if candidate_sources else None

            hits: List[Dict[str, Any]] = []
            for idx in ranked_indices:
                score = scores[idx]
                if score <= 0:
                    break
                candidate = docs[idx]
                meta = candidate.get("metadata") or {}

                if target_bids and str(meta.get("book_id")) not in target_bids:
                    continue
                if target_srcs and str(meta.get("source", "")).lower() not in target_srcs:
                    continue

                hits.append({
                    "id": candidate.get("id"),
                    "text": candidate.get("text"),
                    "metadata": meta,
                    "bm25_score": float(score),
                    "distance": 0.0,
                    "source": meta.get("source", "Library Document"),
                    "book_id": meta.get("book_id", ""),
                    "title": meta.get("title", meta.get("source", "Document")),
                    "page": meta.get("page"),
                    "section_type": meta.get("section_type", "page"),
                })
                if len(hits) >= top_k:
                    break
            return hits
        except Exception as e:
            logger.debug("BM25 query notice: %s", e)
            return []

    @staticmethod
    def _reciprocal_rank_fusion(
        vector_results: List[Dict[str, Any]],
        bm25_results: List[Dict[str, Any]],
        k: int = 60,
    ) -> List[Dict[str, Any]]:
        fused_scores: Dict[str, float] = {}
        chunk_lookup: Dict[str, Dict[str, Any]] = {}

        for rank, item in enumerate(vector_results, start=1):
            cid = item.get("id") or item.get("text", "")[:64]
            chunk_lookup[cid] = item
            fused_scores[cid] = fused_scores.get(cid, 0.0) + (1.0 / (k + rank))

        for rank, item in enumerate(bm25_results, start=1):
            cid = item.get("id") or item.get("text", "")[:64]
            if cid not in chunk_lookup:
                chunk_lookup[cid] = item
            fused_scores[cid] = fused_scores.get(cid, 0.0) + (1.0 / (k + rank))

        sorted_ids = sorted(
            fused_scores.keys(), key=lambda cid: fused_scores[cid], reverse=True
        )

        merged: List[Dict[str, Any]] = []
        for cid in sorted_ids:
            entry = dict(chunk_lookup[cid])
            entry["rrf_score"] = round(fused_scores[cid], 6)
            merged.append(entry)
        return merged

    def _rerank_candidates(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        if ENABLE_RERANKER and self.reranker is not None:
            try:
                pairs = [(query, c.get("text", "")) for c in candidates]
                scores = self.reranker.predict(pairs)
                for item, s in zip(candidates, scores):
                    item["rerank_score"] = float(s)
                candidates.sort(key=lambda x: x.get("rerank_score", -999.0), reverse=True)
            except Exception as re_err:
                logger.debug("CrossEncoder rerank note: %s", re_err)

        return candidates[:top_k]

    def get_known_sources(self) -> set:
        """Returns cached distinct source identifiers present in ChromaDB."""
        now = time.time()
        if hasattr(self, "_known_sources_cache") and (now - getattr(self, "_known_sources_ts", 0) < 60.0):
            return self._known_sources_cache
        try:
            if self.collection is not None:
                with CHROMA_LOCK:
                    data = self.collection.get(include=["metadatas"])
                self._known_sources_cache = set(m.get("source") for m in data.get("metadatas", []) if m and m.get("source"))
                self._known_sources_ts = now
                return self._known_sources_cache
        except Exception as err:
            logger.debug("Notice getting known sources: %s", err)
        return set()

    def resolve_source_name(self, candidates: List[str]) -> Optional[str]:
        known = self.get_known_sources()
        if not known:
            return candidates[0] if candidates else None

        for c in candidates:
            if c in known:
                return c

        known_lower_map = {k.lower(): k for k in known}
        for c in candidates:
            if c.lower() in known_lower_map:
                return known_lower_map[c.lower()]

        known_stem_map = {Path(k).stem.lower(): k for k in known}
        for c in candidates:
            stem = Path(c).stem.lower()
            if stem in known_stem_map:
                return known_stem_map[stem]

        for c in candidates:
            c_clean = c.lower().replace("_", " ").replace("-", " ")
            for k in known:
                k_clean = k.lower().replace("_", " ").replace("-", " ")
                if c_clean in k_clean or k_clean in c_clean:
                    return k

        return candidates[0] if candidates else None

    def get_book_intro_chunks(
        self,
        book_id: Optional[str] = None,
        candidate_sources: Optional[List[str]] = None,
        limit: int = 5,
    ) -> List[dict]:
        if self.collection is None:
            return []

        where_clause = None
        if book_id:
            where_clause = {"book_id": str(book_id)}
        else:
            resolved = self.resolve_source_name(candidate_sources or [])
            if resolved:
                where_clause = {"source": resolved}

        if not where_clause:
            return []

        try:
            with CHROMA_LOCK:
                res = self.collection.get(where=where_clause, limit=max(limit * 6, 40))
            docs = res.get("documents", [])
            metas = res.get("metadatas", [])
            if not docs and book_id and candidate_sources:
                resolved = self.resolve_source_name(candidate_sources)
                if resolved:
                    with CHROMA_LOCK:
                        res = self.collection.get(where={"source": resolved}, limit=max(limit * 6, 40))
                    docs = res.get("documents", [])
                    metas = res.get("metadatas", [])

            chunks = []
            for d, m in zip(docs, metas):
                text_clean = (d or "").strip()
                if len(text_clean) < 80:
                    continue
                chunks.append({
                    "text": text_clean,
                    "metadata": m or {},
                    "chunk_index": (m or {}).get("chunk_index", 999999),
                    "distance": 0.0,
                })

            chunks.sort(key=lambda x: x["chunk_index"])
            return chunks[:limit]
        except Exception as exc:
            logger.warning("Error fetching intro chunks: %s", exc)
            return []

    def update_book_metadata(self, book_id: str, new_title: str) -> int:
        if self.collection is None or not book_id:
            return 0
        try:
            with CHROMA_LOCK:
                res = self.collection.get(where={"book_id": str(book_id)}, include=["metadatas"])
            chunk_ids = res.get("ids", [])
            metadatas = res.get("metadatas", [])
            if not chunk_ids:
                return 0
            new_metas = []
            for m in metadatas:
                um = dict(m)
                um["title"] = str(new_title)
                new_metas.append(um)
            with CHROMA_LOCK:
                for i in range(0, len(chunk_ids), 500):
                    self.collection.update(ids=chunk_ids[i:i + 500], metadatas=new_metas[i:i + 500])
            self._clear_cache()
            return len(chunk_ids)
        except Exception as exc:
            logger.warning("Error updating book metadata in ChromaDB: %s", exc)
            return 0

    @staticmethod
    def _filter_results(raw_results: dict, max_distance: float) -> List[dict]:
        docs = (raw_results.get("documents") or [[]])[0]
        metas = (raw_results.get("metadatas") or [[]])[0]
        dists = (raw_results.get("distances") or [[]])[0]

        verified: List[dict] = []
        for doc, meta, dist in zip(docs, metas, dists):
            if not doc or not doc.strip():
                continue
            if dist is not None and float(dist) <= float(max_distance):
                meta_dict = meta or {}
                verified.append(
                    {
                        "text": doc.strip(),
                        "metadata": meta_dict,
                        "distance": float(dist),
                        "source": meta_dict.get("source", "Library Document"),
                        "book_id": meta_dict.get("book_id", ""),
                        "title": meta_dict.get("title", meta_dict.get("source", "Document")),
                        "page": meta_dict.get("page"),
                        "section_type": meta_dict.get("section_type", "page"),
                    }
                )
        return verified

    def get_adjacent_chunks(
        self,
        book_id: Optional[str],
        source: Optional[str],
        chunk_index: int,
        window: int = 1,
    ) -> List[dict]:
        if chunk_index is None or window <= 0 or self.collection is None:
            return []

        target_indices = [
            idx for idx in range(chunk_index - window, chunk_index + window + 1)
            if idx >= 0 and idx != chunk_index
        ]
        if not target_indices:
            return []

        conditions: List[Dict[str, Any]] = [{"chunk_index": {"$in": target_indices}}]
        if book_id:
            conditions.append({"book_id": str(book_id)})
        elif source:
            conditions.append({"source": str(source)})

        where_filter = {"$and": conditions} if len(conditions) > 1 else conditions[0]
        try:
            with CHROMA_LOCK:
                res = self.collection.get(
                    where=where_filter,
                    include=["documents", "metadatas"],
                )
            docs = res.get("documents") or []
            metas = res.get("metadatas") or []
            return [
                {"text": d.strip(), "metadata": m or {}, "distance": 0.0}
                for d, m in zip(docs, metas)
                if d and d.strip()
            ]
        except Exception as exc:
            logger.debug("Adjacent chunk expansion skipped: %s", exc)
            return []

    def get_document_coverage_chunks(
        self,
        book_id: Optional[str] = None,
        filter_source: Optional[str] = None,
        max_chunks: int = 10,
        start_page: int = 1
    ) -> List[dict]:
        if self.collection is None:
            return []
        try:
            res = None
            with CHROMA_LOCK:
                if book_id:
                    try:
                        res = self.collection.get(where={"book_id": str(book_id)})
                    except Exception:
                        pass
                if (not res or not res.get('documents') or len(res['documents']) == 0) and filter_source:
                    try:
                        res = self.collection.get(where={"source": str(filter_source)})
                    except Exception:
                        pass
            if not res or not res.get('documents'):
                return []

            docs = res['documents']
            metas = res.get('metadatas') or [{}] * len(docs)
            combined = []
            for d, m in zip(docs, metas):
                if not d or not d.strip():
                    continue
                meta_dict = m if isinstance(m, dict) else {}
                p = int(meta_dict.get('page') or 1)
                idx = int(meta_dict.get('chunk_index') or 0)
                combined.append((p, idx, d, meta_dict))

            if not combined:
                return []

            combined.sort(key=lambda x: (x[0], x[1]))
            if start_page > 1:
                filtered_pages = [item for item in combined if item[0] >= start_page]
                if filtered_pages:
                    combined = filtered_pages

            total = len(combined)
            if total <= max_chunks:
                selected = combined
            else:
                step = (total - 1) / float(max_chunks - 1) if max_chunks > 1 else total
                selected = [combined[int(round(i * step))] for i in range(max_chunks)]

            output = []
            for p, idx, d, m in selected:
                cleaned = d[:1500].strip() if len(d) > 1500 else d.strip()
                output.append({
                    "text": cleaned,
                    "source": m.get('source', 'Library Document'),
                    "book_id": m.get('book_id', book_id or ''),
                    "title": m.get('title', m.get('source', 'Document')),
                    "page": p,
                    "section_type": m.get('section_type', 'page'),
                    "distance": 0.0
                })
            return output
        except Exception as e:
            logger.error("Coverage Chunks Retrieval Error: %s", e)
            return []

    def get_chunks_by_pages(
        self,
        book_id: Optional[str] = None,
        filter_source: Optional[str] = None,
        pages: Optional[List[int]] = None
    ) -> List[dict]:
        if self.collection is None or not pages:
            return []
        try:
            res = None
            with CHROMA_LOCK:
                if book_id:
                    try:
                        res = self.collection.get(where={"book_id": str(book_id)})
                    except Exception:
                        pass
                if (not res or not res.get('documents')) and filter_source:
                    try:
                        res = self.collection.get(where={"source": str(filter_source)})
                    except Exception:
                        pass
            if not res or not res.get('documents'):
                return []

            target_pages = set(pages)
            docs = res['documents']
            metas = res.get('metadatas') or [{}] * len(docs)
            out = []
            for d, m in zip(docs, metas):
                p = int(m.get('page') or 0)
                if p in target_pages:
                    cleaned = d[:1500].strip() if len(d) > 1500 else d.strip()
                    out.append({
                        "text": cleaned,
                        "source": m.get('source', 'Library Document'),
                        "book_id": m.get('book_id', book_id or ''),
                        "title": m.get('title', m.get('source', 'Document')),
                        "page": p,
                        "section_type": m.get('section_type', 'page'),
                        "distance": 0.0
                    })
            out.sort(key=lambda x: (x['page'], x['text']))
            return out
        except Exception as e:
            logger.error("Error in get_chunks_by_pages: %s", e)
            return []

    def get_collection_stats(self) -> dict:
        if self.collection is None:
            return {"total_chunks": 0, "status": "Offline"}
        try:
            with CHROMA_LOCK:
                cnt = self.collection.count()
            return {
                "total_chunks": cnt,
                "status": "Online",
                "storage_path": self.persist_directory
            }
        except Exception as e:
            return {"total_chunks": 0, "status": f"Error: {e}"}

    def search(
        self,
        query: str,
        top_k: int = 3,
        filter_source: Optional[str] = None,
        book_id: Optional[str] = None,
        fallback_to_library: bool = False
    ) -> List[str]:
        hits = self.search_with_metadata(
            query,
            top_k=top_k,
            filter_source=filter_source,
            book_id=book_id,
            fallback_to_library=fallback_to_library
        )
        if not hits:
            return []
        formatted = []
        for h in hits:
            source = h.get('metadata', {}).get('source') or h.get('source', 'Archive')
            page_val = h.get('metadata', {}).get('page') or h.get('page')
            page_info = f" (Page {page_val})" if page_val else ""
            formatted.append(f"[Source: {source}{page_info}]\n{h.get('text', '')}")
        return formatted

    def ensure_initialized(self) -> bool:
        if self.collection is not None and self.enable_hybrid_bm25 and self._bm25_index is None:
            self.refresh_bm25_index()
        return self.collection is not None

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        text = text.replace('\x00', '')
        return text.encode('utf-8', 'ignore').decode('utf-8').strip()

    def _smart_chunker(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=overlap,
                separators=["\n\n", "\n", ". ", " ", ""]
            )
            return text_splitter.split_text(text)
        except Exception:
            chunks = []
            start = 0
            step = max(1, chunk_size - overlap)
            while start < len(text):
                end = min(start + chunk_size, len(text))
                chunks.append(text[start:end])
                start += step
            return chunks

    def ingest_text(self, text: str, filename: str, book_id: Optional[str] = None, title: Optional[str] = None) -> int:
        if self.collection is None:
            return 0
        clean = self._clean_text(text)
        if not clean or len(clean) < 20:
            return 0

        chunks = self._smart_chunker(clean)
        if not chunks:
            return 0

        doc_title = title or filename.rsplit('.', 1)[0].replace('_', ' ')
        ids = [f"{filename}_{i}_{str(uuid.uuid4())[:8]}" for i in range(len(chunks))]
        metadatas = [
            {
                "source": str(filename),
                "book_id": str(book_id or ""),
                "title": str(doc_title),
                "page": 1,
                "chunk_index": i
            }
            for i in range(len(chunks))
        ]

        batch_size = 100
        persisted = 0
        for i in range(0, len(chunks), batch_size):
            b_docs = chunks[i:i + batch_size]
            b_meta = metadatas[i:i + batch_size]
            b_ids = ids[i:i + batch_size]
            try:
                embeddings = self.embedder.encode(b_docs, normalize_embeddings=True).tolist()
                with CHROMA_LOCK:
                    self.collection.upsert(documents=b_docs, embeddings=embeddings, metadatas=b_meta, ids=b_ids)
                persisted += len(b_docs)
            except Exception as e:
                logger.error("Error adding chunk batch to ChromaDB: %s", e)

        self._clear_cache()
        if persisted > 0 and self.enable_hybrid_bm25:
            self.refresh_bm25_index()
        return persisted


class ScopedHybridRAGPipeline:
    """
    Lightweight, thread-safe scoped Hybrid RAG Pipeline for course-syllabus filtering.
    Enforces native ChromaDB $in multi-book queries, scoped BM25 token matching,
    and out-of-scope distance guarding.
    """
    def __init__(
        self,
        chroma_collection,
        embedder,
        bm25_cache=None,
        reranker=None,
        rag_max_distance: float = 0.68,
    ) -> None:
        self.collection = chroma_collection
        self.embedder = embedder
        self.bm25_cache = bm25_cache
        self.reranker = reranker
        self.rag_max_distance = rag_max_distance

    def search_with_metadata(
        self,
        query: str,
        candidate_book_ids: Optional[List[str]] = None,
        course_code_scope: Optional[str] = None,
        top_k: int = 5,
        candidate_pool_size: int = 16,
    ) -> Dict[str, Any]:
        clean_query = query.strip()
        query_embedding = self.embedder.encode(
            [clean_query],
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

        where_clause: Optional[Dict[str, Any]] = None
        allowed_bids_set: Optional[set] = None

        if candidate_book_ids:
            clean_bids = [str(bid).strip() for bid in candidate_book_ids if str(bid).strip()]
            allowed_bids_set = set(clean_bids)
            if len(clean_bids) == 1:
                where_clause = {"book_id": clean_bids[0]}
            elif len(clean_bids) > 1:
                where_clause = {"book_id": {"$in": clean_bids}}

        with CHROMA_LOCK:
            chroma_res = self.collection.query(
                query_embeddings=query_embedding,
                n_results=candidate_pool_size,
                where=where_clause,
                include=["documents", "metadatas", "distances"],
            )

        vector_hits: List[Dict[str, Any]] = []
        best_distance = 999.0

        if chroma_res and chroma_res.get("ids") and chroma_res["ids"][0]:
            for cid, doc_text, meta, dist in zip(
                chroma_res["ids"][0],
                chroma_res["documents"][0],
                chroma_res["metadatas"][0],
                chroma_res["distances"][0],
            ):
                d_val = float(dist)
                if d_val < best_distance:
                    best_distance = d_val
                if d_val <= self.rag_max_distance:
                    vector_hits.append(
                        {
                            "id": cid,
                            "text": doc_text,
                            "metadata": meta or {},
                            "distance": d_val,
                        }
                    )

        bm25_hits: List[Dict[str, Any]] = []
        if self.bm25_cache is not None:
            bm25_hits = self._search_bm25_scoped(
                query=clean_query,
                allowed_bids=allowed_bids_set,
                limit=candidate_pool_size,
            )

        if course_code_scope and not vector_hits and not bm25_hits:
            return {
                "chunks": [],
                "out_of_scope": True,
                "course_code_scope": course_code_scope,
                "best_distance": best_distance,
                "fallback_message": (
                    f"I couldn't find verified information about that topic in your approved "
                    f"**{course_code_scope}** course textbooks."
                ),
            }

        fused = self._reciprocal_rank_fusion(vector_hits, bm25_hits)[:candidate_pool_size]

        if self.reranker is not None and fused:
            pairs: List[Tuple[str, str]] = [(clean_query, item["text"]) for item in fused]
            scores = self.reranker.predict(pairs)
            for item, sc in zip(fused, scores):
                item["rerank_score"] = float(sc)
            fused.sort(key=lambda x: x.get("rerank_score", -999.0), reverse=True)

        return {
            "chunks": fused[:top_k],
            "out_of_scope": False,
            "course_code_scope": course_code_scope,
            "best_distance": best_distance,
            "fallback_message": None,
        }

    def _search_bm25_scoped(
        self,
        query: str,
        allowed_bids: Optional[set],
        limit: int = 16,
    ) -> List[Dict[str, Any]]:
        if not self.bm25_cache or not getattr(self.bm25_cache, "bm25", None):
            return []

        tokens = re.findall(r"\w+", query.lower())
        if not tokens:
            return []

        scores = self.bm25_cache.bm25.get_scores(tokens)
        docs = getattr(self.bm25_cache, "docs", [])

        candidate_indices = []
        for idx, sc in enumerate(scores):
            if sc <= 0.0:
                continue
            if allowed_bids is not None:
                doc_bid = str(docs[idx].get("metadata", {}).get("book_id", ""))
                if doc_bid not in allowed_bids:
                    continue
            candidate_indices.append(idx)

        candidate_indices.sort(key=lambda i: scores[i], reverse=True)
        return [
            {
                "id": docs[i]["id"],
                "text": docs[i]["text"],
                "metadata": docs[i]["metadata"],
                "bm25_score": float(scores[i]),
            }
            for i in candidate_indices[:limit]
        ]

    @staticmethod
    def _reciprocal_rank_fusion(
        vector_hits: List[Dict[str, Any]],
        bm25_hits: List[Dict[str, Any]],
        k: int = 60,
    ) -> List[Dict[str, Any]]:
        scores: Dict[str, float] = {}
        lookup: Dict[str, Dict[str, Any]] = {}

        for rank, item in enumerate(vector_hits, start=1):
            cid = item["id"]
            lookup[cid] = item
            scores[cid] = scores.get(cid, 0.0) + (1.0 / (k + rank))

        for rank, item in enumerate(bm25_hits, start=1):
            cid = item["id"]
            lookup.setdefault(cid, item)
            scores[cid] = scores.get(cid, 0.0) + (1.0 / (k + rank))

        ranked_ids = sorted(scores.keys(), key=lambda c: scores[c], reverse=True)
        return [lookup[cid] for cid in ranked_ids]


# Backwards compatibility aliases
TarsArchive = ResilientRAGPipeline
RAGPipeline = ResilientRAGPipeline
EnhancedRAGPipeline = ResilientRAGPipeline
tars_archive = ResilientRAGPipeline()

__all__ = [
    "CHROMA_LOCK",
    "SEARCH_DIRECTORIES",
    "resolve_missing_book_path",
    "build_catalog_fallback_chunks",
    "chunk_pages_with_headers",
    "tokenize_for_bm25",
    "build_contextual_chunk",
    "ResilientRAGPipeline",
    "ScopedHybridRAGPipeline",
    "TarsArchive",
    "RAGPipeline",
    "EnhancedRAGPipeline",
    "tars_archive",
]