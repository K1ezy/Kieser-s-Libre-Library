import os
import shutil
import uuid
import time
import logging
import asyncio
import aiofiles
from pathlib import Path
from datetime import datetime
from nicegui import run
from core.database.mongo_manager import mongo_db
from core.ai_engine.rag_pipeline import tars_archive
from core.utils.text_extractor import extract_text_from_file
from core.config import settings

# Setup Logger
logger = logging.getLogger("INGESTION_SERVICE")

class IngestionService:
    """
    Unified ingestion pipeline for Libre-Library:
    1. Validates and saves file to data/books/<id>/
    2. Extracts cover image (renders PDF first page via PyMuPDF or uses default cover)
    3. Registers metadata in MongoDB
    4. Extracts text and ingests chunks into ChromaDB for TARS RAG
    """
    
    def __init__(self):
        self.books_dir = settings.BASE_DIR / 'data' / 'books'
        self.books_dir.mkdir(parents=True, exist_ok=True)
        self.allowed_extensions = {'.pdf', '.epub', '.docx', '.pptx', '.txt', '.md'}

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitizes filename for cross-platform filesystem safety."""
        safe_name = "".join([c for c in filename if c.isalnum() or c in "._- "])
        return safe_name.strip().replace(" ", "_")

    async def process_upload(self, file_obj, filename: str) -> dict:
        start_time = datetime.now()
        clean_filename = self._sanitize_filename(filename)
        ext = Path(clean_filename).suffix.lower()

        if ext not in self.allowed_extensions:
            return {"success": False, "error": f"Format '{ext}' is not supported. Allowed: PDF, EPUB, DOCX, PPTX, TXT, MD."}

        book_id = str(uuid.uuid4())
        book_folder = self.books_dir / book_id

        try:
            book_folder.mkdir(parents=True, exist_ok=True)
            file_path = book_folder / clean_filename

            # 1. Safely resolve raw bytes from any file adapter or coroutine
            content = b""
            if isinstance(file_obj, bytes):
                content = file_obj
            elif hasattr(file_obj, 'read'):
                res = file_obj.read()
                content = await res if asyncio.iscoroutine(res) else res
            elif hasattr(file_obj, 'file'):
                f = file_obj.file
                if hasattr(f, 'read'):
                    res = f.read()
                    content = await res if asyncio.iscoroutine(res) else res
            elif hasattr(file_obj, 'content'):
                c = file_obj.content
                if hasattr(c, 'read'):
                    res = c.read()
                    content = await res if asyncio.iscoroutine(res) else res
                elif isinstance(c, bytes):
                    content = c

            if not content or len(content) == 0:
                return {"success": False, "error": "Uploaded file is empty or could not be read."}

            # 2. Asynchronous disk write
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)

            # 3. Automatic Cover Extraction
            cover_path = book_folder / "cover.jpg"
            if ext == '.pdf':
                try:
                    import fitz
                    doc = fitz.open(str(file_path))
                    if len(doc) > 0:
                        page = doc[0]
                        pix = page.get_pixmap(dpi=150)
                        pix.save(str(cover_path))
                    doc.close()
                except Exception as cover_err:
                    logger.warning(f"PDF cover extraction notice: {cover_err}")

            cover_url = f"/static_books/{book_id}/cover.jpg" if cover_path.exists() else "/static/default_cover.svg"

            # 4. Extract text for AI knowledge base
            extracted_text = await run.io_bound(extract_text_from_file, str(file_path))
            
            # Ingest into vector store
            facts_learned = 0
            if extracted_text and len(extracted_text) > 20:
                facts_learned = await run.io_bound(tars_archive.ingest_text, extracted_text, clean_filename)

            # 5. Formats dictionary & display metadata
            clean_title = clean_filename.replace(ext, "").replace("_", " ").replace("-", " ").strip().title()

            metadata = {
                "id": book_id,
                "title": clean_title,
                "authors": ["Unknown"],
                "display_author": "Unknown",
                "added_at": time.time(),
                "file_type": ext.replace(".", "").upper(),
                "formats": {ext.replace(".", "").lower(): f"/static_books/{book_id}/{clean_filename}"},
                "local_path": str(file_path),
                "cover_image": cover_url,
                "status": "Ready",
                "file_size": len(content),
                "chunk_count": facts_learned
            }

            # Register in MongoDB
            await mongo_db.add_book_metadata(metadata)
            logger.info(f"Book registered in library: {metadata['title']} ({facts_learned} chunks indexed)")

            elapsed = (datetime.now() - start_time).total_seconds()
            msg = f"Successfully added to library. TARS learned {facts_learned} facts." if facts_learned > 0 else "Successfully added to library."

            return {
                "success": True,
                "message": msg,
                "book_id": book_id,
                "title": metadata['title'],
                "processing_time": f"{elapsed:.2f}s"
            }

        except Exception as e:
            logger.error(f"Critical Ingestion Error: {e}", exc_info=True)
            if book_folder.exists():
                try: shutil.rmtree(book_folder, ignore_errors=True)
                except Exception: pass
            return {"success": False, "error": str(e)}

# Singleton Instance
ingestion_service = IngestionService()