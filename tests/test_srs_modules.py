import unittest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

from core.database.repositories.attendance_repository import AttendanceRepository
from core.database.repositories.requisition_repository import RequisitionRepository
from core.database.repositories.user_repository import UserRepository
from ui.pages.attendance import generate_qr_base64


class TestSRSModules(unittest.IsolatedAsyncioTestCase):
    """
    Unit test suite verifying implementation of SRS Chapters 1 & 2 requirements:
    1. QR Attendance System (Ch. 1 Obj. 3, Ch. 2 FR 3)
    2. Faculty Book Requisitions (Ch. 1 Obj. 4, Ch. 2 FR 4)
    3. Role-Based Access Control / RBAC (Ch. 2 FR 7)
    4. QR generation utility
    """

    async def test_qr_generation(self):
        """Validates that student ID generates a valid non-empty data URI."""
        data_uri = generate_qr_base64("2024-10492")
        self.assertTrue(data_uri.startswith("data:image/png;base64,") or data_uri.startswith("http"))
        self.assertGreater(len(data_uri), 100)

    async def test_attendance_checkin_and_checkout(self):
        """Validates QR scan processing logic (check-in first, check-out on second scan)."""
        repo = AttendanceRepository()
        mock_db = MagicMock()
        repo.set_db(mock_db)

        # Mock collection find_one and insert
        mock_db.__getitem__.return_value = mock_db
        mock_db.find_one = AsyncMock(side_effect=[
            None,  # user lookup
            None,  # active entry check -> none (so check-in)
            None,  # user lookup on second scan
            {      # active entry found -> check-out
                "id": "entry-123",
                "student_id": "2024-001",
                "timestamp_in": time.time() - 3600,
                "status": "Checked In"
            },
            {      # return updated entry
                "id": "entry-123",
                "student_id": "2024-001",
                "status": "Checked Out",
                "duration_minutes": 60
            }
        ])
        mock_db.insert_one = AsyncMock()
        mock_db.update_one = AsyncMock()

        # 1. First scan -> Check In
        t0 = time.time()
        res1 = await repo.record_scan(identifier="2024-001", purpose="Study / Review")
        t1 = time.time()

        self.assertTrue(res1["success"])
        self.assertEqual(res1["action"], "checkin")
        self.assertLess(t1 - t0, 1.5)  # Must be well below 1.5 seconds (NFR 1)

        # 2. Second scan -> Check Out
        res2 = await repo.record_scan(identifier="2024-001")
        self.assertTrue(res2["success"])
        self.assertEqual(res2["action"], "checkout")

    async def test_requisition_lifecycle(self):
        """Validates submission and status updates of faculty book requisitions."""
        repo = RequisitionRepository()
        mock_db = MagicMock()
        repo.set_db(mock_db)
        mock_db.__getitem__.return_value = mock_db
        mock_db.insert_one = AsyncMock()
        mock_db.update_one = AsyncMock(return_value=MagicMock(modified_count=1, matched_count=1))

        # Submit requisition
        res = await repo.create_requisition(
            faculty_id="fac-01",
            faculty_name="Prof. Loren",
            email="loren@nemsu.edu.ph",
            department="BSCS",
            book_title="Modern Artificial Intelligence",
            author="Stuart Russell",
            course_code="CS 413",
            course_title="Software Engineering 2",
            edition_year="4th Edition",
            urgency="Critical for Accreditation",
            justification="Core reference for CS 413 syllabus."
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["requisition"]["status"], "Pending Review")

        # Update status to Approved
        ok = await repo.update_status(res["requisition"]["id"], "Approved", admin_notes="Passed collection committee")
        self.assertTrue(ok)

    async def test_user_rbac_roles(self):
        """Validates user repository handling of RBAC roles (student, faculty, librarian, admin)."""
        repo = UserRepository()
        mock_db = MagicMock()
        repo.set_db(mock_db)
        mock_db.__getitem__.return_value = mock_db
        mock_db.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        # Promote to librarian
        promoted = await repo.update_user_role("user-456", "librarian")
        self.assertTrue(promoted)
        mock_db.update_one.assert_called_with({"id": "user-456"}, {"$set": {"role": "librarian"}})


if __name__ == "__main__":
    unittest.main()
