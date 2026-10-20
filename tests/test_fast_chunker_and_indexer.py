import os
import tempfile
import time
import unittest

from app_startup import init_app_startup, shutdown_app
from core.ai_engine.fast_chunker import (
    compute_fast_file_signature,
    fast_chunk_book,
    fast_extract_document_pages,
)
from core.services.background_indexer import BackgroundRAGIndexer, get_background_indexer


class MockRAGPipeline:
    def __init__(self):
        self.collection = self
        self.upsert_calls = []

    def upsert(self, ids, documents, embeddings, metadatas):
        self.upsert_calls.append({"ids": ids, "documents": documents})

    def refresh_bm25_index(self):
        pass


class TestFastChunkerAndIndexer(unittest.IsolatedAsyncioTestCase):
    """
    Unit and integration tests for high-speed RAG chunking, file fingerprinting,
    non-blocking startup initialization, and background indexer lifecycle.
    """

    def test_compute_fast_file_signature(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"Hello Libre-Library test file content" * 100)
            tmp_path = f.name

        try:
            sig1 = compute_fast_file_signature(tmp_path)
            sig2 = compute_fast_file_signature(tmp_path)
            self.assertEqual(sig1, sig2)
            self.assertEqual(len(sig1), 24)

            # Missing file returns safe fallback
            self.assertEqual(compute_fast_file_signature("non_existent_file.pdf"), "missing_file")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_fast_chunk_book_catalog_fallback(self):
        """Verifies instant < 5ms synthesis of catalog metadata chunk when document file is missing."""
        t0 = time.time()
        book_doc = {
            "title": "Quantum Computing Principles",
            "author": "Dr. Richard Feynman",
            "category": "Physics",
            "isbn": "978-0123456789",
            "synopsis": "Fundamental textbook exploring quantum state superposition and entanglement.",
        }
        chunks = fast_chunk_book(book_doc, file_path="missing_file.pdf")
        elapsed = time.time() - t0

        self.assertLess(elapsed, 0.05)  # Under 50ms
        self.assertEqual(len(chunks), 1)
        chunk = chunks[0]
        self.assertEqual(chunk["source"], "catalog_metadata_fallback")
        self.assertIn("[Book: Quantum Computing Principles | Author: Dr. Richard Feynman", chunk["text"])
        self.assertIn("Overview: Fundamental textbook", chunk["text"])

    def test_background_indexer_lifecycle_and_telemetry(self):
        """Verifies non-blocking start, telemetry reads, and graceful stop."""
        class MockBooksCollection:
            def find(self, *args, **kwargs):
                time.sleep(0.08)
                return []

        mock_rag = MockRAGPipeline()
        mock_col = MockBooksCollection()
        indexer = BackgroundRAGIndexer(mock_rag, books_collection=mock_col)

        telemetry = indexer.get_telemetry()
        self.assertFalse(telemetry["is_running"])
        self.assertEqual(telemetry["progress_ratio"], 0.0)

        # Non-blocking start returns immediately
        started = indexer.start_non_blocking()
        self.assertTrue(started)
        self.assertTrue(indexer.is_running)

        indexer.request_stop()
        self.assertTrue(indexer.stop_requested)

        # Wait for worker thread to gracefully finish
        if indexer._worker_thread:
            indexer._worker_thread.join(timeout=1.0)
        self.assertFalse(indexer.is_running)

    async def test_instant_app_startup_under_one_second(self):
        """Verifies app_startup boots database and registers background tasks in < 1.0 second."""
        elapsed = await init_app_startup()
        self.assertLess(elapsed, 1.0, f"Startup took {elapsed:.3f}s, exceeding 1.0s limit!")
        await shutdown_app()


if __name__ == "__main__":
    unittest.main()
