import unittest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

from core.database.repositories.book_repository import BookRepository
from core.database.mongo_manager import MongoManager
from ui.pages.book_details import BookDetailsPage


class TestBookDetails(unittest.IsolatedAsyncioTestCase):
    """Test suite for BookDetailsPage components and BookRepository metadata formatting."""

    def setUp(self):
        self.mock_db = MagicMock()
        self.repo = BookRepository(self.mock_db)

    def test_format_added_date_datetime(self):
        """Verifies datetime instances format to '%b %d, %Y'."""
        dt = datetime(2026, 1, 8, 17, 13, 42)
        formatted = self.repo.format_added_date(dt)
        self.assertEqual(formatted, "Jan 08, 2026")

    def test_format_added_date_timestamp(self):
        """Verifies numeric timestamps format cleanly."""
        formatted = self.repo.format_added_date(1700000000)
        self.assertIn("2023", formatted)

    def test_format_added_date_string(self):
        """Verifies ISO string dates format properly."""
        formatted = self.repo.format_added_date("2024-01-15T00:00:00")
        self.assertEqual(formatted, "2024-01-15")

    def test_format_added_date_none(self):
        """Verifies None falls back to 'Recently'."""
        formatted = self.repo.format_added_date(None)
        self.assertEqual(formatted, "Recently")

    def test_mongo_manager_resolve_path_delegation(self):
        """Verifies MongoManager delegates resolve_document_path to BookRepository."""
        mgr = MongoManager()
        mgr.books = MagicMock()
        mgr.books.resolve_document_path.return_value = "/mock/path.pdf"
        res = mgr.resolve_document_path("123", {"title": "Test"})
        self.assertEqual(res, "/mock/path.pdf")
        mgr.books.resolve_document_path.assert_called_once_with("123", {"title": "Test"})

    def test_book_details_page_initialization(self):
        """Verifies BookDetailsPage stores book_id properly."""
        page = BookDetailsPage("test-book-id")
        self.assertEqual(page.book_id, "test-book-id")
        self.assertIsNone(page.book)
        self.assertIsNone(page.content_container)
        self.assertIsNone(page.reading_card_container)

    @patch('ui.pages.book_details.mongo_db')
    @patch('ui.pages.book_details.ui')
    @patch('ui.pages.book_details.app')
    async def test_update_reading_status_lifecycle(self, mock_app, mock_ui, mock_db):
        """Verifies status transitions for Want to Read, Reading, and Completed."""
        mock_app.storage.user.get.return_value = 'test-user-123'
        mock_db.update_book_reading_status = AsyncMock(return_value=True)
        mock_db.progress.save_reading_progress = AsyncMock(return_value=True)

        page = BookDetailsPage("book-abc")
        page.book = {'id': 'book-abc', 'title': 'Test Book', 'page_count': 200, 'reading_status': 'none'}
        page.render_reading_card = MagicMock()

        # 1. Want to Read
        await page.update_reading_status('want_to_read')
        self.assertEqual(page.book['reading_status'], 'want_to_read')
        self.assertEqual(page.reading_progress['status'], 'want_to_read')
        self.assertEqual(page.reading_progress['current_page'], 0)
        self.assertEqual(page.reading_progress['progress_percent'], 0.0)
        mock_db.update_book_reading_status.assert_called_with('book-abc', 'want_to_read')
        page.render_reading_card.assert_called()

        # 2. Currently Reading
        await page.update_reading_status('reading')
        self.assertEqual(page.book['reading_status'], 'reading')
        self.assertEqual(page.reading_progress['status'], 'reading')
        self.assertEqual(page.reading_progress['current_page'], 1)
        self.assertEqual(page.reading_progress['progress_percent'], 0.5)

        # 3. Update page number
        await page.update_page_number(50)
        self.assertEqual(page.reading_progress['current_page'], 50)
        self.assertEqual(page.reading_progress['progress_percent'], 25.0)

        # 4. Completed
        await page.update_reading_status('completed')
        self.assertEqual(page.book['reading_status'], 'completed')
        self.assertEqual(page.reading_progress['status'], 'completed')
        self.assertEqual(page.reading_progress['current_page'], 200)
        self.assertEqual(page.reading_progress['progress_percent'], 100.0)

    def test_get_reading_history_delegation(self):
        """Verifies MongoManager delegates get_reading_history to ProgressRepository."""
        mgr = MongoManager()
        mgr.progress = MagicMock()
        mgr.progress.get_reading_history = AsyncMock(return_value=[{'book_id': 'b1', 'status': 'reading'}])
        
        import asyncio
        res = asyncio.run(mgr.get_reading_history("u1", limit=50))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]['book_id'], 'b1')
        mgr.progress.get_reading_history.assert_called_once_with("u1", limit=50)


if __name__ == '__main__':
    unittest.main()
