import unittest
from datetime import datetime
import uuid

from core.database.mongo_manager import mongo_db
from core.database.repositories.operations_repository import (
    PHT_TZ,
    LibraryOperationsRepository,
)
from core.security.rbac_policy import (
    Permission,
    UserRole,
    get_circulation_policy,
    has_permission,
    can_operate_attendance_scanner,
    require_scanner_authority,
)


class TestRBACAndOperations(unittest.IsolatedAsyncioTestCase):
    """
    Automated test suite verifying the authoritative Role & Permission Matrix,
    Student vs. Faculty circulation quotas, Form FM-LIBS-002 requisition lifecycle,
    and Admin-only RBAC governance.
    """

    async def asyncSetUp(self):
        await mongo_db.initialize()
        self.repo = mongo_db.operations
        self.prefix = f"test_rbac_{uuid.uuid4().hex[:6]}"
        self.test_user_ids = []
        self.test_book_ids = []
        self.test_loan_ids = []
        self.test_req_ids = []

        import random
        base_num = random.randint(10000, 80000)

        # Seed users representing all 4 institutional tiers with collision-free unique IDs and emails
        self.student = {
            "_id": f"{self.prefix}_stud_1",
            "id": f"{self.prefix}_stud_1",
            "institutional_id": f"99-{base_num + 1:05d}",
            "student_id": f"99-{base_num + 1:05d}",
            "full_name": "Student Borrower",
            "username": f"{self.prefix}_stud_1",
            "email": f"{self.prefix}_stud@test.edu",
            "role": "student",
            "department": "BSCS",
        }
        self.faculty = {
            "_id": f"{self.prefix}_fac_1",
            "id": f"{self.prefix}_fac_1",
            "institutional_id": f"99-{base_num + 2:05d}",
            "full_name": "Prof. Maria Santos",
            "username": f"{self.prefix}_fac_1",
            "email": f"{self.prefix}_fac@test.edu",
            "role": "faculty",
            "department": "BSCS",
        }
        self.librarian = {
            "_id": f"{self.prefix}_lib_1",
            "id": f"{self.prefix}_lib_1",
            "institutional_id": f"99-{base_num + 3:05d}",
            "full_name": "Chief Librarian",
            "username": f"{self.prefix}_lib_1",
            "email": f"{self.prefix}_lib@test.edu",
            "role": "librarian",
            "department": "LIBRARY",
        }
        self.admin = {
            "_id": f"{self.prefix}_adm_1",
            "id": f"{self.prefix}_adm_1",
            "institutional_id": f"99-{base_num + 4:05d}",
            "full_name": "Root Admin",
            "username": f"{self.prefix}_adm_1",
            "email": f"{self.prefix}_adm@test.edu",
            "role": "admin",
            "department": "IT",
        }

        for u in (self.student, self.faculty, self.librarian, self.admin):
            self.test_user_ids.append(u["_id"])
            await mongo_db.db["users"].replace_one({"_id": u["_id"]}, u, upsert=True)

        # Seed 15 test physical books
        self.books = []
        for i in range(1, 16):
            bid = f"{self.prefix}_book_{i}"
            self.test_book_ids.append(bid)
            bdoc = {
                "_id": bid,
                "id": bid,
                "title": f"Computer Science Volume {i}",
                "author": "ACM Press",
                "format": "EPUB" if i % 2 == 0 else "PDF",
                "available_copies": 5,
            }
            self.books.append(bdoc)
            await mongo_db.db["books"].replace_one({"_id": bid}, bdoc, upsert=True)

    async def asyncTearDown(self):
        if mongo_db.db is not None:
            if self.test_user_ids:
                await mongo_db.db["users"].delete_many({"_id": {"$in": self.test_user_ids}})
            if self.test_book_ids:
                await mongo_db.db["books"].delete_many({"_id": {"$in": self.test_book_ids}})
            if self.test_loan_ids:
                await mongo_db.db["loans"].delete_many({"$or": [
                    {"_id": {"$in": self.test_loan_ids}},
                    {"user_id": {"$in": self.test_user_ids}},
                ]})
            if self.test_req_ids:
                await mongo_db.db["requisitions"].delete_many({"$or": [
                    {"_id": {"$in": self.test_req_ids}},
                    {"requester_id": {"$in": self.test_user_ids}},
                ]})

    # =========================================================================
    # 1. Permission Matrix Verification
    # =========================================================================
    def test_permission_matrix_matches_institutional_specification(self):
        # Student permissions (Entrance Fast Scanner authority strictly removed)
        self.assertTrue(has_permission("student", Permission.BORROW_BOOKS))
        self.assertTrue(has_permission("student", Permission.RENEW_OWN_LOAN))
        self.assertFalse(has_permission("student", Permission.SCAN_ATTENDANCE_PASS))
        self.assertFalse(has_permission("student", Permission.OPERATE_GATE_TERMINAL))
        self.assertTrue(has_permission("student", Permission.READ_OPDS_FEED))
        self.assertTrue(has_permission("student", Permission.USE_TARS_AI_WORKSTATION))
        self.assertFalse(has_permission("student", Permission.SUBMIT_REQUISITION_FM_LIBS_002))
        self.assertFalse(has_permission("student", Permission.OPERATE_CIRCULATION_DESK))
        self.assertFalse(has_permission("student", Permission.MANAGE_RBAC_USERS))
        self.assertFalse(has_permission("student", Permission.VIEW_LIVE_DOORWAY_STREAM))

        # Faculty permissions (Entrance Fast Scanner authority strictly removed)
        self.assertTrue(has_permission("faculty", Permission.BORROW_BOOKS))
        self.assertTrue(has_permission("faculty", Permission.RENEW_OWN_LOAN))
        self.assertFalse(has_permission("faculty", Permission.SCAN_ATTENDANCE_PASS))
        self.assertFalse(has_permission("faculty", Permission.OPERATE_GATE_TERMINAL))
        self.assertTrue(has_permission("faculty", Permission.SUBMIT_REQUISITION_FM_LIBS_002))
        self.assertTrue(has_permission("faculty", Permission.VIEW_CURRICULAR_ANALYTICS))
        self.assertFalse(has_permission("faculty", Permission.REVIEW_REQUISITION_FM_LIBS_002))
        self.assertFalse(has_permission("faculty", Permission.OPERATE_CIRCULATION_DESK))
        self.assertFalse(has_permission("faculty", Permission.VIEW_LIVE_DOORWAY_STREAM))

        # Librarian permissions (Authorized to operate gate terminal & scan attendance passes)
        self.assertTrue(has_permission("librarian", Permission.OPERATE_CIRCULATION_DESK))
        self.assertTrue(has_permission("librarian", Permission.REVIEW_REQUISITION_FM_LIBS_002))
        self.assertTrue(has_permission("librarian", Permission.VIEW_EXPORT_FM_LIBS_009))
        self.assertTrue(has_permission("librarian", Permission.PURGE_CATALOG_TITLES))
        self.assertTrue(has_permission("librarian", Permission.SCAN_ATTENDANCE_PASS))
        self.assertTrue(has_permission("librarian", Permission.OPERATE_GATE_TERMINAL))
        self.assertFalse(has_permission("librarian", Permission.MANAGE_RBAC_USERS))
        self.assertFalse(has_permission("librarian", Permission.MANAGE_CHROMADB_VECTORS))
        self.assertFalse(has_permission("librarian", Permission.VIEW_LIVE_DOORWAY_STREAM))

        # Admin universal permissions across all tiers (including gate terminal & live doorway)
        self.assertTrue(has_permission("admin", Permission.VIEW_LIVE_DOORWAY_STREAM))
        self.assertTrue(has_permission("admin", Permission.SCAN_ATTENDANCE_PASS))
        self.assertTrue(has_permission("admin", Permission.OPERATE_GATE_TERMINAL))
        for perm in Permission:
            self.assertTrue(has_permission("admin", perm), f"Admin missing permission {perm}")

    # =========================================================================
    # 1b. Entrance Fast Scanner Authority RBAC Enforcement
    # =========================================================================
    async def test_entrance_fast_scanner_authority_enforcement(self):
        """Verifies students and faculty cannot operate scanner, while librarian and admin succeed."""
        # 1. Authority boolean check
        self.assertFalse(can_operate_attendance_scanner("student"))
        self.assertFalse(can_operate_attendance_scanner(self.student))
        self.assertFalse(can_operate_attendance_scanner("faculty"))
        self.assertFalse(can_operate_attendance_scanner(self.faculty))
        self.assertTrue(can_operate_attendance_scanner("librarian"))
        self.assertTrue(can_operate_attendance_scanner(self.librarian))
        self.assertTrue(can_operate_attendance_scanner("admin"))
        self.assertTrue(can_operate_attendance_scanner(self.admin))

        # 2. Server-side assertion guard
        with self.assertRaises(PermissionError):
            require_scanner_authority("student")
        with self.assertRaises(PermissionError):
            require_scanner_authority("faculty")
        require_scanner_authority("librarian")  # Should not raise
        require_scanner_authority("admin")      # Should not raise

        # 3. Backend scan execution enforcement
        test_inst_id = self.student.get("institutional_id", "23-00128")

        # Student operator is rejected
        res_student = await mongo_db.record_attendance_scan(
            identifier=test_inst_id,
            operator_role="student",
            operator_id=str(self.student["_id"]),
        )
        self.assertFalse(res_student.get("success"))
        self.assertIn("Access Denied", res_student.get("error", ""))

        # Faculty operator is rejected
        res_faculty = await mongo_db.record_attendance_scan(
            identifier=test_inst_id,
            operator_role="faculty",
            operator_id=str(self.faculty["_id"]),
        )
        self.assertFalse(res_faculty.get("success"))
        self.assertIn("Access Denied", res_faculty.get("error", ""))

        # Librarian operator succeeds
        res_librarian = await mongo_db.record_attendance_scan(
            identifier=test_inst_id,
            operator_role="librarian",
            operator_id=str(self.librarian["_id"]),
        )
        self.assertTrue(res_librarian.get("success"))
        self.assertIn(res_librarian.get("action"), ("checkin", "cooldown"))

        # Clean up any attendance logs created during this test
        await mongo_db.db["attendance_logs"].delete_many({"institutional_id": test_inst_id})

    # =========================================================================
    # 2. Student vs. Faculty Circulation Quotas & Renewal Windows
    # =========================================================================
    async def test_student_3_books_7_days_and_faculty_10_books_30_days(self):
        t0 = datetime(2026, 10, 21, 9, 0, 0, tzinfo=PHT_TZ)

        # Student borrows 3 books (7-day loan duration)
        for i in range(1, 4):
            loan = await self.repo.borrow_book(self.student, f"{self.prefix}_book_{i}", now_override=t0)
            self.test_loan_ids.append(loan["_id"])
            self.assertEqual((loan["due_at"] - t0).days, 7)

        # 4th book for Student must be blocked (quota is 3)
        with self.assertRaises(ValueError) as ctx_stud:
            await self.repo.borrow_book(self.student, f"{self.prefix}_book_4", now_override=t0)
        self.assertIn("3/3", str(ctx_stud.exception))

        # Student renewal adds +7 days (7 + 7 = 14 days from t0)
        student_loans = await self.repo.list_active_loans(user_id=self.student["_id"], now_override=t0)
        renewed_s = await self.repo.renew_loan(self.student, student_loans[0]["_id"], now_override=t0)
        self.assertEqual((renewed_s["due_at"] - t0).days, 14)

        # Student second renewal must be blocked (max_renewals = 1)
        with self.assertRaises(ValueError) as ctx_ren:
            await self.repo.renew_loan(self.student, student_loans[0]["_id"], now_override=t0)
        self.assertIn("Maximum renewal limit", str(ctx_ren.exception))

        # Faculty borrows up to 10 books (30-day loan duration)
        for i in range(1, 11):
            f_loan = await self.repo.borrow_book(self.faculty, f"{self.prefix}_book_{i}", now_override=t0)
            self.test_loan_ids.append(f_loan["_id"])
            self.assertEqual((f_loan["due_at"] - t0).days, 30)

        # 11th book for Faculty must be blocked (quota is 10)
        with self.assertRaises(ValueError) as ctx_fac:
            await self.repo.borrow_book(self.faculty, f"{self.prefix}_book_11", now_override=t0)
        self.assertIn("10/10", str(ctx_fac.exception))

        # Faculty renewal adds +15 days (30 + 15 = 45 days from t0)
        faculty_loans = await self.repo.list_active_loans(user_id=self.faculty["_id"], now_override=t0)
        renewed_f = await self.repo.renew_loan(self.faculty, faculty_loans[0]["_id"], now_override=t0)
        self.assertEqual((renewed_f["due_at"] - t0).days, 45)

        # Librarian checks in a returned book at the Circulation Desk
        returned = await self.repo.checkin_return_loan(self.librarian, faculty_loans[0]["_id"], now_override=t0)
        self.assertEqual(returned["status"], "Returned")

    # =========================================================================
    # 3. Form FM-LIBS-002 Requisition Submission & Librarian Review Workflow
    # =========================================================================
    async def test_fm_libs_002_requisition_lifecycle(self):
        # Students cannot submit Form FM-LIBS-002 requisitions
        with self.assertRaises(PermissionError):
            await self.repo.submit_requisition(
                self.student,
                course_code="CS 101",
                title="Intro to Algorithms",
                author="Cormen",
                justification="Needed for freshman algorithms study.",
            )

        # Faculty submits Form FM-LIBS-002 requisition
        req = await self.repo.submit_requisition(
            self.faculty,
            course_code="CS 402",
            title="Artificial Intelligence: A Modern Approach",
            author="Stuart Russell, Peter Norvig",
            edition="4th Edition",
            priority="High (Core Syllabus)",
            justification="Core reference textbook required for senior CS thesis and AI coursework.",
            copies_requested=5,
        )
        self.test_req_ids.append(req["_id"])
        self.assertEqual(req["status"], "Pending Review")
        self.assertTrue(req["requisition_code"].startswith("FM-LIBS-002-"))

        # Faculty cannot approve their own requisition
        with self.assertRaises(PermissionError):
            await self.repo.review_requisition(
                self.faculty, req["_id"], "Approved / In Acquisition", "Self-approved"
            )

        # Librarian reviews and approves the requisition with official committee notes
        reviewed = await self.repo.review_requisition(
            self.librarian,
            req["_id"],
            new_status="Approved / In Acquisition",
            review_notes="Approved by Library Committee; queued for Q4 procurement.",
        )
        self.assertEqual(reviewed["status"], "Approved / In Acquisition")
        self.assertIn("queued for Q4 procurement", reviewed["review_notes"])

    # =========================================================================
    # 4. Admin-Only RBAC Governance Verification
    # =========================================================================
    async def test_only_admin_can_modify_user_roles(self):
        # Librarian cannot modify user roles
        with self.assertRaises(PermissionError):
            await self.repo.update_user_role(self.librarian, self.student["_id"], "faculty")

        # Admin promotes Student -> Faculty
        promoted = await self.repo.update_user_role(self.admin, self.student["_id"], "faculty")
        self.assertEqual(promoted["role"], "faculty")
        self.assertEqual(get_circulation_policy(promoted).max_active_loans, 10)

        # Invalid role should raise ValueError
        with self.assertRaises(ValueError):
            await self.repo.update_user_role(self.admin, self.student["_id"], "superman")


if __name__ == "__main__":
    unittest.main()
