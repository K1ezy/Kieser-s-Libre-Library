import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import FastAPI
import httpx
import time

from core.database.repositories.annotation_repository import AnnotationRepository
from core.external_api.annotations_router import annotations_router


class AsyncCursorMock:
    """Helper mock to simulate Motor's async cursor with to_list()."""
    def __init__(self, data):
        self._data = data

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return self._data


class TestAnnotationRepository(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.repo = AnnotationRepository(self.mock_db)

    async def test_create_annotation_success(self):
        self.mock_db['annotations'].insert_one = AsyncMock(return_value=MagicMock(acknowledged=True))

        res = await self.repo.create_annotation(
            user_id="user_123",
            book_id="book_abc",
            selected_text="It is a truth universally acknowledged...",
            color="yellow",
            cfi_range="epubcfi(/6/4!/4/2:0)",
            page_number=1,
            rects=[{"x": 10.0, "y": 20.0, "width": 100.0, "height": 14.0}],
            note="Famous opening line"
        )
        self.assertTrue(res["success"])
        ann = res["annotation"]
        self.assertTrue(ann["id"].startswith("ann_"))
        self.assertEqual(ann["user_id"], "user_123")
        self.assertEqual(ann["book_id"], "book_abc")
        self.assertEqual(ann["color"], "yellow")
        self.assertEqual(ann["selected_text"], "It is a truth universally acknowledged...")
        self.assertEqual(ann["note"], "Famous opening line")
        self.mock_db['annotations'].insert_one.assert_called_once()

    async def test_create_annotation_empty_text_fails(self):
        res = await self.repo.create_annotation(
            user_id="user_123",
            book_id="book_abc",
            selected_text="   "
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "Selected text cannot be empty")

    async def test_get_book_annotations(self):
        sample_annotations = [
            {
                "id": "ann_1",
                "user_id": "user_1",
                "book_id": "book_1",
                "selected_text": "Sample quote 1",
                "color": "yellow",
                "page_number": 5
            },
            {
                "id": "ann_2",
                "user_id": "user_1",
                "book_id": "book_1",
                "selected_text": "Sample quote 2",
                "color": "green",
                "page_number": 12
            }
        ]
        self.mock_db['annotations'].find = MagicMock(return_value=AsyncCursorMock(sample_annotations))

        res = await self.repo.get_book_annotations("user_1", "book_1")
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]["id"], "ann_1")
        self.assertEqual(res[1]["color"], "green")

    async def test_get_annotation_by_id(self):
        doc = {
            "id": "ann_99",
            "user_id": "user_test",
            "book_id": "book_test",
            "selected_text": "Target quote"
        }
        self.mock_db['annotations'].find_one = AsyncMock(return_value=doc)

        res = await self.repo.get_annotation("ann_99")
        self.assertIsNotNone(res)
        self.assertEqual(res["id"], "ann_99")
        self.assertEqual(res["selected_text"], "Target quote")

    async def test_update_annotation_color_and_note(self):
        self.mock_db['annotations'].update_one = AsyncMock(
            return_value=MagicMock(acknowledged=True, matched_count=1)
        )

        res = await self.repo.update_annotation(
            "ann_99",
            {"color": "pink", "note": "Updated interpretation"}
        )
        self.assertTrue(res)
        self.mock_db['annotations'].update_one.assert_called_once()
        args = self.mock_db['annotations'].update_one.call_args[0]
        query, update = args[0], args[1]
        self.assertEqual(query, {"id": "ann_99"})
        self.assertEqual(update["$set"]["color"], "pink")
        self.assertEqual(update["$set"]["note"], "Updated interpretation")
        self.assertIn("updated_at", update["$set"])

    async def test_delete_annotation(self):
        self.mock_db['annotations'].delete_one = AsyncMock(
            return_value=MagicMock(acknowledged=True, deleted_count=1)
        )

        res = await self.repo.delete_annotation("ann_99", user_id="user_123")
        self.assertTrue(res)
        self.mock_db['annotations'].delete_one.assert_called_once_with({"id": "ann_99", "user_id": "user_123"})

    def test_generate_markdown_export(self):
        annotations = [
            {
                "id": "ann_1",
                "color": "yellow",
                "page_number": 42,
                "selected_text": "To be, or not to be, that is the question.",
                "note": "Hamlet soliloquy exploring existence",
                "created_at": 1791850000.0
            },
            {
                "id": "ann_2",
                "color": "green",
                "page_number": 45,
                "selected_text": "Thus conscience does make cowards of us all.",
                "note": "",
                "created_at": 1791851000.0
            }
        ]

        md = self.repo.generate_markdown_export(annotations, book_title="Hamlet")
        self.assertIn("# 📚 Reading Notes & Highlights: Hamlet", md)
        self.assertIn("**Total Annotations:** 2", md)
        self.assertIn("[Yellow] Page 42", md)
        self.assertIn("> \"To be, or not to be, that is the question.\"", md)
        self.assertIn("**Note:** Hamlet soliloquy exploring existence", md)
        self.assertIn("[Green] Page 45", md)


class TestAnnotationsRouter(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(annotations_router)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver"
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    @patch('core.external_api.annotations_router.mongo_db')
    async def test_api_create_annotation(self, mock_mongo):
        created_doc = {
            "id": "ann_20261013_xyz",
            "book_id": "book_108",
            "user_id": "student_a",
            "selected_text": "The quick brown fox jumps over the lazy dog.",
            "color": "blue",
            "page_number": 3,
            "note": "Typographic pangram"
        }
        mock_mongo.create_annotation = AsyncMock(return_value={"success": True, "annotation": created_doc})

        res = await self.client.post("/api/annotations/", json={
            "book_id": "book_108",
            "user_id": "student_a",
            "selected_text": "The quick brown fox jumps over the lazy dog.",
            "color": "blue",
            "page_number": 3,
            "note": "Typographic pangram"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["annotation"]["id"], "ann_20261013_xyz")
        self.assertEqual(data["annotation"]["color"], "blue")

    @patch('core.external_api.annotations_router.mongo_db')
    async def test_api_get_book_annotations(self, mock_mongo):
        mock_mongo.get_book_annotations = AsyncMock(return_value=[
            {"id": "ann_1", "selected_text": "Quote 1", "color": "yellow"},
            {"id": "ann_2", "selected_text": "Quote 2", "color": "pink"}
        ])

        res = await self.client.get("/api/annotations/book_108?user_id=student_a")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["annotations"]), 2)

    @patch('core.external_api.annotations_router.mongo_db')
    async def test_api_update_annotation(self, mock_mongo):
        mock_mongo.update_annotation = AsyncMock(return_value=True)
        mock_mongo.get_annotation = AsyncMock(return_value={
            "id": "ann_1",
            "color": "green",
            "note": "Updated insight"
        })

        res = await self.client.put("/api/annotations/ann_1", json={
            "color": "green",
            "note": "Updated insight"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["annotation"]["color"], "green")

    @patch('core.external_api.annotations_router.mongo_db')
    async def test_api_delete_annotation(self, mock_mongo):
        mock_mongo.delete_annotation = AsyncMock(return_value=True)

        res = await self.client.delete("/api/annotations/ann_1?user_id=student_a")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["deleted_id"], "ann_1")

    @patch('core.external_api.annotations_router.mongo_db')
    async def test_api_export_markdown(self, mock_mongo):
        mock_mongo.get_book_annotations = AsyncMock(return_value=[
            {"id": "ann_1", "color": "yellow", "page_number": 1, "selected_text": "Excerpt", "note": "Note"}
        ])
        mock_mongo.get_book_details = AsyncMock(return_value={"title": "Introduction to AI"})
        mock_mongo.generate_annotations_markdown = MagicMock(
            return_value="# 📚 Reading Notes & Highlights: Introduction to AI\n\n> Excerpt"
        )

        res = await self.client.get("/api/annotations/book_ai/export?user_id=student_a")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/markdown", res.headers.get("content-type", ""))
        self.assertIn("attachment; filename=", res.headers.get("content-disposition", ""))
        self.assertIn("# 📚 Reading Notes & Highlights: Introduction to AI", res.text)

    @patch('core.external_api.annotations_router.tars_engine')
    async def test_api_explain_passage(self, mock_tars):
        async def dummy_stream(messages, max_tokens=150):
            yield "This passage demonstrates the principle of causality in physics. "
            yield "Actions directly result in measurable outcomes."

        mock_tars.stream_response = dummy_stream

        res = await self.client.post("/api/annotations/explain", json={
            "passage_text": "Every action has an equal and opposite reaction.",
            "book_id": "book_physics",
            "context_title": "Classical Mechanics"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("causality in physics", data["explanation"])


if __name__ == "__main__":
    unittest.main()
