import unittest
from unittest.mock import MagicMock, patch
from core.ai_engine.rag_pipeline import (
    TarsArchive,
    EnhancedRAGPipeline,
    build_contextual_chunk,
    tokenize_for_bm25,
)
from core.config import BGE_QUERY_PREFIX


class TestEnhancedRAG(unittest.TestCase):
    """Verifies all components of the Enhanced Hybrid + Reranked RAG Pipeline."""

    def setUp(self):
        self.rag = TarsArchive()
        self.rag._is_initialized = True
        self.rag.collection = MagicMock()

    # 1. Contextual Chunk Header Tests
    def test_build_contextual_chunk_formatting(self):
        raw = "Winston Smith walked down the hall with his diary."
        chunk = build_contextual_chunk(
            raw_text=raw,
            book_title="1984",
            author="George Orwell",
            category="Dystopian Fiction",
            page_number=42,
            section="Chapter 1",
        )
        expected_header = "[Book: 1984 | Author: George Orwell | Subject: Dystopian Fiction | Section: Chapter 1 | Page: 42]"
        self.assertTrue(chunk.startswith(expected_header))
        self.assertIn(raw, chunk)

    def test_build_contextual_chunk_handles_missing_fields(self):
        raw = "Simple text passage."
        chunk = build_contextual_chunk(
            raw_text=raw,
            book_title="Clean Code",
        )
        self.assertEqual(chunk, "[Book: Clean Code]\nSimple text passage.")

    def test_build_contextual_chunk_empty_input(self):
        self.assertEqual(build_contextual_chunk("", "Title"), "")
        self.assertEqual(build_contextual_chunk("   ", "Title"), "")

    # 2. BM25 Tokenizer Tests
    def test_tokenize_for_bm25(self):
        text = "Form FM-LIBS-009: Daily Entrance Log (ISBN: 978-0141036144)!"
        tokens = tokenize_for_bm25(text)
        self.assertIn("form", tokens)
        self.assertIn("fm", tokens)
        self.assertIn("libs", tokens)
        self.assertIn("009", tokens)
        self.assertIn("978", tokens)
        self.assertIn("0141036144", tokens)

    # 3. Reciprocal Rank Fusion (RRF) Tests
    def test_reciprocal_rank_fusion_math_and_order(self):
        vector_hits = [
            {"id": "doc_A", "text": "Passage A", "distance": 0.2},
            {"id": "doc_B", "text": "Passage B", "distance": 0.4},
            {"id": "doc_C", "text": "Passage C", "distance": 0.6},
        ]
        bm25_hits = [
            {"id": "doc_B", "text": "Passage B", "bm25_score": 15.2},
            {"id": "doc_C", "text": "Passage C", "bm25_score": 8.1},
            {"id": "doc_D", "text": "Passage D", "bm25_score": 5.0},
        ]

        fused = TarsArchive._reciprocal_rank_fusion(vector_hits, bm25_hits, k=60)
        self.assertGreater(len(fused), 0)

        # doc_B is rank 2 in vector and rank 1 in BM25:
        # score = 1/(60+2) + 1/(60+1) = 1/62 + 1/61 = 0.016129 + 0.016393 = ~0.032522
        # doc_A is rank 1 in vector and unranked in BM25:
        # score = 1/(60+1) = 0.016393
        # Therefore, doc_B must be ranked #1 after fusion!
        self.assertEqual(fused[0]["id"], "doc_B")
        self.assertIn("rrf_score", fused[0])
        self.assertAlmostEqual(fused[0]["rrf_score"], (1.0 / 62) + (1.0 / 61), places=4)

    # 4. In-Memory BM25 Search & Scoping Tests
    def test_bm25_search_retrieves_exact_matches(self):
        sample_corpus = [
            {
                "id": "c1",
                "text": "Discussion on sorting algorithms: QuickSort and MergeSort.",
                "metadata": {"book_id": "b1", "source": "algo.pdf", "page": 10},
            },
            {
                "id": "c2",
                "text": "Official compliance policy for Form FM-LIBS-009 university entrance.",
                "metadata": {"book_id": "b2", "source": "policy.pdf", "page": 5},
            },
            {
                "id": "c3",
                "text": "Database indexing using B-Trees and Hashing techniques.",
                "metadata": {"book_id": "b3", "source": "db.pdf", "page": 88},
            },
        ]

        from rank_bm25 import BM25Okapi
        tokenized = [tokenize_for_bm25(doc["text"]) for doc in sample_corpus]
        self.rag._bm25_docs = sample_corpus
        self.rag._bm25_index = BM25Okapi(tokenized)

        # Query exact code "FM-LIBS-009"
        hits = self.rag._search_bm25("FM-LIBS-009", top_k=2)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["id"], "c2")
        self.assertEqual(hits[0]["page"], 5)

        # Query with scoping by book_id
        hits_scoped = self.rag._search_bm25(
            "algorithms", top_k=2, candidate_book_ids=["b1"]
        )
        self.assertEqual(len(hits_scoped), 1)
        self.assertEqual(hits_scoped[0]["id"], "c1")

    # 5. BGE Query Prefixing Tests
    def test_bge_query_prefixing_applied_for_bge_models(self):
        with patch("core.ai_engine.rag_pipeline.EMBEDDING_MODEL_NAME", "BAAI/bge-small-en-v1.5"):
            mock_embedder = MagicMock()
            mock_vec = MagicMock()
            mock_vec.tolist.return_value = [0.1, 0.2, 0.3]
            mock_embedder.encode.return_value = mock_vec
            self.rag._embedder = mock_embedder

            # Clear cache to force encode
            self.rag._encode_query.cache_clear()
            res = self.rag._encode_query("What is data encapsulation?")

            # Verify query was prepended with BGE prefix
            called_query = mock_embedder.encode.call_args[0][0]
            self.assertTrue(called_query.startswith(BGE_QUERY_PREFIX))
            self.assertIn("What is data encapsulation?", called_query)

    def test_bge_query_prefixing_omitted_for_minilm(self):
        with patch("core.ai_engine.rag_pipeline.EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2"):
            mock_embedder = MagicMock()
            mock_vec = MagicMock()
            mock_vec.tolist.return_value = [0.1, 0.2, 0.3]
            mock_embedder.encode.return_value = mock_vec
            self.rag._embedder = mock_embedder

            self.rag._encode_query.cache_clear()
            res = self.rag._encode_query("What is data encapsulation?")

            called_query = mock_embedder.encode.call_args[0][0]
            self.assertFalse(called_query.startswith(BGE_QUERY_PREFIX))
            self.assertEqual(called_query, "What is data encapsulation?")

    # 6. Cross-Encoder Reranker Graceful Fallback Tests
    def test_reranker_fallback_when_disabled(self):
        candidates = [
            {"id": "doc_1", "text": "First passage"},
            {"id": "doc_2", "text": "Second passage"},
        ]
        with patch("core.ai_engine.rag_pipeline.ENABLE_RERANKER", False):
            reranked = self.rag._rerank_candidates("query", candidates, top_k=2)
            self.assertEqual(reranked, candidates)

    def test_reranker_scores_and_sorts_descending(self):
        candidates = [
            {"id": "doc_1", "text": "Passage about weather"},
            {"id": "doc_2", "text": "Passage about database ACID transactions"},
        ]
        mock_reranker = MagicMock()
        mock_reranker.predict.return_value = [-1.5, 4.8]  # doc_2 is vastly more relevant

        with patch("core.ai_engine.rag_pipeline.ENABLE_RERANKER", True):
            self.rag._reranker = mock_reranker
            reranked = self.rag._rerank_candidates("What are ACID properties?", candidates, top_k=2)
            self.assertEqual(reranked[0]["id"], "doc_2")
            self.assertAlmostEqual(reranked[0]["rerank_score"], 4.8)

    # 7. Backward Compatibility Alias Test
    def test_enhanced_rag_pipeline_alias(self):
        self.assertIs(EnhancedRAGPipeline, TarsArchive)


if __name__ == "__main__":
    unittest.main()
