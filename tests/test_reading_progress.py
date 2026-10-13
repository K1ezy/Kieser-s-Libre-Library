import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import FastAPI
import httpx

from core.database.repositories.progress_repository import ProgressRepository
from core.external_api.progress_router import progress_router
from ui.pages.reader_interface import BookReader


class TestReadingProgressRepository(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.repo = ProgressRepository(self.mock_db)

    async def test_save_reading_progress_with_cfi(self):
        self.mock_db['reading_progress'].find_one = AsyncMock(return_value=None)
        self.mock_db['reading_progress'].update_one = AsyncMock(return_value=MagicMock(acknowledged=True))

        res = await self.repo.save_reading_progress(
            user_id="user_123",
            book_id="book_abc",
            current_page=25,
            total_pages=100,
            status="reading",
            cfi="epubcfi(/6/14[ch2]!/4/2:0)",
            client_timestamp=1790000000.0
        )
        self.assertTrue(res)
        self.mock_db['reading_progress'].update_one.assert_called_once()
        args = self.mock_db['reading_progress'].update_one.call_args[0]
        query, update = args[0], args[1]
        self.assertEqual(query, {"user_id": "user_123", "book_id": "book_abc"})
        self.assertEqual(update["$set"]["current_page"], 25)
        self.assertEqual(update["$set"]["progress_percent"], 25.0)
        self.assertEqual(update["$set"]["cfi"], "epubcfi(/6/14[ch2]!/4/2:0)")

    async def test_save_reading_progress_preserves_existing_cfi(self):
        existing_doc = {
            "user_id": "user_123",
            "book_id": "book_abc",
            "current_page": 20,
            "cfi": "epubcfi(/6/12!/4:0)",
            "last_read_at": 1790000000.0
        }
        self.mock_db['reading_progress'].find_one = AsyncMock(return_value=existing_doc)
        self.mock_db['reading_progress'].update_one = AsyncMock(return_value=MagicMock(acknowledged=True))

        # Save without providing cfi
        res = await self.repo.save_reading_progress(
            user_id="user_123",
            book_id="book_abc",
            current_page=21,
            total_pages=100,
            status="reading",
            cfi=None,
            client_timestamp=1790000010.0
        )
        self.assertTrue(res)
        update = self.mock_db['reading_progress'].update_one.call_args[0][1]
        self.assertEqual(update["$set"]["cfi"], "epubcfi(/6/12!/4:0)")

    async def test_save_reading_progress_discards_stale_update(self):
        existing_doc = {
            "user_id": "user_123",
            "book_id": "book_abc",
            "current_page": 50,
            "last_read_at": 1790000100.0
        }
        self.mock_db['reading_progress'].find_one = AsyncMock(return_value=existing_doc)
        self.mock_db['reading_progress'].update_one = AsyncMock()

        # Attempt to save older position (timestamp = 1790000050.0 < 1790000100.0)
        res = await self.repo.save_reading_progress(
            user_id="user_123",
            book_id="book_abc",
            current_page=45,
            total_pages=100,
            client_timestamp=1790000050.0
        )
        self.assertTrue(res)
        self.mock_db['reading_progress'].update_one.assert_not_called()


class TestReadingProgressAPI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(progress_router)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver"
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    @patch('core.external_api.progress_router.mongo_db')
    async def test_api_sync_forward_navigation(self, mock_mongo):
        mock_mongo.save_reading_progress = AsyncMock(return_value=True)
        mock_mongo.update_book_reading_status = AsyncMock(return_value=True)

        res = await self.client.post("/api/progress/sync", json={
            "book_id": "book_108",
            "user_id": "user_alpha",
            "current_page": 10,
            "total_pages": 100,
            "cfi": "epubcfi(/6/14[ch2]!/4/2:0)"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["current_page"], 10)
        self.assertEqual(data["total_pages"], 100)
        self.assertEqual(data["progress_percent"], 10.0)
        self.assertEqual(data["cfi"], "epubcfi(/6/14[ch2]!/4/2:0)")
        mock_mongo.save_reading_progress.assert_called_once()

    @patch('core.external_api.progress_router.mongo_db')
    async def test_api_sync_backward_navigation(self, mock_mongo):
        mock_mongo.save_reading_progress = AsyncMock(return_value=True)
        mock_mongo.update_book_reading_status = AsyncMock(return_value=True)

        res = await self.client.post("/api/progress/sync", json={
            "book_id": "book_108",
            "user_id": "user_alpha",
            "current_page": 5,
            "total_pages": 100,
            "cfi": "epubcfi(/6/8[ch1]!/4/1:0)"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["current_page"], 5)
        self.assertEqual(data["progress_percent"], 5.0)

    @patch('core.external_api.progress_router.mongo_db')
    async def test_api_sync_completed_status_transition(self, mock_mongo):
        mock_mongo.save_reading_progress = AsyncMock(return_value=True)
        mock_mongo.update_book_reading_status = AsyncMock(return_value=True)

        res = await self.client.post("/api/progress/sync", json={
            "book_id": "book_108",
            "user_id": "user_alpha",
            "current_page": 100,
            "total_pages": 100
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["reading_status"], "completed")
        self.assertEqual(data["progress_percent"], 100.0)

    @patch('core.external_api.progress_router.mongo_db')
    async def test_api_sync_pdf_progress(self, mock_mongo):
        mock_mongo.save_reading_progress = AsyncMock(return_value=True)
        mock_mongo.update_book_reading_status = AsyncMock(return_value=True)

        # PDF with 66 pages at page 10: progress formula ((10-1)/(66-1))*100 = 13.8%
        res = await self.client.post("/api/progress/sync", json={
            "book_id": "pdf_book_11",
            "user_id": "student_1",
            "current_page": 10,
            "total_pages": 66,
            "progress_percent": 13.8,
            "cfi": None
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["current_page"], 10)
        self.assertEqual(data["total_pages"], 66)
        self.assertEqual(data["progress_percent"], 13.8)
        self.assertIsNone(data["cfi"])

    @patch('core.external_api.progress_router.mongo_db')
    async def test_api_sync_with_appearance_preferences(self, mock_mongo):
        mock_mongo.save_reading_progress = AsyncMock(return_value=True)
        mock_mongo.update_book_reading_status = AsyncMock(return_value=True)
        mock_mongo.save_reader_preferences = AsyncMock(return_value=True)

        res = await self.client.post("/api/progress/sync", json={
            "book_id": "epub_book_99",
            "user_id": "student_reader",
            "current_page": 40,
            "total_pages": 200,
            "progress_percent": 20.0,
            "theme": "sepia",
            "font_size": 18,
            "font_family": "serif",
            "line_height": 1.65
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["theme"], "sepia")
        self.assertEqual(data["font_size"], 18)
        self.assertEqual(data["font_family"], "serif")
        self.assertEqual(data["line_height"], 1.65)
        mock_mongo.save_reader_preferences.assert_called_once_with(
            "student_reader",
            {"theme": "sepia", "font_size": 18, "font_family": "serif", "line_height": 1.65}
        )

    @patch('core.external_api.progress_router.mongo_db')
    async def test_api_preferences_get_and_post(self, mock_mongo):
        mock_mongo.get_reader_preferences = AsyncMock(return_value={
            "theme": "dark", "font_size": 20, "font_family": "dyslexic", "line_height": 1.95
        })
        mock_mongo.save_reader_preferences = AsyncMock(return_value=True)

        # GET preferences
        res_get = await self.client.get("/api/progress/preferences/user_test")
        self.assertEqual(res_get.status_code, 200)
        data_get = res_get.json()
        self.assertEqual(data_get["preferences"]["theme"], "dark")
        self.assertEqual(data_get["preferences"]["font_size"], 20)

        # POST preferences
        res_post = await self.client.post("/api/progress/preferences/user_test", json={
            "theme": "black",
            "font_size": 22,
            "font_family": "sans",
            "line_height": 1.4
        })
        self.assertEqual(res_post.status_code, 200)
        data_post = res_post.json()
        self.assertEqual(data_post["status"], "ok")
        self.assertEqual(data_post["preferences"]["theme"], "black")
        mock_mongo.save_reader_preferences.assert_called_once()


class TestBookReaderComponent(unittest.TestCase):
    def test_reader_initialization(self):
        reader = BookReader(
            book_id="108",
            current_page=15,
            total_pages=250,
            user_id="user_test",
            saved_cfi="epubcfi(/6/14!/4:0)",
            theme="sepia",
            font_size=18,
            font_family="serif",
            line_height=1.95
        )
        self.assertEqual(reader.book_id, "108")
        self.assertEqual(reader.current_page, 15)
        self.assertEqual(reader.total_pages, 250)
        self.assertEqual(reader.user_id, "user_test")
        self.assertEqual(reader.saved_cfi, "epubcfi(/6/14!/4:0)")
        self.assertEqual(reader.theme, "sepia")
        self.assertEqual(reader.font_size, 18)
        self.assertEqual(reader.font_family, "serif")
        self.assertEqual(reader.line_height, 1.95)

    def test_reader_theme_palette_helpers(self):
        reader_light = BookReader(book_id="108", theme="light")
        cls, bg = reader_light.get_prose_theme_classes()
        self.assertIn("bg-white", cls)
        self.assertEqual(bg, "#f8fafc")

        reader_sepia = BookReader(book_id="108", theme="sepia")
        cls, bg = reader_sepia.get_prose_theme_classes()
        self.assertIn("bg-[#fbf0d9]", cls)
        self.assertEqual(bg, "#f4ecd8")

        reader_dark = BookReader(book_id="108", theme="dark")
        cls, bg = reader_dark.get_prose_theme_classes()
        self.assertIn("bg-[#1e293b]", cls)
        self.assertEqual(bg, "#0f172a")

        reader_black = BookReader(book_id="108", theme="black")
        cls, bg = reader_black.get_prose_theme_classes()
        self.assertIn("bg-[#09090b]", cls)
        self.assertEqual(bg, "#000000")

    def test_reader_invalid_id_rejection(self):
        reader = BookReader(book_id="../../etc/passwd")
        res = reader.find_content_file()
        self.assertFalse(res)
        self.assertIn("Invalid book identifier format", reader.error_msg)

    def test_reader_detects_pdf_and_epub_formats(self):
        # Book 11 is Alice in Wonderland (PDF)
        pdf_reader = BookReader(book_id="11", current_page=1, total_pages=66)
        found_pdf = pdf_reader.find_content_file()
        self.assertTrue(found_pdf)
        self.assertEqual(pdf_reader.file_type, "pdf")
        self.assertIn(".pdf", pdf_reader.file_name.lower())

        # Book 108 is Sherlock Holmes (EPUB)
        epub_reader = BookReader(book_id="108", current_page=1, total_pages=100)
        found_epub = epub_reader.find_content_file()
        self.assertTrue(found_epub)
        self.assertEqual(epub_reader.file_type, "epub")
        self.assertIn(".epub", epub_reader.file_name.lower())

    def test_reader_finds_witcher_pdf_with_special_characters(self):
        witcher_reader = BookReader(book_id="The_Complete_Witcher__The_Last___Andrzej_Sapkowski_(1)_ba93")
        found = witcher_reader.find_content_file()
        self.assertTrue(found, f"Witcher book should be found, error: {witcher_reader.error_msg}")
        self.assertEqual(witcher_reader.file_type, "pdf")
        self.assertIn(".pdf", witcher_reader.file_name.lower())


if __name__ == '__main__':
    unittest.main()

