import time
import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from core.database.repositories.base_repository import BaseRepository
from core.security.rbac_policy import (
    CIRCULATION_POLICIES,
    get_circulation_policy,
    Permission,
    require_permission,
)

logger = logging.getLogger("CIRCULATION_REPOSITORY")


class CirculationRepository(BaseRepository):
    """
    Dedicated repository for Physical Book Borrowing, Circulation Desk operations,
    loan lifecycles, role-based borrowing privileges, renewals, and returns.
    """

    ROLE_BORROW_LIMITS = {
        role.value: policy.max_active_loans
        for role, policy in CIRCULATION_POLICIES.items()
    }

    ROLE_LOAN_DAYS = {
        role.value: policy.loan_duration_days
        for role, policy in CIRCULATION_POLICIES.items()
    }

    MAX_RENEWALS = 2

    async def borrow_book(
        self,
        user_id: str,
        book_id: str,
        custom_days: Optional[int] = None,
        notes: str = ""
    ) -> Dict[str, Any]:
        """
        Issues a new book loan for a user (faculty or student) enforcing role quotas.
        """
        if self.db is None:
            return {"success": False, "error": "Database connection is not available."}

        clean_uid = str(user_id).strip()
        clean_bid = str(book_id).strip()

        # 1. Verify Borrower User Account
        user = await self.db['users'].find_one({"id": clean_uid})
        if not user:
            user = await self.db['users'].find_one({"username": clean_uid})
        if not user:
            return {"success": False, "error": "Borrower account could not be found."}

        role = str(user.get("role", "student")).lower().strip()
        max_allowed = self.ROLE_BORROW_LIMITS.get(role, 3)

        # 2. Check active loans limit
        active_count = await self.db['book_loans'].count_documents({
            "user_id": user.get("id", clean_uid),
            "status": {"$in": ["active", "overdue"]}
        })
        if active_count >= max_allowed:
            return {
                "success": False,
                "error": f"Borrowing quota exceeded. {role.capitalize()} accounts can borrow up to {max_allowed} books at a time."
            }

        # 3. Check duplicate active loan for the same book
        existing_loan = await self.db['book_loans'].find_one({
            "user_id": user.get("id", clean_uid),
            "book_id": clean_bid,
            "status": {"$in": ["active", "overdue"]}
        })
        if existing_loan:
            return {
                "success": False,
                "error": "You already have an active loan for this book."
            }

        # 4. Verify Book Details
        book = await self.db['books'].find_one({"id": clean_bid})
        if not book:
            return {"success": False, "error": "Requested book does not exist in the catalog."}

        # 5. Calculate loan duration and due date
        loan_days = int(custom_days) if custom_days else self.ROLE_LOAN_DAYS.get(role, 14)
        now = time.time()
        due_timestamp = now + (loan_days * 86400)

        loan_uuid = str(uuid.uuid4())
        loan_code = f"LN-{datetime.now().strftime('%y%m%d')}-{loan_uuid[:5].upper()}"

        borrower_inst_id = (
            user.get("institutional_id")
            or user.get("student_id")
            or user.get("employee_id")
            or "N/A"
        )

        author_str = book.get("display_author") or book.get("authors") or "Unknown Author"
        if isinstance(author_str, list):
            author_str = ", ".join(author_str)

        loan_doc = {
            "id": loan_uuid,
            "loan_id": loan_code,
            "book_id": clean_bid,
            "book_title": book.get("title", "Untitled Book"),
            "book_author": str(author_str),
            "book_cover": book.get("cover_image") or book.get("cover_url") or "",
            "file_type": book.get("file_type", "epub"),
            "user_id": user.get("id", clean_uid),
            "borrower_name": user.get("name") or user.get("username", "Borrower"),
            "borrower_username": user.get("username", ""),
            "borrower_role": role,
            "institutional_id": borrower_inst_id,
            "department": user.get("department") or user.get("program") or "",
            "borrow_date": now,
            "due_date": due_timestamp,
            "loan_days": loan_days,
            "return_date": None,
            "status": "active",
            "renewal_count": 0,
            "librarian_notes": notes.strip(),
            "created_at": now,
            "updated_at": now,
        }

        try:
            await self.db['book_loans'].insert_one(loan_doc)
            return {"success": True, "loan": self.clean_doc(loan_doc)}
        except Exception as e:
            logger.error(f"Borrow Book Error: {e}")
            return {"success": False, "error": f"Failed to record book loan: {e}"}

    async def return_book(self, loan_id: str, notes: str = "") -> Dict[str, Any]:
        """
        Marks an active or overdue loan as returned.
        """
        if self.db is None:
            return {"success": False, "error": "Database unavailable."}

        clean_lid = str(loan_id).strip()
        loan = await self.db['book_loans'].find_one({
            "$or": [{"id": clean_lid}, {"loan_id": clean_lid}]
        })
        if not loan:
            return {"success": False, "error": "Loan record not found."}

        if loan.get("status") == "returned":
            return {"success": False, "error": "This book has already been returned."}

        now = time.time()
        updates = {
            "status": "returned",
            "return_date": now,
            "updated_at": now,
        }
        if notes:
            updates["librarian_notes"] = notes.strip()

        try:
            await self.db['book_loans'].update_one(
                {"_id": loan["_id"]},
                {"$set": updates}
            )
            loan.update(updates)
            return {"success": True, "loan": self.clean_doc(loan)}
        except Exception as e:
            logger.error(f"Return Book Error: {e}")
            return {"success": False, "error": f"Failed to process return: {e}"}

    async def renew_loan(self, loan_id: str, extension_days: int = 15) -> Dict[str, Any]:
        """
        Extends the due date of an active loan by extension_days (max 2 renewals).
        """
        if self.db is None:
            return {"success": False, "error": "Database unavailable."}

        clean_lid = str(loan_id).strip()
        loan = await self.db['book_loans'].find_one({
            "$or": [{"id": clean_lid}, {"loan_id": clean_lid}]
        })
        if not loan:
            return {"success": False, "error": "Loan record not found."}

        if loan.get("status") != "active":
            return {"success": False, "error": "Only active loans can be renewed."}

        current_renewals = int(loan.get("renewal_count", 0))
        if current_renewals >= self.MAX_RENEWALS:
            return {
                "success": False,
                "error": f"Maximum renewals ({self.MAX_RENEWALS}) reached for this loan."
            }

        now = time.time()
        current_due = float(loan.get("due_date", now))
        new_due = current_due + (extension_days * 86400)

        updates = {
            "due_date": new_due,
            "renewal_count": current_renewals + 1,
            "updated_at": now,
        }

        try:
            await self.db['book_loans'].update_one(
                {"_id": loan["_id"]},
                {"$set": updates}
            )
            loan.update(updates)
            return {
                "success": True,
                "new_due_date": new_due,
                "renewal_count": current_renewals + 1,
                "loan": self.clean_doc(loan)
            }
        except Exception as e:
            logger.error(f"Renew Loan Error: {e}")
            return {"success": False, "error": f"Failed to renew loan: {e}"}

    async def get_user_active_loans(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves all currently active or overdue loans for a specific user account.
        Dynamically calculates remaining days or overdue status.
        """
        if self.db is None or not user_id:
            return []

        clean_uid = str(user_id).strip()
        cursor = self.db['book_loans'].find({
            "user_id": clean_uid,
            "status": {"$in": ["active", "overdue"]}
        }).sort("due_date", 1)

        docs = await cursor.to_list(length=50)
        now = time.time()
        results = []

        for d in docs:
            due = float(d.get("due_date", now))
            seconds_remaining = due - now
            days_remaining = int(seconds_remaining // 86400)
            is_overdue = seconds_remaining < 0

            # Auto-update status if overdue
            if is_overdue and d.get("status") == "active":
                d["status"] = "overdue"
                try:
                    await self.db['book_loans'].update_one(
                        {"_id": d["_id"]},
                        {"$set": {"status": "overdue", "updated_at": now}}
                    )
                except Exception:
                    pass

            d["days_remaining"] = days_remaining
            d["is_overdue"] = is_overdue
            results.append(self.clean_doc(d))

        return results

    async def get_user_loan_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves complete borrowing history for a user (active, returned, overdue)."""
        if self.db is None or not user_id:
            return []
        clean_uid = str(user_id).strip()
        cursor = self.db['book_loans'].find({"user_id": clean_uid}).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return self.clean_docs(docs)

    async def get_all_loans(
        self,
        status: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 150
    ) -> List[Dict[str, Any]]:
        """Queries circulation records for the Librarian Console."""
        if self.db is None:
            return []
        query: Dict[str, Any] = {}
        if status and status.strip() and status != "All":
            query["status"] = status.strip()
        if role and role.strip() and role != "All":
            query["borrower_role"] = role.strip().lower()

        cursor = self.db['book_loans'].find(query).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        now = time.time()
        results = []
        for d in docs:
            due = float(d.get("due_date", now))
            seconds_remaining = due - now
            d["days_remaining"] = int(seconds_remaining // 86400)
            d["is_overdue"] = seconds_remaining < 0 and d.get("status") != "returned"
            results.append(self.clean_doc(d))
        return results

    async def get_circulation_stats(self) -> Dict[str, Any]:
        """Provides operational metrics for circulation desks and accreditation dashboards."""
        if self.db is None:
            return {
                "active_loans": 0,
                "returned_loans": 0,
                "overdue_loans": 0,
                "faculty_loans": 0,
                "student_loans": 0,
                "total_loans": 0
            }
        try:
            import asyncio
            active_q = {"status": "active"}
            returned_q = {"status": "returned"}
            overdue_q = {"status": "overdue"}
            faculty_q = {"borrower_role": "faculty"}
            student_q = {"borrower_role": "student"}

            (
                active_count,
                returned_count,
                overdue_count,
                faculty_count,
                student_count,
                total_count
            ) = await asyncio.gather(
                self.db['book_loans'].count_documents(active_q),
                self.db['book_loans'].count_documents(returned_q),
                self.db['book_loans'].count_documents(overdue_q),
                self.db['book_loans'].count_documents(faculty_q),
                self.db['book_loans'].count_documents(student_q),
                self.db['book_loans'].count_documents({}),
            )

            return {
                "active_loans": active_count,
                "returned_loans": returned_count,
                "overdue_loans": overdue_count,
                "faculty_loans": faculty_count,
                "student_loans": student_count,
                "total_loans": total_count
            }
        except Exception as e:
            logger.error(f"Circulation Stats Error: {e}")
            return {
                "active_loans": 0,
                "returned_loans": 0,
                "overdue_loans": 0,
                "faculty_loans": 0,
                "student_loans": 0,
                "total_loans": 0
            }
