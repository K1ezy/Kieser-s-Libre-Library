import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from core.database.repositories.syllabus_repository import SyllabusRepository, get_course_syllabus_map
from components.chat.message_bubble import (
    linkify_tars_citations,
    build_deep_link_url,
    _extract_highlight_snippet,
)
from core.ai_engine.rag_pipeline import ResilientRAGPipeline, ScopedHybridRAGPipeline


class TestCitationLinkification(unittest.TestCase):
    """Verifies deterministic citation linkification and reader deep-linking."""

    def test_extract_highlight_snippet(self):
        text = "[Book: CS 401 | Page 84]\nRound-robin scheduling assigns a fixed time quantum to each active process in the ready queue."
        snippet = _extract_highlight_snippet(text, max_words=6)
        self.assertEqual(snippet, "Round-robin scheduling assigns a fixed time")

    def test_build_deep_link_url_pdf(self):
        meta = {"book_id": "book_abc123", "format": "PDF", "page": 84}
        text = "Process synchronization prevents race conditions across concurrent threads."
        url = build_deep_link_url(meta, text)
        self.assertTrue(url.startswith("/read/book_abc123?page=84&highlight="))
        self.assertIn("Process+synchronization", url)

    def test_build_deep_link_url_epub(self):
        meta = {"book_id": "epub_456", "format": "EPUB", "cfi": "/6/4[chap01]!/4/2"}
        text = "Distributed databases maintain consistency."
        url = build_deep_link_url(meta, text)
        self.assertTrue(url.startswith("/read/epub_456?cfi="))
        self.assertIn("chap01", url)

    def test_linkify_tars_citations_book_tag(self):
        chunks = [
            {
                "text": "Virtual memory paging allows contiguous address spaces.",
                "metadata": {
                    "book_id": "os_book_1",
                    "title": "Operating Systems Principles",
                    "page": 84,
                    "format": "PDF",
                },
            }
        ]
        llm_text = "Paging abstracts physical memory [Book: Operating Systems Principles | Page 84]."
        linkified = linkify_tars_citations(llm_text, chunks)

        self.assertIn('class="tars-citation-chip"', linkified)
        self.assertIn('/read/os_book_1?page=84', linkified)
        self.assertIn('📖 Operating Systems Principles — p. 84', linkified)

    def test_linkify_tars_citations_source_index(self):
        chunks = [
            {
                "text": "Normalization decomposes tables to eliminate redundancy.",
                "metadata": {
                    "book_id": "db_book_2",
                    "title": "Database Systems",
                    "page": 112,
                    "format": "PDF",
                },
            }
        ]
        llm_text = "Third Normal Form removes transitive dependencies [Source 1, Page 112]."
        linkified = linkify_tars_citations(llm_text, chunks)

        self.assertIn('/read/db_book_2?page=112', linkified)
        self.assertIn('Database Systems', linkified)

    def test_linkify_tars_citations_single_source_fallback(self):
        chunks = [
            {
                "text": "Computer networks use packet switching.",
                "metadata": {
                    "book_id": "net_book_3",
                    "title": "Computer Networks",
                    "page": 45,
                    "format": "PDF",
                },
            }
        ]
        # LLM slightly mistitles book, but single source resolves deterministically
        llm_text = "Packets travel through routers [Net Architecture, p. 45]."
        linkified = linkify_tars_citations(llm_text, chunks)

        self.assertIn('/read/net_book_3?page=45', linkified)

    def test_linkify_preserves_unrelated_brackets(self):
        chunks = [
            {
                "text": "Sample text",
                "metadata": {"book_id": "b1", "title": "B1", "page": 1},
            }
        ]
        llm_text = "Array indexing like arr[0] is constant time O(1)."
        linkified = linkify_tars_citations(llm_text, chunks)
        self.assertEqual(linkified, llm_text)


class TestSyllabusRepository(unittest.IsolatedAsyncioTestCase):
    """Verifies course syllabus aggregation and Form FM-LIBS-002 curricular sync."""

    async def test_sync_approved_requisitions(self):
        mock_db = MagicMock()
        mock_reqs = MagicMock()
        mock_books = MagicMock()
        mock_db.__getitem__.side_effect = lambda key: mock_reqs if key == "requisitions" else mock_books

        class FakeAsyncCursor:
            def __init__(self, docs):
                self.docs = docs

            def __aiter__(self):
                self.iter = iter(self.docs)
                return self

            async def __anext__(self):
                try:
                    return next(self.iter)
                except StopIteration:
                    raise StopAsyncIteration

        mock_reqs.find.return_value = FakeAsyncCursor([
            {
                "course_code": "CS 401",
                "title": "Operating Systems",
                "isbn": "978-0133591620",
                "department": "BSCS",
                "course_title": "Operating Systems & Concurrency",
            }
        ])

        mock_update_res = MagicMock()
        mock_update_res.modified_count = 1
        mock_books.update_many = AsyncMock(return_value=mock_update_res)

        repo = SyllabusRepository(mock_db)
        synced = await repo.sync_approved_requisitions_to_books()

        self.assertEqual(synced, 1)
        mock_books.update_many.assert_called_once()
        args, kwargs = mock_books.update_many.call_args
        self.assertIn("$addToSet", args[1])
        self.assertEqual(args[1]["$addToSet"]["course_codes"], "CS 401")

    async def test_get_available_course_scopes_priority(self):
        mock_db = MagicMock()
        mock_books = MagicMock()
        mock_db.__getitem__.return_value = mock_books

        class FakeAsyncCursor:
            def __init__(self, docs):
                self.docs = docs

            def __aiter__(self):
                self.iter = iter(self.docs)
                return self

            async def __anext__(self):
                try:
                    return next(self.iter)
                except StopIteration:
                    raise StopAsyncIteration

        mock_books.find.return_value = FakeAsyncCursor([
            {
                "_id": "bid_it302",
                "title": "Database Systems",
                "course_codes": ["IT 302"],
                "course_titles": {"IT 302": "Database Management"},
                "program": "BSIT",
                "category": "Databases",
            },
            {
                "_id": "bid_cs401",
                "title": "Modern OS",
                "course_codes": ["CS 401"],
                "course_titles": {"CS 401": "Operating Systems"},
                "program": "BSCS",
                "category": "Systems",
            },
        ])

        repo = SyllabusRepository(mock_db)
        scopes = await repo.get_available_course_scopes(user_program="BSCS")

        self.assertEqual(len(scopes), 2)
        # BSCS program should prioritize CS 401 as first entry
        self.assertEqual(scopes[0]["course_code"], "CS 401")
        self.assertEqual(scopes[1]["course_code"], "IT 302")
        self.assertIn("bid_cs401", scopes[0]["book_ids"])

    async def test_get_course_syllabus_map_helper(self):
        mock_db = MagicMock()
        mock_books = MagicMock()
        mock_reqs = MagicMock()
        mock_db.__getitem__.side_effect = lambda k: mock_reqs if k == "requisitions" else mock_books

        class FakeAsyncCursor:
            def __init__(self, docs):
                self.docs = docs

            def __aiter__(self):
                self.iter = iter(self.docs)
                return self

            async def __anext__(self):
                try:
                    return next(self.iter)
                except StopIteration:
                    raise StopAsyncIteration

        mock_reqs.find.return_value = FakeAsyncCursor([])
        mock_books.find.return_value = FakeAsyncCursor([
            {
                "_id": "bid_cs401",
                "title": "Operating Systems",
                "course_codes": ["CS 401"],
                "course_titles": {"CS 401": "Operating Systems"},
                "program": "BSCS",
            }
        ])

        s_map = await get_course_syllabus_map(mock_db)
        self.assertIn("CS 401", s_map)
        self.assertEqual(s_map["CS 401"]["book_ids"], ["bid_cs401"])


class TestChromaMultiBookScoping(unittest.TestCase):
    """Verifies ChromaDB native $in filtering without premature loop breaking."""

    def test_search_with_metadata_multi_book_in_clause(self):
        pipeline = ResilientRAGPipeline.__new__(ResilientRAGPipeline)
        pipeline.collection = MagicMock()
        pipeline.enable_hybrid_bm25 = False
        pipeline._embedder = MagicMock()
        pipeline._reranker = None
        pipeline.rag_max_distance = 0.68
        pipeline._bm25_docs = []
        pipeline._query_cache = {}
        pipeline._get_cached = MagicMock(return_value=None)
        pipeline._set_cached = MagicMock()
        pipeline._filter_results = ResilientRAGPipeline._filter_results
        pipeline._encode_query = MagicMock(return_value=[0.1] * 384)

        pipeline.collection.query.return_value = {
            "ids": [["c1", "c2"]],
            "documents": [["doc 1", "doc 2"]],
            "metadatas": [[{"book_id": "b1", "page": 10}, {"book_id": "b2", "page": 20}]],
            "distances": [[0.25, 0.35]],
        }

        hits = pipeline.search_with_metadata(
            query="concurrency deadlock",
            candidate_book_ids=["b1", "b2"],
            course_code_scope="CS 401",
            top_k=5,
        )

        pipeline.collection.query.assert_called_once()
        call_kwargs = pipeline.collection.query.call_args[1]
        self.assertEqual(call_kwargs["where"], {"book_id": {"$in": ["b1", "b2"]}})
        self.assertEqual(len(hits), 2)
        found_bids = {h["metadata"]["book_id"] for h in hits}
        self.assertEqual(found_bids, {"b1", "b2"})

    def test_scoped_hybrid_rag_pipeline_search_and_out_of_scope(self):
        mock_col = MagicMock()
        mock_embed = MagicMock()
        mock_embed.encode.return_value = MagicMock(tolist=lambda: [[0.1] * 384])

        pipeline = ScopedHybridRAGPipeline(
            chroma_collection=mock_col,
            embedder=mock_embed,
            rag_max_distance=0.68,
        )

        # 1. Matching hits
        mock_col.query.return_value = {
            "ids": [["chunk_1"]],
            "documents": [["Virtual memory page tables"]],
            "metadatas": [[{"book_id": "b_os", "title": "OS Book", "page": 84}]],
            "distances": [[0.32]],
        }

        res = pipeline.search_with_metadata(
            query="virtual memory",
            candidate_book_ids=["b_os"],
            course_code_scope="CS 401",
        )

        self.assertFalse(res["out_of_scope"])
        self.assertEqual(len(res["chunks"]), 1)
        self.assertEqual(res["chunks"][0]["id"], "chunk_1")
        mock_col.query.assert_called_with(
            query_embeddings=[[0.1] * 384],
            n_results=16,
            where={"book_id": "b_os"},
            include=["documents", "metadatas", "distances"],
        )

        # 2. Out of scope fallback
        mock_col.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        out_res = pipeline.search_with_metadata(
            query="macroeconomics monetary policy",
            candidate_book_ids=["b_os"],
            course_code_scope="CS 401",
        )
        self.assertTrue(out_res["out_of_scope"])
        self.assertIn("CS 401", out_res["fallback_message"])
        self.assertEqual(out_res["chunks"], [])


if __name__ == "__main__":
    unittest.main()

