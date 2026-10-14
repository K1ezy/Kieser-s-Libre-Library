import os
import shutil
import uuid
import time
import logging
import asyncio
import aiofiles
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from nicegui import run
from core.database.mongo_manager import mongo_db
from core.database.models import BookMetadata
from core.ai_engine.rag_pipeline import tars_archive
from core.utils.text_extractor import extract_text_from_file
from core.config import settings

# Setup Logger
logger = logging.getLogger("INGESTION_SERVICE")

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB ceiling


class IngestionService:
    """
    Unified ingestion pipeline for Libre-Library:
    1. Validates extension, file size ceiling, and binary magic-byte signatures
    2. Saves file to data/books/<id>/
    3. Extracts cover image (renders PDF first page via PyMuPDF or uses default cover)
    4. Extracts text and ingests chunks into ChromaDB for TARS RAG
    5. Registers validated BookMetadata in MongoDB with explicit indexing_status tracking
    """

    def __init__(self):
        self.books_dir = settings.BASE_DIR / 'data' / 'books'
        self.books_dir.mkdir(parents=True, exist_ok=True)
        self.allowed_extensions = {'.pdf', '.epub', '.docx', '.pptx', '.txt', '.md'}

    def _sanitize_filename(self, filename: str) -> str:
        clean = str(filename).replace("\\", "/").split("/")[-1]
        clean = "".join(c for c in clean if c.isalnum() or c in "._- ")
        while ".." in clean:
            clean = clean.replace("..", ".")
        return clean.strip() or "unnamed_document.pdf"

    @staticmethod
    def _validate_magic_bytes(ext: str, content: bytes) -> Optional[str]:
        """Verifies binary file header signatures to prevent spoofed file uploads."""
        if len(content) > MAX_UPLOAD_BYTES:
            return f"File exceeds the maximum allowed size of {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        if ext == ".pdf" and not content.startswith(b"%PDF-"):
            return "Invalid PDF file: missing '%PDF-' magic header."
        if ext in {".epub", ".docx", ".pptx"} and not content.startswith(b"PK\x03\x04"):
            return f"Invalid {ext.upper()} archive: missing ZIP/OpenXML header signature."
        return None

    async def process_upload(self, file_obj, filename: str, progress_callback=None) -> dict:
        start_time = datetime.now()
        clean_filename = self._sanitize_filename(filename)
        ext = Path(clean_filename).suffix.lower()

        async def report(step: int, total_steps: int, stage: str, message: str, percent: int, log_type: str = "info"):
            if progress_callback:
                try:
                    res = progress_callback(step, total_steps, stage, message, percent, log_type)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as cb_err:
                    logger.debug(f"Progress callback exception: {cb_err}")

        if ext not in self.allowed_extensions:
            err_msg = f"Format '{ext}' is not supported. Allowed: PDF, EPUB, DOCX, PPTX, TXT, MD."
            await report(0, 6, "Validation", err_msg, 0, "error")
            return {"success": False, "error": err_msg}

        book_id = str(uuid.uuid4())
        book_folder = self.books_dir / book_id

        try:
            await report(1, 6, "Validation", f"Validated format '{ext.upper()}' for '{clean_filename}'", 15, "info")

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
                err_empty = "Uploaded file is empty or could not be read."
                await report(1, 6, "Validation", err_empty, 0, "error")
                return {"success": False, "error": err_empty}

            sig_error = self._validate_magic_bytes(ext, content)
            if sig_error:
                await report(1, 6, "Validation", sig_error, 0, "error")
                return {"success": False, "error": sig_error}

            book_folder.mkdir(parents=True, exist_ok=True)
            file_path = book_folder / clean_filename

            # 2. Asynchronous disk write
            size_mb = len(content) / (1024 * 1024)
            size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{len(content)/1024:.1f} KB"
            await report(2, 6, "Storage Vault", f"Storing '{clean_filename}' ({size_str}) into archive vault...", 30, "info")
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)

            # 3. Extract Embedded Local Metadata & Formats
            from core.utils.metadata_scraper import extract_local_file_metadata
            from core.utils.cover_manager import cover_manager

            await report(3, 6, "Metadata Extraction", "Parsing document structure & extracting embedded metadata...", 45, "info")
            local_meta = await run.io_bound(extract_local_file_metadata, file_path)
            clean_title = local_meta.get('title') or clean_filename.replace(ext, "").replace("_", " ").replace("-", " ").strip().title()
            authors = local_meta.get('authors') or ["Unknown"]
            display_author = authors[0] if authors else "Unknown"
            file_type_str = ext.replace(".", "").upper()
            await report(3, 6, "Metadata Extraction", f"Identified title: '{clean_title}' by {display_author}", 62, "info")

            # 4. Universal Cover Art Extraction & Optimization
            await report(4, 6, "Cover Art Synthesis", f"Extracting & rendering visual cover artwork ({file_type_str})...", 70, "info")
            cover_path = book_folder / "cover.jpg"
            if not cover_path.exists():
                await cover_manager.extract_cover_async(
                    file_path=file_path,
                    output_path=cover_path,
                    title=clean_title,
                    author=display_author,
                    file_type=file_type_str
                )

            cover_url = f"/static_books/{book_id}/cover.jpg" if cover_path.exists() else "/static/default_cover.svg"

            # 5. Extract structured text & ingest with page awareness into ChromaDB
            await report(5, 6, "AI Vector Memory", "Chunking document & vectorizing passages into ChromaDB (TARS RAG)...", 82, "info")
            facts_learned = 0
            indexing_status = "indexed"
            indexing_error = None
            try:
                facts_learned = await run.io_bound(
                    tars_archive.ingest_document,
                    str(file_path),
                    clean_filename,
                    book_id,
                    clean_title
                )
                if facts_learned == 0:
                    indexing_status = "failed"
                    indexing_error = "No extractable text chunks found."
            except Exception as rag_err:
                indexing_status = "failed"
                indexing_error = str(rag_err)
                logger.error(f"RAG indexing warning for '{clean_filename}': {rag_err}", exc_info=True)

            book_model = BookMetadata(
                id=book_id,
                title=clean_title,
                authors=authors,
                display_author=display_author,
                description=local_meta.get('description', ''),
                subjects=local_meta.get('subjects', []),
                added_at=time.time(),
                file_type=file_type_str,
                formats={ext.replace(".", "").lower(): f"/static_books/{book_id}/{clean_filename}"},
                local_path=str(file_path),
                cover_image=cover_url,
                status="Ready",
                indexing_status=indexing_status,
                indexing_error=indexing_error,
                file_size=len(content),
                chunk_count=facts_learned
            )
            metadata = book_model.model_dump()

            # 6. Register in MongoDB
            await report(6, 6, "Catalog Registration", "Cataloging document record in MongoDB & OPDS feeds...", 95, "info")
            await mongo_db.add_book_metadata(metadata)
            logger.info(
                f"Book registered in library: {metadata['title']} by {display_author} "
                f"({facts_learned} chunks, status={indexing_status})"
            )

            elapsed = (datetime.now() - start_time).total_seconds()
            msg = (
                f"Successfully added to library. TARS learned {facts_learned} facts."
                if facts_learned > 0 else
                "Added to catalog (RAG indexing pending/failed; can be re-indexed from Admin Console)."
            )

            await report(6, 6, "Ingestion Complete", f"Ingestion verified in {elapsed:.2f}s! '{clean_title}' is ready.", 100, "info")

            return {
                "success": True,
                "message": msg,
                "book_id": book_id,
                "title": metadata['title'],
                "indexing_status": indexing_status,
                "processing_time": f"{elapsed:.2f}s"
            }

        except Exception as e:
            logger.error(f"Critical Ingestion Error: {e}", exc_info=True)
            await report(0, 6, "Error", f"Critical ingestion failure: {str(e)}", 0, "error")
            if book_folder.exists():
                try:
                    shutil.rmtree(book_folder, ignore_errors=True)
                except Exception:
                    pass
            return {"success": False, "error": str(e)}

    async def reindex_failed_books(self, progress_callback=None) -> Dict[str, Any]:
        """Scans MongoDB for books with chunk_count == 0 or indexing_status == 'failed' and re-runs ChromaDB ingestion."""
        all_books = await mongo_db.get_all_books()
        target_books = [
            b for b in all_books
            if b.get("chunk_count", 0) == 0 or b.get("indexing_status") == "failed"
        ]
        total = len(target_books)
        reindexed = 0
        failed = 0
        for i, b in enumerate(target_books, 1):
            local_path = b.get("local_path")
            book_id = b.get("id")
            title = b.get("title", "Untitled")
            if progress_callback:
                try:
                    res = progress_callback(i, total, title, "indexing")
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    pass
            if local_path and Path(local_path).exists():
                try:
                    chunks = await run.io_bound(
                        tars_archive.reindex_document,
                        str(local_path),
                        Path(local_path).name,
                        str(book_id),
                        str(title)
                    )
                    if chunks > 0:
                        update_data = {
                            "chunk_count": chunks,
                            "indexing_status": "indexed",
                            "indexing_error": None
                        }
                        if hasattr(mongo_db.books, "update_book"):
                            await mongo_db.books.update_book(book_id, update_data)
                        elif hasattr(mongo_db.books, "update_book_metadata"):
                            await mongo_db.books.update_book_metadata(book_id, update_data)
                        reindexed += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.error(f"Failed to re-index book {book_id}: {e}")
                    failed += 1
            else:
                failed += 1
        return {"reindexed": reindexed, "failed": failed, "total": total}



# Singleton Instance
ingestion_service = IngestionService()