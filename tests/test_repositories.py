"""
Unit tests for domain repository pattern refactoring.
Verifies single-responsibility repository modules and backward-compatible facade delegation.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock
from core.database.mongo_manager import MongoManager
from core.database.repositories.book_repository import BookRepository
from core.database.repositories.chat_repository import ChatRepository
from core.database.repositories.user_repository import UserRepository
from core.database.repositories.planner_repository import PlannerRepository
from core.database.repositories.progress_repository import ProgressRepository


class TestRepositoriesArchitecture(unittest.TestCase):
    """Verifies modular separation of repositories and facade delegation."""

    def setUp(self):
        self.mock_db = MagicMock()
        self.manager = MongoManager()
        self.manager.db = self.mock_db

    def test_repository_domain_instances_exist(self):
        """MongoManager initializes dedicated domain repositories."""
        self.assertIsInstance(self.manager.books, BookRepository)
        self.assertIsInstance(self.manager.chats, ChatRepository)
        self.assertIsInstance(self.manager.chat, ChatRepository)
        self.assertIsInstance(self.manager.users, UserRepository)
        self.assertIsInstance(self.manager.planner, PlannerRepository)
        self.assertIsInstance(self.manager.progress, ProgressRepository)

    def test_facade_delegates_to_book_repository(self):
        """Facade methods cleanly delegate to the domain BookRepository."""
        self.manager.books.get_recent_books = AsyncMock(return_value=[{"id": "b1", "title": "Test Book"}])
        
        import asyncio
        result = asyncio.run(self.manager.get_recent_books(limit=5))
        self.manager.books.get_recent_books.assert_called_once_with(limit=5)
        self.assertEqual(result, [{"id": "b1", "title": "Test Book"}])

    def test_facade_delegates_to_chat_repository(self):
        """Facade methods delegate chat session queries to ChatRepository."""
        self.manager.chats.get_chat_sessions = AsyncMock(return_value=[{"id": "c1", "title": "Chat 1"}])
        
        import asyncio
        result = asyncio.run(self.manager.get_chat_sessions(limit=10, user_id="u1"))
        self.manager.chats.get_chat_sessions.assert_called_once_with(limit=10, user_id="u1")
        self.assertEqual(result, [{"id": "c1", "title": "Chat 1"}])

    def test_facade_delegates_to_user_repository(self):
        """Facade methods delegate user queries to UserRepository."""
        self.manager.users.get_user_by_identifier = AsyncMock(return_value={"id": "u1", "username": "admin"})
        
        import asyncio
        result = asyncio.run(self.manager.get_user_by_identifier("admin"))
        self.manager.users.get_user_by_identifier.assert_called_once_with("admin")
        self.assertEqual(result["id"], "u1")

    def test_book_repository_date_formatter(self):
        """Verifies BookRepository formatting helper."""
        repo = BookRepository(self.mock_db)
        # Formatted timestamp should contain the year
        self.assertIn("2023", repo.format_added_date(1700000000))
        self.assertEqual(repo.format_added_date("2024-01-15T00:00:00"), "2024-01-15")
        self.assertEqual(repo.format_added_date(None), "Recently")


if __name__ == '__main__':
    unittest.main()
