import logging
import uuid
import os
import time
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from core.config import settings as app_settings

# Setup Logger
logger = logging.getLogger("TARS_ARCHIVE")

class TarsArchive:
    """
    Persistent Vector Knowledge Base using ChromaDB and SentenceTransformers.
    Optimized with lazy initialization and thread safety.
    """
    def __init__(self):
        self.db_path = app_settings.CHROMA_PATH
        self.local_model_path = app_settings.BASE_DIR / "models" / "all-MiniLM-L6-v2"
        self.client = None
        self.collection = None
        self.embedding_fn = None
        self._init_lock = threading.Lock()
        self._is_initialized = False
        self._query_cache: Dict[tuple, Any] = {}
        self._cache_lock = threading.Lock()
        logger.info("TARS Archive registered (Lazy Loading Mode).")

    def ensure_initialized(self) -> bool:
        """
        Thread-safely initializes ChromaDB and embedding models on first access.
        """
        if self._is_initialized and self.collection is not None:
            return True

        with self._init_lock:
            if self._is_initialized and self.collection is not None:
                return True

            try:
                import chromadb
                from chromadb.config import Settings
                from chromadb.utils import embedding_functions

                self.db_path.mkdir(parents=True, exist_ok=True)

                # Offline Embedding Model check
                if self.local_model_path.exists():
                    logger.info(f"OFFLINE MODE: Using local embedding model at {self.local_model_path}")
                    os.environ["TRANSFORMERS_OFFLINE"] = "1"
                    os.environ["HF_HUB_OFFLINE"] = "1"
                    model_target = str(self.local_model_path)
                else:
                    logger.warning("Local embedding model not found. Using HuggingFace model 'all-MiniLM-L6-v2'.")
                    model_target = "all-MiniLM-L6-v2"

                try:
                    import torch
                    torch.set_num_threads(min(4, os.cpu_count() or 1))
                except Exception:
                    pass

                self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=model_target,
                    device="cpu"  # Keep CPU to save VRAM for the LLM
                )

                self.client = chromadb.PersistentClient(
                    path=str(self.db_path),
                    settings=Settings(anonymized_telemetry=False)
                )

                self.collection = self.client.get_or_create_collection(
                    name="tars_knowledge_base",
                    embedding_function=self.embedding_fn
                )

                doc_count = self.collection.count()
                logger.info(f"TARS Archive ONLINE. Loaded {doc_count} documents.")
                self._is_initialized = True
                return True

            except Exception as e:
                logger.critical(f"ChromaDB Initialization Failed: {e}", exc_info=True)
                self.collection = None
                self._is_initialized = False
                return False

    def _clear_cache(self):
        """Clears cached semantic query results upon data mutation."""
        with self._cache_lock:
            self._query_cache.clear()

    def _clean_text(self, text: str) -> str:
        """Sanitizes text to remove Null bytes and encoding errors."""
        if not text:
            return ""
        text = text.replace('\x00', '')
        return text.encode('utf-8', 'ignore').decode('utf-8').strip()

    def _smart_chunker(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """
        Splits text into chunks preserving paragraph and sentence boundaries.
        Uses langchain_text_splitters RecursiveCharacterTextSplitter.
        """
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=overlap,
                separators=["\n\n", "\n", ". ", " ", ""]
            )
            return text_splitter.split_text(text)
        except Exception:
            # Fallback simple chunking if text splitter is unavailable
            chunks = []
            start = 0
            while start < len(text):
                end = min(start + chunk_size, len(text))
                chunks.append(text[start:end])
                start += chunk_size - overlap
            return chunks

    def ingest_text(self, text: str, filename: str, book_id: Optional[str] = None, title: Optional[str] = None) -> int:
        """Directly chunks and ingests extracted clean text into ChromaDB with metadata."""
        if not self.ensure_initialized() or not self.collection:
            return 0

        clean = self._clean_text(text)
        if not clean or len(clean) < 20:
            return 0

        # Check if already indexed
        try:
            where_check = {"book_id": book_id} if book_id else {"source": filename}
            existing = self.collection.get(where=where_check)
            if existing and len(existing['ids']) > 0:
                logger.info(f"Document '{filename}' already in memory ({len(existing['ids'])} chunks).")
                return len(existing['ids'])
        except Exception:
            pass

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

        # Batch insert into ChromaDB (max 200 chunks per batch to prevent memory spikes)
        batch_size = 200
        for i in range(0, len(chunks), batch_size):
            b_docs = chunks[i:i + batch_size]
            b_meta = metadatas[i:i + batch_size]
            b_ids = ids[i:i + batch_size]
            try:
                self.collection.add(
                    documents=b_docs,
                    metadatas=b_meta,
                    ids=b_ids
                )
            except Exception as e:
                logger.error(f"Error adding chunk batch to ChromaDB: {e}")

        self._clear_cache()
        logger.info(f"Persisted {len(chunks)} chunks from '{filename}' into vector store.")
        return len(chunks)

    def ingest_document(self, file_path: str, filename: str, book_id: Optional[str] = None, title: Optional[str] = None) -> int:
        """
        Extracts structured document units (pages/slides) and ingests them into ChromaDB
        with precise page numbers, book_id, and titles for pinpoint RAG citations.
        """
        if not self.ensure_initialized() or not self.collection:
            return 0

        file_p = Path(file_path)
        if not file_p.exists() or file_p.stat().st_size == 0:
            logger.warning(f"Skipping '{filename}': File not found or empty.")
            return 0

        # Check if already indexed
        try:
            where_check = {"book_id": book_id} if book_id else {"source": filename}
            existing = self.collection.get(where=where_check)
            if existing and len(existing['ids']) > 0:
                logger.info(f"Document '{filename}' already in memory ({len(existing['ids'])} chunks).")
                return len(existing['ids'])
        except Exception:
            pass

        from core.utils.text_extractor import extract_document_structure
        sections = extract_document_structure(str(file_p))
        if not sections:
            # Fallback to direct text ingestion
            from core.utils.text_extractor import extract_text_from_file
            raw_text = extract_text_from_file(str(file_p))
            return self.ingest_text(raw_text, filename, book_id=book_id, title=title)

        doc_title = title or filename.rsplit('.', 1)[0].replace('_', ' ')
        all_chunks = []
        all_metas = []
        all_ids = []

        chunk_counter = 0
        for sec in sections:
            page_num = sec.get('page', 1)
            sec_type = sec.get('type', 'page')
            sec_text = self._clean_text(sec.get('text', ''))
            if not sec_text or len(sec_text) < 15:
                continue

            sec_chunks = self._smart_chunker(sec_text, chunk_size=900, overlap=150)
            for c in sec_chunks:
                all_chunks.append(c)
                all_metas.append({
                    "source": str(filename),
                    "book_id": str(book_id or ""),
                    "title": str(doc_title),
                    "page": int(page_num),
                    "section_type": str(sec_type),
                    "chunk_index": chunk_counter
                })
                all_ids.append(f"{filename}_p{page_num}_{chunk_counter}_{str(uuid.uuid4())[:6]}")
                chunk_counter += 1

        if not all_chunks:
            return 0

        # Batch insert into ChromaDB
        batch_size = 200
        for i in range(0, len(all_chunks), batch_size):
            b_docs = all_chunks[i:i + batch_size]
            b_meta = all_metas[i:i + batch_size]
            b_ids = all_ids[i:i + batch_size]
            try:
                self.collection.add(
                    documents=b_docs,
                    metadatas=b_meta,
                    ids=b_ids
                )
            except Exception as e:
                logger.error(f"Error adding chunk batch to ChromaDB: {e}")

        self._clear_cache()
        logger.info(f"Persisted {len(all_chunks)} structured page-aware chunks for '{filename}'.")
        return len(all_chunks)

    def ingest_file(self, file_path: str, filename: str, book_id: Optional[str] = None) -> int:
        """Reads a file, chunks it with page metadata, and stores it in ChromaDB."""
        return self.ingest_document(file_path, filename, book_id=book_id)

    def search_with_metadata(
        self,
        query: str,
        top_k: int = 4,
        filter_source: Optional[str] = None,
        book_id: Optional[str] = None,
        fallback_to_library: bool = False,
        max_distance: Optional[float] = 1.35
    ) -> List[dict]:
        """
        Queries ChromaDB vector database with source metadata, page numbers, and similarity distances.
        Supports filtering strictly by book_id or source filename without leaking cross-book data.
        """
        if not self.ensure_initialized() or not self.collection:
            return []

        cache_key = (str(query).strip().lower(), top_k, str(filter_source or ""), str(book_id or ""), fallback_to_library, max_distance)
        now = time.time()
        with self._cache_lock:
            if cache_key in self._query_cache:
                ts, hits = self._query_cache[cache_key]
                if now - ts < 120.0:
                    return [dict(h) for h in hits]

        try:
            if self.collection.count() == 0:
                return []

            where_clause = None
            if book_id:
                where_clause = {"book_id": str(book_id)}
            elif filter_source:
                where_clause = {"source": str(filter_source)}

            results = None
            if where_clause:
                try:
                    results = self.collection.query(
                        query_texts=[query],
                        n_results=top_k,
                        where=where_clause
                    )
                except Exception as query_err:
                    logger.debug(f"Scoped query error: {query_err}")

            has_scoped_hits = bool(
                results and results.get('documents') and len(results['documents']) > 0 and len(results['documents'][0]) > 0
            )

            # Security/Accuracy: Prevent cross-document contamination
            # If a specific document was targeted and no hits were found, do NOT silently fall back to other books
            if where_clause and not has_scoped_hits and not fallback_to_library:
                logger.debug(f"Scoped search for {where_clause} yielded 0 hits. Suppressing general fallback.")
                return []

            if not has_scoped_hits:
                # Query without where clause (general library search across all documents)
                results = self.collection.query(
                    query_texts=[query],
                    n_results=top_k
                )

            if not results or not results.get('documents') or len(results['documents']) == 0 or len(results['documents'][0]) == 0:
                return []

            output = []
            docs = results['documents'][0]
            metas = results['metadatas'][0] if results.get('metadatas') and len(results['metadatas']) > 0 else [{}] * len(docs)
            dists = results['distances'][0] if results.get('distances') and len(results['distances']) > 0 else [0.0] * len(docs)

            for doc, meta, dist in zip(docs, metas, dists):
                # Filter out irrelevant noise if distance exceeds threshold
                if max_distance is not None and dist is not None and dist > max_distance:
                    continue
                m = meta if isinstance(meta, dict) else {}
                output.append({
                    "text": doc,
                    "source": m.get('source', 'Library Document'),
                    "book_id": m.get('book_id', ''),
                    "title": m.get('title', m.get('source', 'Document')),
                    "page": m.get('page'),
                    "section_type": m.get('section_type', 'page'),
                    "distance": dist
                })

            with self._cache_lock:
                if len(self._query_cache) >= 200:
                    self._query_cache.clear()
                self._query_cache[cache_key] = (now, output)

            return output
        except Exception as e:
            logger.error(f"Search Query Failed: {e}")
            return []

    def search(
        self,
        query: str,
        top_k: int = 3,
        filter_source: Optional[str] = None,
        book_id: Optional[str] = None,
        fallback_to_library: bool = False
    ) -> List[str]:
        """Queries the long-term memory and returns formatted citations with page numbers."""
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
            source = h.get('source', 'Archive')
            page_info = f" (Page {h['page']})" if h.get('page') else ""
            formatted.append(f"[Source: {source}{page_info}]\n{h.get('text', '')}")
        return formatted


    def get_collection_stats(self) -> dict:
        """Returns statistics about ChromaDB knowledge store."""
        if not self.ensure_initialized() or not self.collection:
            return {"total_chunks": 0, "status": "Offline"}
        try:
            cnt = self.collection.count()
            return {
                "total_chunks": cnt,
                "status": "Online",
                "storage_path": str(self.db_path)
            }
        except Exception as e:
            return {"total_chunks": 0, "status": f"Error: {e}"}

    def delete_source(self, source_name: str, book_id: Optional[str] = None) -> bool:
        """Deletes all chunks associated with a source filename or book ID."""
        if not self.ensure_initialized() or not self.collection:
            return False

        purged = 0
        try:
            # Delete by book_id if provided
            target_id = book_id or source_name
            try:
                existing_bid = self.collection.get(where={"book_id": target_id})
                if existing_bid and existing_bid.get('ids'):
                    self.collection.delete(ids=existing_bid['ids'])
                    purged += len(existing_bid['ids'])
            except Exception:
                pass

            # Delete by source filename
            try:
                existing_src = self.collection.get(where={"source": source_name})
                if existing_src and existing_src.get('ids'):
                    self.collection.delete(ids=existing_src['ids'])
                    purged += len(existing_src['ids'])
            except Exception:
                pass

            if purged > 0:
                self._clear_cache()
                logger.info(f"Purged {purged} chunks for source: {source_name} / {book_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete source '{source_name}': {e}")
            return False

# Architectural Aliases & Singleton Instance
RAGPipeline = TarsArchive
tars_archive = TarsArchive()