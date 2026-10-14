import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio

from core.database.repositories.planner_repository import PlannerRepository
from core.database.repositories.user_repository import UserRepository
from core.database.repositories.annotation_repository import AnnotationRepository
from core.database.repositories.requisition_repository import RequisitionRepository
from core.utils.media_handler import save_user_avatar, save_user_cover


class AsyncCursorMock:
    """Helper mock to simulate Motor async cursor."""
    def __init__(self, data):
        self._data = data

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return self._data


class TestAuditRemediation(unittest.IsolatedAsyncioTestCase):
    """Regression test suite validating all audit remediation fixes."""

    def setUp(self):
        self.mock_db = MagicMock()

    # --- 1. Planner Multi-Tenant Data Isolation ---
    async def test_planner_tasks_isolation_no_leakage(self):
        """Validates that a new user with 0 tasks receives an empty list and never leaks other users' tasks."""
        repo = PlannerRepository(self.mock_db)

        # User has zero tasks in database
        self.mock_db['planner_tasks'].find = MagicMock(
            return_value=AsyncCursorMock([])
        )

        tasks = await repo.get_tasks("new_user_without_tasks")
        self.assertEqual(tasks, [])
        # Verify query specifically targeted new_user_without_tasks
        find_query = self.mock_db['planner_tasks'].find.call_args[0][0]
        self.assertEqual(find_query, {"user_id": "new_user_without_tasks"})

    # --- 2. Per-User Favorites Isolation ---
    async def test_user_favorites_isolation(self):
        """Validates user-scoped favorites storage and lookup."""
        from core.database.repositories.book_repository import BookRepository
        repo = BookRepository(self.mock_db)

        # Toggle favorite on (add)
        self.mock_db['user_favorites'].find_one = AsyncMock(return_value=None)
        self.mock_db['user_favorites'].insert_one = AsyncMock(return_value=MagicMock(acknowledged=True))

        is_fav = await repo.toggle_book_favorite("book_42", user_id="user_A")
        self.assertTrue(is_fav)
        self.mock_db['user_favorites'].insert_one.assert_called_once()

        # Toggle favorite off (remove)
        self.mock_db['user_favorites'].find_one = AsyncMock(return_value={"user_id": "user_A", "book_id": "book_42"})
        self.mock_db['user_favorites'].delete_one = AsyncMock(return_value=MagicMock(acknowledged=True))

        is_fav_off = await repo.toggle_book_favorite("book_42", user_id="user_A")
        self.assertFalse(is_fav_off)

    async def test_get_user_favorite_book_ids(self):
        """Validates retrieval of favorite book IDs scoped strictly to requested user."""
        repo = UserRepository(self.mock_db)
        fav_docs = [
            {"user_id": "user_A", "book_id": "book_1"},
            {"user_id": "user_A", "book_id": "book_2"}
        ]
        self.mock_db['user_favorites'].find = MagicMock(return_value=AsyncCursorMock(fav_docs))

        ids = await repo.get_user_favorite_book_ids("user_A")
        self.assertEqual(set(ids), {"book_1", "book_2"})

    # --- 3. Annotation Ownership Enforcement ---
    async def test_annotation_update_ownership_filter(self):
        """Validates that update_annotation includes user_id in the query filter."""
        repo = AnnotationRepository(self.mock_db)
        self.mock_db['annotations'].update_one = AsyncMock(
            return_value=MagicMock(acknowledged=True, matched_count=1)
        )

        res = await repo.update_annotation(
            "ann_101",
            {"color": "green", "note": "Safe note"},
            user_id="legitimate_owner"
        )
        self.assertTrue(res)
        query = self.mock_db['annotations'].update_one.call_args[0][0]
        self.assertEqual(query, {"id": "ann_101", "user_id": "legitimate_owner"})

    async def test_annotation_delete_ownership_filter(self):
        """Validates that delete_annotation includes user_id in the query filter."""
        repo = AnnotationRepository(self.mock_db)
        self.mock_db['annotations'].delete_one = AsyncMock(
            return_value=MagicMock(acknowledged=True, deleted_count=1)
        )

        res = await repo.delete_annotation("ann_101", user_id="legitimate_owner")
        self.assertTrue(res)
        query = self.mock_db['annotations'].delete_one.call_args[0][0]
        self.assertEqual(query, {"id": "ann_101", "user_id": "legitimate_owner"})

    # --- 4. Requisition Analytics Empty State ---
    async def test_requisition_counts_empty_state_not_mocked(self):
        """Validates that department counts return an empty dict rather than fake fabricated counts."""
        repo = RequisitionRepository(self.mock_db)
        self.mock_db['faculty_requisitions'].aggregate = MagicMock(
            return_value=AsyncCursorMock([])
        )

        counts = await repo.get_department_requisition_counts()
        self.assertEqual(counts, {})

    # --- 5. Media Handler Path Traversal Sanitization ---
    def test_media_handler_user_id_sanitization(self):
        """Validates that malicious user_id with path traversal characters is sanitized."""
        test_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
        # User ID with path traversal attempt
        malicious_uid = "../../etc/passwd"
        success, url = save_user_avatar(malicious_uid, "avatar.png", test_png)
        self.assertTrue(success)
        # Should not contain ".." or "/" in the filename
        self.assertNotIn("..", url)
        self.assertNotIn("/etc/", url)
        self.assertIn("etcpasswd_avatar.png", url)


if __name__ == '__main__':
    unittest.main()
