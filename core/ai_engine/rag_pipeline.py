import logging
import uuid
import os
import re
import time
import threading
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import chromadb

from core.config import EMBEDDING_MODEL_PATH, RAG_MAX_DISTANCE, settings as app_settings

logger = logging.getLogger("TARS_ARCHIVE")

CACHE_MAX_SIZE = 256
CACHE_TTL_SECONDS = 180.0


class TarsArchive:
    """Persistent ChromaDB RAG Engine with strict L2 distance gating."""

    def __init__(self, persist_dir: str = "data/chroma_db"):
        self.persist_dir = str(persist_dir)
        try:
            self.client = chromadb.PersistentClient(path=self.persist_dir)
            self.collection = self.client.get_or_create_collection(
                name="tars_knowledge_base",
                metadata={"hnsw:space": "l2"},
            )
        except Exception as exc:
            logger.warning("ChromaDB persistent client init notice: %s", exc)
            self.client = None
            self.collection = None

        self._embedder = None
        self._query_cache: "OrderedDict[tuple, Tuple[float, List[dict]]]" = OrderedDict()
        self._cache_lock = threading.Lock()
        self._is_initialized = True

    @property
    def embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(EMBEDDING_MODEL_PATH)
        return self._embedder

    @lru_cache(maxsize=128)
    def _encode_query(self, query_text: str) -> tuple:
        vec = self.embedder.encode(query_text, normalize_embeddings=True)
        return tuple(vec.tolist())

    def get_known_sources(self) -> set:
        """Returns cached distinct source identifiers present in ChromaDB."""
        now = time.time()
        if hasattr(self, "_known_sources_cache") and (now - getattr(self, "_known_sources_ts", 0) < 60.0):
            return self._known_sources_cache
        try:
            if self.collection is not None:
                data = self.collection.get(include=["metadatas"])
                self._known_sources_cache = set(m.get("source") for m in data.get("metadatas", []) if m and m.get("source"))
                self._known_sources_ts = now
                return self._known_sources_cache
        except Exception as err:
            logger.debug("Notice getting known sources: %s", err)
        return set()

    def resolve_source_name(self, candidates: List[str]) -> Optional[str]:
        """Resolves the exact matching ChromaDB source name from candidate filenames/titles."""
        known = self.get_known_sources()
        if not known:
            return candidates[0] if candidates else None

        # 1. Exact match
        for c in candidates:
            if c in known:
                return c

        # 2. Case-insensitive match
        known_lower_map = {k.lower(): k for k in known}
        for c in candidates:
            if c.lower() in known_lower_map:
                return known_lower_map[c.lower()]

        # 3. Stem / filename match without extension
        known_stem_map = {Path(k).stem.lower(): k for k in known}
        for c in candidates:
            stem = Path(c).stem.lower()
            if stem in known_stem_map:
                return known_stem_map[stem]

        # 4. Partial substring match for messy renames
        for c in candidates:
            c_clean = c.lower().replace("_", " ").replace("-", " ")
            if len(c_clean) >= 6:
                for k, orig in known_lower_map.items():
                    k_clean = k.replace("_", " ").replace("-", " ")
                    if c_clean in k_clean or k_clean in c_clean:
                        return orig

        return None

    def _build_where_filter(
        self,
        filter_source: Optional[str] = None,
        book_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if book_id and filter_source:
            return {"$and": [{"book_id": str(book_id)}, {"source": str(filter_source)}]}
        if book_id:
            return {"book_id": str(book_id)}
        if filter_source:
            return {"source": str(filter_source)}
        return None

    def _clear_cache(self):
        """Clears cached semantic query results upon data mutation."""
        with self._cache_lock:
            self._query_cache.clear()

    def _get_cached(self, cache_key: tuple, now: float) -> Optional[List[dict]]:
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
        with self._cache_lock:
            if cache_key in self._query_cache:
                self._query_cache.move_to_end(cache_key)
            self._query_cache[cache_key] = (now, output)
            while len(self._query_cache) > CACHE_MAX_SIZE:
                self._query_cache.popitem(last=False)

    def search_with_metadata(
        self,
        query: str,
        top_k: int = 3,
        filter_source: Optional[str] = None,
        book_id: Optional[str] = None,
        candidate_sources: Optional[List[str]] = None,
        candidate_book_ids: Optional[List[str]] = None,
        fallback_to_library: bool = False,
        max_distance: Optional[float] = RAG_MAX_DISTANCE,
    ) -> List[dict]:
        """
        Queries ChromaDB with metadata scoping, dynamic alias resolution, and strict distance filtering.
        Returns [] if no chunks meet max_distance.
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

        if not is_scoped:
            try:
                results = self.collection.query(
                    query_embeddings=query_embedding,
                    n_results=max(top_k, 1),
                    include=["documents", "metadatas", "distances"],
                )
                matched_chunks = self._filter_results(results, effective_threshold)
            except Exception as exc:
                logger.error("Unscoped ChromaDB query failed: %s", exc)
        else:
            # 1. Try Candidate Book IDs first
            for bid in all_book_ids:
                try:
                    res = self.collection.query(
                        query_embeddings=query_embedding,
                        n_results=max(top_k, 1),
                        where={"book_id": str(bid)},
                        include=["documents", "metadatas", "distances"],
                    )
                    hits = self._filter_results(res, effective_threshold)
                    if hits:
                        matched_chunks.extend(hits)
                        break
                except Exception as e:
                    logger.debug("Query by book_id %s notice: %s", bid, e)

            # 2. Try Candidate Sources / Filename Aliases
            if not matched_chunks:
                resolved_source = self.resolve_source_name(all_sources)
                query_sources = [resolved_source] if resolved_source else all_sources

                for src in query_sources:
                    if not src:
                        continue
                    try:
                        src_results = self.collection.query(
                            query_embeddings=query_embedding,
                            n_results=max(top_k, 1),
                            where={"source": str(src)},
                            include=["documents", "metadatas", "distances"],
                        )
                        hits = self._filter_results(src_results, effective_threshold)
                        if hits:
                            matched_chunks.extend(hits)
                            break
                    except Exception as exc:
                        logger.debug("Source query failed for %s: %s", src, exc)

            # 3. Optional fallback to entire library only if scoped search yielded nothing
            # AND fallback is explicitly enabled — still strictly gated by effective_threshold
            if not matched_chunks and fallback_to_library:
                try:
                    fallback_results = self.collection.query(
                        query_embeddings=query_embedding,
                        n_results=max(top_k, 1),
                        include=["documents", "metadatas", "distances"],
                    )
                    matched_chunks = self._filter_results(fallback_results, effective_threshold)
                except Exception as exc:
                    logger.error("Fallback ChromaDB query failed: %s", exc)

        self._set_cached(cache_key, now, matched_chunks)
        return matched_chunks

    def get_book_intro_chunks(
        self,
        book_id: Optional[str] = None,
        candidate_sources: Optional[List[str]] = None,
        limit: int = 5,
    ) -> List[dict]:
        """
        Retrieves the earliest introductory/chapter chunks for a book
        to guarantee grounded context for broad summary and outline requests.
        """
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
            res = self.collection.get(where=where_clause, limit=max(limit * 6, 40))
            docs = res.get("documents", [])
            metas = res.get("metadatas", [])
            if not docs and book_id and candidate_sources:
                resolved = self.resolve_source_name(candidate_sources)
                if resolved:
                    res = self.collection.get(where={"source": resolved}, limit=max(limit * 6, 40))
                    docs = res.get("documents", [])
                    metas = res.get("metadatas", [])

            chunks = []
            for d, m in zip(docs, metas):
                text_clean = (d or "").strip()
                # Skip tiny boilerplate or copyright lines
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
        """Dynamically updates display title across all ChromaDB chunks for a book."""
        if self.collection is None or not book_id:
            return 0
        try:
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
        """Fetches neighboring chunks on the same/adjacent page for continuity."""
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

    def ensure_initialized(self) -> bool:
        """Compatibility initializer for application lifecycle startup."""
        return self.collection is not None

    def _clean_text(self, text: str) -> str:
        """Sanitizes text to remove Null bytes and encoding errors."""
        if not text:
            return ""
        text = text.replace('\x00', '')
        return text.encode('utf-8', 'ignore').decode('utf-8').strip()

    def _smart_chunker(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """Splits text into chunks preserving paragraph and sentence boundaries."""
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

        batch_size = 200
        persisted = 0
        for i in range(0, len(chunks), batch_size):
            b_docs = chunks[i:i + batch_size]
            b_meta = metadatas[i:i + batch_size]
            b_ids = ids[i:i + batch_size]
            try:
                embeddings = self.embedder.encode(b_docs, normalize_embeddings=True).tolist()
                self.collection.add(documents=b_docs, embeddings=embeddings, metadatas=b_meta, ids=b_ids)
                persisted += len(b_docs)
            except Exception as e:
                logger.error("Error adding chunk batch to ChromaDB: %s", e)

        self._clear_cache()
        return persisted

    def ingest_document(
        self,
        file_path: str,
        filename: str,
        book_id: Optional[str] = None,
        title: Optional[str] = None,
        force_reindex: bool = False
    ) -> int:
        if self.collection is None:
            return 0

        file_p = Path(file_path)
        if not file_p.exists() or file_p.stat().st_size == 0:
            return 0

        try:
            where_check = {"book_id": book_id} if book_id else {"source": filename}
            existing = self.collection.get(where=where_check)
            if existing and len(existing.get('ids', [])) > 0:
                if not force_reindex:
                    return len(existing['ids'])
                self.collection.delete(ids=existing['ids'])
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

            sec_chunks = [sec_text] if len(sec_text) <= 1500 else self._smart_chunker(sec_text, chunk_size=1200, overlap=200)
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
                embeddings = self.embedder.encode(b_docs, normalize_embeddings=True).tolist()
                self.collection.add(documents=b_docs, embeddings=embeddings, metadatas=b_meta, ids=b_ids)
                persisted += len(b_docs)
            except Exception as e:
                logger.error("Error adding chunk batch to ChromaDB: %s", e)

        self._clear_cache()
        return persisted

    def reindex_document(self, file_path: str, filename: str, book_id: str, title: Optional[str] = None) -> int:
        self.delete_source(filename, book_id=book_id)
        return self.ingest_document(file_path, filename, book_id=book_id, title=title)

    def delete_source(self, source_name: str, book_id: Optional[str] = None) -> bool:
        if self.collection is None:
            return False
        try:
            target_id = book_id or source_name
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
            return True
        except Exception as e:
            logger.error("Failed to delete source '%s': %s", source_name, e)
            return False

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
            cnt = self.collection.count()
            return {
                "total_chunks": cnt,
                "status": "Online",
                "storage_path": self.persist_dir
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


RAGPipeline = TarsArchive
tars_archive = TarsArchive()