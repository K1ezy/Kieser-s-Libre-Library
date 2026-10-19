import unittest
from unittest.mock import MagicMock, patch
import os
import tempfile
from pathlib import Path

from core.ai_engine.text_extractor import (
    extract_document_structure,
    _run_page_ocr,
)
from core.ai_engine.rag_pipeline import (
    CHROMA_LOCK,
    ResilientRAGPipeline,
    resolve_missing_book_path,
    build_catalog_fallback_chunks,
    chunk_pages_with_headers,
)


class TestResilientRAGPipeline(unittest.TestCase):
    """Verifies all 4 batch-indexing architectural fixes."""

    # 1. Test Smart OCR Circuit Breaker & Blank Page Skip
    def test_smart_ocr_blank_page_skip(self):
        """Pages with <20 chars and no images should never call OCR."""
        mock_page = MagicMock()
        mock_page.get_text.return_value = ""  # blank page
        mock_page.get_images.return_value = []  # no images!

        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page
        mock_doc.__enter__.return_value = mock_doc
        mock_doc.__exit__.return_value = False

        with patch("fitz.open", return_value=mock_doc), \
             patch("core.ai_engine.text_extractor._run_page_ocr") as mock_ocr:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                temp_pdf = f.name
            try:
                pages = extract_document_structure(temp_pdf, enable_ocr=True)
                mock_ocr.assert_not_called()
                self.assertEqual(len(pages), 0)
            finally:
                Path(temp_pdf).unlink(missing_ok=True)

    def test_ocr_low_density_circuit_breaker(self):
        """After 5 OCR pages with average yield < 25 words/page, circuit breaker trips."""
        mock_pages = []
        for i in range(10):
            p = MagicMock()
            p.get_text.return_value = ""  # low text
            p.get_images.return_value = ["img_ref"]  # has image
            mock_pages.append(p)

        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 10
        mock_doc.__getitem__.side_effect = lambda idx: mock_pages[idx]
        mock_doc.__enter__.return_value = mock_doc
        mock_doc.__exit__.return_value = False

        # Mock OCR returning only 5 words per page (under 25 threshold)
        with patch("fitz.open", return_value=mock_doc), \
             patch("core.ai_engine.text_extractor._run_page_ocr", return_value="five words here on page"):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                temp_pdf = f.name
            try:
                pages = extract_document_structure(temp_pdf, enable_ocr=True, max_ocr_pages=15)
                # Should have run exactly 5 times and then tripped the circuit breaker
                self.assertEqual(len(pages), 5)
            finally:
                Path(temp_pdf).unlink(missing_ok=True)

    def test_progress_callback_invocations(self):
        """Progress callback should be invoked periodically on digital pages and on every OCR page."""
        mock_pages = []
        for i in range(25):
            p = MagicMock()
            p.get_text.return_value = f"This is digital text for page number {i+1} with sufficient length."
            p.get_images.return_value = []
            mock_pages.append(p)

        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 25
        mock_doc.__getitem__.side_effect = lambda idx: mock_pages[idx]
        mock_doc.__enter__.return_value = mock_doc
        mock_doc.__exit__.return_value = False

        callback_calls = []

        def cb(cur, tot, msg):
            callback_calls.append((cur, tot, msg))

        with patch("fitz.open", return_value=mock_doc):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                temp_pdf = f.name
            try:
                pages = extract_document_structure(temp_pdf, progress_callback=cb)
                self.assertEqual(len(pages), 25)
                # Pages 1, 10, 20, 25 should have triggered callbacks
                called_pages = [c[0] for c in callback_calls]
                self.assertIn(1, called_pages)
                self.assertIn(10, called_pages)
                self.assertIn(20, called_pages)
                self.assertIn(25, called_pages)
            finally:
                Path(temp_pdf).unlink(missing_ok=True)

    # 2. Test Catalog Metadata Fallback for Missing Files (e.g. Chronicles of Narnia)
    def test_catalog_fallback_chunks_synthesis(self):
        """When local_path is None, synthesizes rich metadata fallback chunk."""
        book_doc = {
            "title": "The Chronicles of Narnia",
            "author": "C.S. Lewis",
            "category": "Fantasy",
            "isbn": "978-0066238500",
            "publisher": "HarperCollins",
            "publication_year": 1950,
            "description": "Journeys to the end of the world, fantastic creatures, and great battles.",
            "call_number": "STACK-042",
        }
        chunks = build_catalog_fallback_chunks(book_doc)
        self.assertEqual(len(chunks), 1)
        text = chunks[0]["text"]
        self.assertIn("The Chronicles of Narnia", text)
        self.assertIn("C.S. Lewis", text)
        self.assertIn("Fantasy", text)
        self.assertIn("978-0066238500", text)
        self.assertIn("Catalog Synopsis & Overview", text)
        self.assertEqual(chunks[0]["source"], "catalog_metadata_fallback")

    # 3. Test Deferred BM25 Rebuild in Batch Operations
    def test_deferred_bm25_in_reindex_failed_books(self):
        """reindex_failed_books should rebuild BM25 only ONCE at the end."""
        pipeline = ResilientRAGPipeline(enable_hybrid_bm25=True)
        pipeline.collection = MagicMock()
        pipeline.refresh_bm25_index = MagicMock()

        unindexed = [
            {"_id": "b1", "title": "Book 1", "author": "Author 1", "local_path": None},
            {"_id": "b2", "title": "Book 2", "author": "Author 2", "local_path": None},
            {"_id": "b3", "title": "Book 3", "author": "Author 3", "local_path": None},
        ]

        with patch.object(pipeline.embedder, "encode", return_value=MagicMock(tolist=lambda: [[0.1] * 384])):
            summary = pipeline.reindex_failed_books(unindexed)

        self.assertEqual(summary["total_processed"], 3)
        self.assertEqual(summary["indexed_fallback"], 3)
        self.assertEqual(summary["failed"], 0)
        # BM25 index refresh should be called exactly ONCE in finally: block
        pipeline.refresh_bm25_index.assert_called_once()

    # 4. Test ChromaDB RLock Protection
    def test_chroma_rlock_protection(self):
        """Verify that CHROMA_LOCK is an RLock and can be acquired re-entrantly."""
        with CHROMA_LOCK:
            with CHROMA_LOCK:
                # Re-entrant acquisition succeeds without deadlock
                acquired = True
        self.assertTrue(acquired)


if __name__ == "__main__":
    unittest.main()
