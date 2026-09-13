import logging
import uuid
import os
import time
import threading
from pathlib import Path
from typing import List, Optional
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

    def ingest_text(self, text: str, filename: str) -> int:
        """Directly chunks and ingests extracted clean text into ChromaDB."""
        if not self.ensure_initialized() or not self.collection:
            return 0

        clean = self._clean_text(text)
        if not clean or len(clean) < 20:
            return 0

        # Check if already indexed
        try:
            existing = self.collection.get(where={"source": filename})
            if existing and len(existing['ids']) > 0:
                logger.info(f"Document '{filename}' already in memory ({len(existing['ids'])} chunks).")
                return len(existing['ids'])
        except Exception:
            pass

        chunks = self._smart_chunker(clean)
        if not chunks:
            return 0

        ids = [f"{filename}_{i}_{str(uuid.uuid4())[:8]}" for i in range(len(chunks))]
        metadatas = [{"source": str(filename)} for _ in chunks]

        # Batch insert into ChromaDB (max 250 chunks per batch to prevent memory spikes)
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

        logger.info(f"Persisted {len(chunks)} chunks from '{filename}' into vector store.")
        return len(chunks)

    def ingest_file(self, file_path: str, filename: str) -> int:
        """Reads a file, chunks it, and stores it in ChromaDB."""
        if not self.ensure_initialized() or not self.collection:
            return 0

        file_p = Path(file_path)
        if not file_p.exists() or file_p.stat().st_size == 0:
            logger.warning(f"Skipping '{filename}': File not found or empty.")
            return 0

        ext = file_p.suffix.lower()
        text = ""

        try:
            if ext == ".pdf":
                from pypdf import PdfReader
                reader = PdfReader(str(file_p))
                for i, page in enumerate(reader.pages):
                    extracted = page.extract_text()
                    if extracted:
                        text += f"[Page {i+1}] {extracted}\n"

            elif ext == ".docx":
                import docx
                doc = docx.Document(str(file_p))
                text += f"[Document: {filename}]\n"
                for para in doc.paragraphs:
                    if para.text.strip():
                        text += para.text + "\n"
                for table in doc.tables:
                    for row in table.rows:
                        text += " | ".join([cell.text.strip() for cell in row.cells]) + "\n"

            elif ext == ".pptx":
                from pptx import Presentation
                prs = Presentation(str(file_p))
                text += f"[Presentation: {filename}]\n"
                for i, slide in enumerate(prs.slides):
                    text += f"\n--- Slide {i+1} ---\n"
                    for shape in slide.shapes:
                        if hasattr(shape, "text") and shape.text.strip():
                            text += shape.text.strip() + "\n"

            elif ext == ".epub":
                try:
                    import ebooklib
                    from ebooklib import epub
                    from bs4 import BeautifulSoup
                    book = epub.read_epub(str(file_p))
                    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                        soup = BeautifulSoup(item.get_content(), 'html.parser')
                        t = soup.get_text()
                        if t.strip():
                            text += t.strip() + "\n"
                except Exception:
                    pass

            else:
                with open(file_p, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()

        except Exception as e:
            logger.error(f"Failed to read file '{filename}': {e}")
            return 0

        return self.ingest_text(text, filename)

    def search(self, query: str, top_k: int = 3) -> List[str]:
        """Queries the long-term memory."""
        if not self.ensure_initialized() or not self.collection:
            return []

        try:
            if self.collection.count() == 0:
                return []

            results = self.collection.query(
                query_texts=[query],
                n_results=top_k
            )

            if results and results.get('documents') and len(results['documents']) > 0:
                return results['documents'][0]

            return []
        except Exception as e:
            logger.error(f"Search Query Failed: {e}")
            return []

    def delete_source(self, source_name: str) -> bool:
        """Deletes all chunks associated with a source filename or ID."""
        if not self.ensure_initialized() or not self.collection:
            return False

        try:
            existing = self.collection.get(where={"source": source_name})
            if existing and existing.get('ids'):
                self.collection.delete(ids=existing['ids'])
                logger.info(f"Purged {len(existing['ids'])} chunks for source: {source_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete source '{source_name}': {e}")
            return False

# Singleton Instance
tars_archive = TarsArchive()