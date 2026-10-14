import logging
import uuid
import os
import re
import time
import threading
from collections import OrderedDict
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from core.config import settings as app_settings

# Setup Logger
logger = logging.getLogger("TARS_ARCHIVE")

CACHE_MAX_SIZE = 256
CACHE_TTL_SECONDS = 180.0


class TarsArchive:
    """
    Persistent Vector Knowledge Base using ChromaDB and SentenceTransformers.
    Optimized with lazy initialization, thread safety, O(1) OrderedDict LRU caching,
    and hybrid lexical + dense vector ranking.
    """

    def __init__(self):
        self.db_path = app_settings.CHROMA_PATH
        self.local_model_path = app_settings.BASE_DIR / "models" / "all-MiniLM-L6-v2"
        self.client = None
        self.collection = None
        self.embedding_fn = None
        self._init_lock = threading.Lock()
        self._is_initialized = False
        self._query_cache: "OrderedDict[tuple, Tuple[float, List[dict]]]" = OrderedDict()
        self._cache_lock = threading.Lock()
        logger.info("TARS Archive registered (Lazy Loading Mode with LRU Cache).")

    def _ensure_local_model_links(self):
        """Ensures local offline model can be discovered by HuggingFace / ChromaDB under standard aliases."""
        if not self.local_model_path.exists():
            return
        try:
            import subprocess
            resolved_target = str(self.local_model_path.resolve())
            root_link = app_settings.BASE_DIR / "all-MiniLM-L6-v2"
            if not root_link.exists():
                try:
                    os.symlink(resolved_target, str(root_link), target_is_directory=True)
                except Exception:
                    try:
                        subprocess.run(f'cmd /c mklink /J "{root_link}" "{resolved_target}"', shell=True, capture_output=True)
                    except Exception:
                        pass

            st_dir = app_settings.BASE_DIR / "sentence-transformers"
            st_dir.mkdir(parents=True, exist_ok=True)
            st_link = st_dir / "all-MiniLM-L6-v2"
            if not st_link.exists():
                try:
                    os.symlink(resolved_target, str(st_link), target_is_directory=True)
                except Exception:
                    try:
                        subprocess.run(f'cmd /c mklink /J "{st_link}" "{resolved_target}"', shell=True, capture_output=True)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"Model link initialization notice: {e}")

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

                if self.local_model_path.exists():
                    logger.info(f"OFFLINE MODE: Using local embedding model at {self.local_model_path}")
                    os.environ["TRANSFORMERS_OFFLINE"] = "1"
                    os.environ["HF_HUB_OFFLINE"] = "1"
                    self._ensure_local_model_links()
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
                    device="cpu"
                )

                if hasattr(self.embedding_fn, "_model") and self.embedding_fn._model is not None:
                    cached_m = self.embedding_fn._model
                    embedding_functions.SentenceTransformerEmbeddingFunction.models["all-MiniLM-L6-v2"] = cached_m
                    embedding_functions.SentenceTransformerEmbeddingFunction.models["sentence-transformers/all-MiniLM-L6-v2"] = cached_m
                    embedding_functions.SentenceTransformerEmbeddingFunction.models[model_target] = cached_m
                    embedding_functions.SentenceTransformerEmbeddingFunction.models[str(Path(model_target).resolve())] = cached_m

                self.client = chromadb.PersistentClient(
                    path=str(self.db_path),
                    settings=Settings(anonymized_telemetry=False)
                )

                self.collection = self.client.get_or_create_collection(
                    name="tars_knowledge_base",
                    embedding_function=self.embedding_fn
                )

                if getattr(self.collection, "_embedding_function", None) is None:
                    self.collection._embedding_function = self.embedding_fn

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

    def _get_cached(self, cache_key: tuple, now: float) -> Optional[List[dict]]:
        """O(1) LRU cache read with TTL validation."""
        with self._cache_lock:
            entry = self._query_cache.get(cache_key)
            if entry is None:
                return None
            ts, hits = entry
            if now - ts < CACHE_TTL_SECONDS:
                self._query_cache.move_to_end(cache_key)
                return [dict(h) for h in hits]
            del self._query_cache[cache_key]
            return None

    def _set_cached(self, cache_key: tuple, now: float, output: List[dict]):
        """O(1) LRU cache write that evicts only the oldest entry when full."""
        with self._cache_lock:
            if cache_key in self._query_cache:
                self._query_cache.move_to_end(cache_key)
            self._query_cache[cache_key] = (now, output)
            while len(self._query_cache) > CACHE_MAX_SIZE:
                self._query_cache.popitem(last=False)

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
            chunks = []
            start = 0
            step = max(1, chunk_size - overlap)
            while start < len(text):
                end = min(start + chunk_size, len(text))
                chunks.append(text[start:end])
                start += step
            return chunks

    @staticmethod
    def _compute_lexical_boost(query: str, passage: str) -> float:
        """Computes a lightweight lexical term-overlap bonus to complement dense cosine distance."""
        q_terms = {t for t in re.findall(r"\w{3,}", query.lower())}
        if not q_terms:
            return 0.0
        p_lower = passage.lower()
        matched = sum(1 for t in q_terms if t in p_lower)
        return (matched / len(q_terms)) * 0.20

    def ingest_text(self, text: str, filename: str, book_id: Optional[str] = None, title: Optional[str] = None) -> int:
        """Directly chunks and ingests extracted clean text into ChromaDB with metadata."""
        if not self.ensure_initialized() or not self.collection:
            return 0

        clean = self._clean_text(text)
        if not clean or len(clean) < 20:
            return 0

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

        batch_size = 200
        persisted = 0
        for i in range(0, len(chunks), batch_size):
            b_docs = chunks[i:i + batch_size]
            b_meta = metadatas[i:i + batch_size]
            b_ids = ids[i:i + batch_size]
            try:
                b_embeddings = self.embedding_fn(b_docs) if self.embedding_fn else None
                if b_embeddings is not None:
                    self.collection.add(
                        documents=b_docs,
                        embeddings=b_embeddings,
                        metadatas=b_meta,
                        ids=b_ids
                    )
                else:
                    self.collection.add(
                        documents=b_docs,
                        metadatas=b_meta,
                        ids=b_ids
                    )
                persisted += len(b_docs)
            except Exception as e:
                logger.error(f"Error adding chunk batch to ChromaDB: {e}")

        self._clear_cache()
        logger.info(f"Persisted {persisted} chunks from '{filename}' into vector store.")
        return persisted

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

        batch_size = 200
        persisted = 0
        for i in range(0, len(all_chunks), batch_size):
            b_docs = all_chunks[i:i + batch_size]
            b_meta = all_metas[i:i + batch_size]
            b_ids = all_ids[i:i + batch_size]
            try:
                b_embeddings = self.embedding_fn(b_docs) if self.embedding_fn else None
                if b_embeddings is not None:
                    self.collection.add(
                        documents=b_docs,
                        embeddings=b_embeddings,
                        metadatas=b_meta,
                        ids=b_ids
                    )
                else:
                    self.collection.add(
                        documents=b_docs,
                        metadatas=b_meta,
                        ids=b_ids
                    )
                persisted += len(b_docs)
            except Exception as e:
                logger.error(f"Error adding chunk batch to ChromaDB: {e}")

        self._clear_cache()
        logger.info(f"Persisted {persisted} structured page-aware chunks for '{filename}'.")
        return persisted

    def reindex_document(self, file_path: str, filename: str, book_id: str, title: Optional[str] = None) -> int:
        """Purges any partial/stale vectors for a book and re-runs structured ingestion."""
        self.delete_source(filename, book_id=book_id)
        return self.ingest_document(file_path, filename, book_id=book_id, title=title)

    def ingest_file(self, file_path: str, filename: str, book_id: Optional[str] = None) -> int:
        """Reads a file, chunks it with page metadata, and stores it in ChromaDB."""
        return self.ingest_document(file_path, filename, book_id=book_id)

    def search_with_metadata(
        self,
        query: str,
        top_k: int = 3,
        filter_source: Optional[str] = None,
        book_id: Optional[str] = None,
        fallback_to_library: bool = False,
        max_distance: Optional[float] = 1.25
    ) -> List[dict]:
        """
        Queries ChromaDB vector database with source metadata, page numbers, and hybrid lexical-vector re-ranking.
        Supports filtering strictly by book_id or source filename without leaking cross-book data.
        """
        if not self.ensure_initialized() or not self.collection:
            return []

        cache_key = (
            str(query).strip().lower(),
            top_k,
            str(filter_source or ""),
            str(book_id or ""),
            fallback_to_library,
            max_distance
        )
        now = time.time()
        cached_hits = self._get_cached(cache_key, now)
        if cached_hits is not None:
            return cached_hits

        try:
            if self.collection.count() == 0:
                return []

            results = None
            has_scoped_hits = False
            candidate_k = max(top_k * 2, 6)
            q_emb = self.embedding_fn([query]) if self.embedding_fn else None
            q_kwargs = {"query_embeddings": q_emb} if q_emb is not None else {"query_texts": [query]}

            # Strategy 1: Targeted search by book_id if provided
            if book_id:
                try:
                    res = self.collection.query(
                        n_results=candidate_k,
                        where={"book_id": str(book_id)},
                        **q_kwargs
                    )
                    if res and res.get('documents') and len(res['documents']) > 0 and len(res['documents'][0]) > 0:
                        results = res
                        has_scoped_hits = True
                except Exception as query_err:
                    logger.debug(f"Scoped book_id query error: {query_err}")

            # Strategy 2: Targeted search by source filename / path if provided
            if not has_scoped_hits and filter_source:
                candidate_sources = [str(filter_source)]
                src_name = Path(str(filter_source)).name
                if src_name not in candidate_sources:
                    candidate_sources.append(src_name)

                for cand in candidate_sources:
                    try:
                        res = self.collection.query(
                            n_results=candidate_k,
                            where={"source": cand},
                            **q_kwargs
                        )
                        if res and res.get('documents') and len(res['documents']) > 0 and len(res['documents'][0]) > 0:
                            results = res
                            has_scoped_hits = True
                            break
                    except Exception as query_err:
                        logger.debug(f"Scoped source query error: {query_err}")

            is_scoped = bool(book_id or filter_source)
            if is_scoped and not has_scoped_hits and not fallback_to_library:
                logger.debug(f"Scoped search for book_id={book_id}, source={filter_source} yielded 0 hits. Suppressing fallback.")
                return []

            if not has_scoped_hits:
                results = self.collection.query(
                    n_results=candidate_k,
                    **q_kwargs
                )

            if not results or not results.get('documents') or len(results['documents']) == 0 or len(results['documents'][0]) == 0:
                return []

            candidates = []
            docs = results['documents'][0]
            metas = results['metadatas'][0] if results.get('metadatas') and len(results['metadatas']) > 0 else [{}] * len(docs)
            dists = results['distances'][0] if results.get('distances') and len(results['distances']) > 0 else [0.0] * len(docs)

            for doc, meta, dist in zip(docs, metas, dists):
                raw_dist = float(dist) if dist is not None else 0.0
                lexical_bonus = self._compute_lexical_boost(query, doc)
                effective_dist = max(0.0, raw_dist - lexical_bonus)
                if max_distance is not None and effective_dist > max_distance:
                    continue
                m = meta if isinstance(meta, dict) else {}
                cleaned_doc = doc[:700].strip() if len(doc) > 700 else doc.strip()
                candidates.append({
                    "text": cleaned_doc,
                    "source": m.get('source', 'Library Document'),
                    "book_id": m.get('book_id', ''),
                    "title": m.get('title', m.get('source', 'Document')),
                    "page": m.get('page'),
                    "section_type": m.get('section_type', 'page'),
                    "distance": round(effective_dist, 4)
                })

            candidates.sort(key=lambda item: item["distance"])
            output = candidates[:top_k]
            self._set_cached(cache_key, now, output)
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

    def get_document_coverage_chunks(
        self,
        book_id: Optional[str] = None,
        filter_source: Optional[str] = None,
        max_chunks: int = 10,
        start_page: int = 1
    ) -> List[dict]:
        """
        Retrieves representative chunks distributed chronologically across a document's pages
        to provide comprehensive multi-page coverage for summaries, study guides, and lecture overviews.
        """
        if not self.ensure_initialized() or not self.collection:
            return []

        try:
            res = None
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

            if not res or not res.get('documents') or len(res['documents']) == 0:
                return []

            docs = res['documents']
            metas = res.get('metadatas') or [{}] * len(docs)

            combined = []
            for d, m in zip(docs, metas):
                if not d or not d.strip():
                    continue
                meta_dict = m if isinstance(m, dict) else {}
                try:
                    p = int(meta_dict.get('page') or 1)
                except Exception:
                    p = 1
                try:
                    idx = int(meta_dict.get('chunk_index') or 0)
                except Exception:
                    idx = 0
                combined.append((p, idx, d, meta_dict))

            if not combined:
                return []

            # Sort strictly by page number and chunk position
            combined.sort(key=lambda x: (x[0], x[1]))

            # If user asks to continue from a later page
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
                cleaned = d[:900].strip() if len(d) > 900 else d.strip()
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
            logger.error(f"Coverage Chunks Retrieval Error: {e}")
            return []

    def get_chunks_by_pages(
        self,
        book_id: Optional[str] = None,
        filter_source: Optional[str] = None,
        pages: Optional[List[int]] = None
    ) -> List[dict]:
        """Retrieves exact chunks belonging to specified page numbers for adjacent window expansion."""
        if not self.ensure_initialized() or not self.collection or not pages:
            return []
        try:
            res = None
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
            if not res or not res.get('documents') or len(res['documents']) == 0:
                try:
                    res = self.collection.get()
                except Exception:
                    pass
            if not res or not res.get('documents'):
                return []
            target_pages = set(pages)
            docs = res['documents']
            metas = res.get('metadatas') or [{}] * len(docs)
            out = []
            for d, m in zip(docs, metas):
                m_source = m.get('source', '')
                m_book_id = m.get('book_id', '')
                if filter_source and m_source and m_source != filter_source and m_book_id != str(book_id or ''):
                    continue
                p = int(m.get('page') or 0)
                if p in target_pages:
                    cleaned = d[:900].strip() if len(d) > 900 else d.strip()
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
            logger.error(f"Error in get_chunks_by_pages: {e}")
            return []

    def get_collection_stats(self) -> dict:
        """Returns statistics about ChromaDB knowledge store."""
        if not self.ensure_initialized() or not self.collection:
            return {"total_chunks": 0, "status": "Offline"}
        try:
            cnt = self.collection.count()
            with self._cache_lock:
                cache_entries = len(self._query_cache)
            return {
                "total_chunks": cnt,
                "status": "Online",
                "cache_entries": cache_entries,
                "storage_path": str(self.db_path)
            }
        except Exception as e:
            return {"total_chunks": 0, "status": f"Error: {e}"}

    def _get_raw_collection(self):
        """
        Fast accessor for the ChromaDB collection without loading heavy neural embedding models.
        Ideal for deletions, count checks, and metadata purges (<0.3s).
        """
        if self.collection is not None:
            return self.collection

        with self._init_lock:
            if self.collection is not None:
                return self.collection

            try:
                import chromadb
                from chromadb.config import Settings

                self.db_path.mkdir(parents=True, exist_ok=True)
                if self.client is None:
                    self.client = chromadb.PersistentClient(
                        path=str(self.db_path),
                        settings=Settings(anonymized_telemetry=False)
                    )

                try:
                    return self.client.get_collection(name="tars_knowledge_base")
                except Exception:
                    return self.client.get_or_create_collection(name="tars_knowledge_base")
            except Exception as e:
                logger.error(f"Failed to access raw ChromaDB collection: {e}")
                return None

    def delete_source(self, source_name: str, book_id: Optional[str] = None) -> bool:
        """Deletes all chunks associated with a source filename or book ID with instant cache invalidation."""
        coll = self._get_raw_collection()
        if not coll:
            return False

        try:
            target_id = book_id or source_name
            try:
                coll.delete(where={"book_id": str(target_id)})
            except Exception as e_bid:
                logger.debug(f"Direct book_id deletion notice: {e_bid}")

            if source_name and source_name != target_id:
                try:
                    coll.delete(where={"source": str(source_name)})
                except Exception as e_src:
                    logger.debug(f"Direct source deletion notice: {e_src}")

            self._clear_cache()
            logger.info(f"Purged vector embeddings and invalidated cache for: {source_name} / {book_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete source '{source_name}': {e}")
            return False


# Architectural Aliases & Singleton Instance
RAGPipeline = TarsArchive
tars_archive = TarsArchive()