import unittest
from unittest.mock import MagicMock, patch
from core.ai_engine.rag_pipeline import RAGPipeline

class TestRAGPipeline(unittest.TestCase):
    """Verifies RAG text cleaning, chunking, and scoped query fallback prevention."""

    def setUp(self):
        self.rag = RAGPipeline()
        self.rag._is_initialized = True
        self.rag.collection = MagicMock()

    def test_clean_text_strips_null_bytes(self):
        """Null bytes and malformed encoding should be cleanly stripped."""
        dirty = "Hello\x00World! This is a test \x00 string."
        clean = self.rag._clean_text(dirty)
        self.assertNotIn("\x00", clean)
        self.assertEqual(clean, "HelloWorld! This is a test  string.")

    def test_smart_chunker_basic(self):
        """Smart chunker should divide text into chunks according to max chunk size."""
        sample_text = "Paragraph one with several words. " * 30
        chunks = self.rag._smart_chunker(sample_text, chunk_size=200, overlap=50)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 300)

    def test_search_with_metadata_suppresses_fallback_when_scoped(self):
        """When book_id is supplied and returns 0 hits, general fallback MUST NOT be executed."""
        self.rag.collection.count.return_value = 50
        # Mock empty return for the scoped query
        self.rag.collection.query.return_value = {
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]]
        }

        results = self.rag.search_with_metadata(
            query="quantum mechanics",
            book_id="specific_book_123",
            fallback_to_library=False
        )

        self.assertEqual(results, [])
        # Only the scoped query should have been run with where clause
        self.rag.collection.query.assert_called_once()
        call_kwargs = self.rag.collection.query.call_args.kwargs
        self.assertEqual(call_kwargs.get("where"), {"book_id": "specific_book_123"})

    def test_search_with_metadata_filters_high_distance(self):
        """Results with distance > max_distance should be filtered out."""
        self.rag.collection.count.return_value = 10
        self.rag.collection.query.return_value = {
            "documents": [["Relevant chunk", "Completely irrelevant chunk"]],
            "metadatas": [[
                {"source": "doc1.pdf", "title": "Doc 1", "page": 1, "book_id": "b1"},
                {"source": "doc2.pdf", "title": "Doc 2", "page": 12, "book_id": "b2"}
            ]],
            "distances": [[0.45, 1.85]]
        }

        results = self.rag.search_with_metadata(
            query="machine learning",
            max_distance=1.35
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["text"], "Relevant chunk")
        self.assertAlmostEqual(results[0]["distance"], 0.45)

    def test_search_query_caching(self):
        """Repeated identical queries should hit the in-memory cache without repeating Chroma query."""
        self.rag.collection.count.return_value = 10
        self.rag.collection.query.return_value = {
            "documents": [["Cached content"]],
            "metadatas": [[{"source": "test.pdf", "title": "Test"}]],
            "distances": [[0.3]]
        }

        # First query populates cache
        res1 = self.rag.search_with_metadata("neural networks")
        self.assertEqual(self.rag.collection.query.call_count, 1)

        # Second query hits cache
        res2 = self.rag.search_with_metadata("neural networks")
        self.assertEqual(self.rag.collection.query.call_count, 1)  # No second call to query
        self.assertEqual(res1, res2)

if __name__ == "__main__":
    unittest.main()
