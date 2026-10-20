from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, ReturnDocument

from core.security.rbac_policy import (
    Permission,
    UserRole,
    get_circulation_policy,
    require_permission,
)

PHT_TZ = timezone(timedelta(hours=8))

VALID_REQUISITION_STATUSES = (
    "Pending Review",
    "Approved / In Acquisition",
    "Rejected",
)

VALID_PRIORITIES = ("High (Core Syllabus)", "Medium (Reference)", "Standard")


class LibraryOperationsRepository:
    """
    Unified repository enforcing role-based circulation limits, renewals,
    curricular textbook requisitions (Form FM-LIBS-002), catalog management,
    and Admin RBAC governance.
    """

    def __init__(self, db) -> None:
        self.db = db
        if db is not None:
            self.users = db["users"]
            self.books = db["books"]
            self.loans = db["loans"]
            self.requisitions = db["requisitions"]
            self.counters = db["counters"]
        else:
            self.users = None
            self.books = None
            self.loans = None
            self.requisitions = None
            self.counters = None

    async def ensure_indexes(self) -> None:
        if self.loans is not None:
            await self.loans.create_index(
                [("user_id", ASCENDING), ("status", ASCENDING)],
                name="idx_user_active_loans",
            )
            await self.loans.create_index(
                [("status", ASCENDING), ("due_at", ASCENDING)],
                name="idx_circulation_desk_due",
            )
        if self.requisitions is not None:
            await self.requisitions.create_index(
                [("status", ASCENDING), ("created_at", DESCENDING)],
                name="idx_fm_libs_002_queue",
            )
            await self.requisitions.create_index(
                [("requester_id", ASCENDING), ("created_at", DESCENDING)],
                name="idx_faculty_requisitions",
            )

    @staticmethod
    def _now_pht(override_now: Optional[datetime] = None) -> datetime:
        if override_now is not None:
            if override_now.tzinfo is None:
                return override_now.replace(tzinfo=PHT_TZ)
            return override_now.astimezone(PHT_TZ)
        return datetime.now(PHT_TZ)

    # =========================================================================
    # 1. PHYSICAL CIRCULATION, QUOTAS & LOAN RENEWALS
    # =========================================================================
    async def borrow_book(
        self,
        borrower_doc: Dict[str, Any],
        book_id: Any,
        now_override: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Issues a physical book loan enforcing the borrower's role policy:
        - Student: max 3 active loans, 7-day duration
        - Faculty: max 10 active loans, 30-day duration
        """
        require_permission(borrower_doc, Permission.BORROW_BOOKS)
        policy = get_circulation_policy(borrower_doc)

        user_id = str(borrower_doc.get("_id") or borrower_doc.get("id"))
        inst_id = borrower_doc.get("institutional_id") or borrower_doc.get("student_id") or "N/A"
        full_name = borrower_doc.get("full_name") or borrower_doc.get("username") or "Borrower"

        active_count = await self.loans.count_documents(
            {"user_id": user_id, "status": {"$in": ["Active", "Overdue"]}}
        )
        if active_count >= policy.max_active_loans:
            raise ValueError(
                f"Loan limit reached for {policy.display_label}: You currently have "
                f"{active_count}/{policy.max_active_loans} active borrowed books."
            )

        str_bid = str(book_id)
        if ObjectId.is_valid(str_bid):
            book_query = {"$or": [{"_id": ObjectId(str_bid)}, {"_id": book_id}, {"id": book_id}]}
        else:
            book_query = {"$or": [{"_id": book_id}, {"id": book_id}]}

        book = await self.books.find_one(book_query)
        if not book:
            raise ValueError("Requested book was not found in the catalog.")

        available_copies = int(book.get("available_copies", 1))
        if available_copies <= 0:
            raise ValueError(f"'{book.get('title', 'Book')}' currently has 0 available physical copies.")

        now = self._now_pht(now_override)
        due_at = now + timedelta(days=policy.loan_duration_days)

        loan_doc: Dict[str, Any] = {
            "user_id": user_id,
            "institutional_id": inst_id,
            "borrower_name": full_name,
            "borrower_role": policy.role.value,
            "book_id": str(book.get("_id") or book.get("id")),
            "book_title": book.get("title", "Untitled"),
            "book_author": book.get("author") or book.get("display_author") or "Unknown Author",
            "borrowed_at": now,
            "due_at": due_at,
            "returned_at": None,
            "renewal_count": 0,
            "max_renewals": policy.max_renewals_per_loan,
            "renewal_window_days": policy.renewal_extension_days,
            "status": "Active",
        }

        await self.books.update_one(
            {"_id": book["_id"]},
            {"$inc": {"available_copies": -1}},
        )
        res = await self.loans.insert_one(loan_doc)
        loan_doc["_id"] = res.inserted_id
        return loan_doc

    async def renew_loan(
        self,
        actor_doc: Dict[str, Any],
        loan_id: Any,
        now_override: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Extends a loan's due date:
        - Student self-renewal: +7 days
        - Faculty self-renewal: +15 days
        - Librarian / Admin override: +15 days (or borrower's role window) even if previously renewed
        """
        require_permission(actor_doc, Permission.RENEW_OWN_LOAN)
        actor_policy = get_circulation_policy(actor_doc)
        actor_id = str(actor_doc.get("_id") or actor_doc.get("id"))

        str_lid = str(loan_id)
        if ObjectId.is_valid(str_lid):
            loan_query = {"$or": [{"_id": ObjectId(str_lid)}, {"_id": loan_id}, {"id": loan_id}]}
        else:
            loan_query = {"$or": [{"_id": loan_id}, {"id": loan_id}]}

        loan = await self.loans.find_one(loan_query)
        if not loan:
            raise ValueError("Loan record not found.")

        if loan.get("status") == "Returned":
            raise ValueError("Cannot renew a book that has already been returned.")

        is_owner = str(loan.get("user_id")) == actor_id
        if not is_owner and not actor_policy.can_override_loans:
            raise PermissionError("You can only renew your own active loans.")

        now = self._now_pht(now_override)
        current_due = loan["due_at"]
        if current_due.tzinfo is None:
            current_due = current_due.replace(tzinfo=timezone.utc).astimezone(PHT_TZ)

        if not actor_policy.can_override_loans:
            if now > current_due or loan.get("status") == "Overdue":
                raise ValueError(
                    "Overdue loans cannot be self-renewed. Please see a Librarian at the Circulation Desk."
                )
            if int(loan.get("renewal_count", 0)) >= int(loan.get("max_renewals", 1)):
                raise ValueError(
                    f"Maximum renewal limit ({loan.get('max_renewals', 1)}) reached for this loan."
                )

        borrower_policy = get_circulation_policy(loan.get("borrower_role", "student"))
        extension_days = borrower_policy.renewal_extension_days
        base_date = max(current_due, now)
        new_due_at = base_date + timedelta(days=extension_days)

        updated_loan = await self.loans.find_one_and_update(
            {"_id": loan["_id"]},
            {
                "$set": {
                    "due_at": new_due_at,
                    "status": "Active",
                    "last_renewed_at": now,
                    "last_renewed_by_role": actor_policy.role.value,
                },
                "$inc": {"renewal_count": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if updated_loan:
            for field in ("due_at", "borrowed_at", "returned_at", "last_renewed_at"):
                val = updated_loan.get(field)
                if isinstance(val, datetime) and val.tzinfo is None:
                    updated_loan[field] = val.replace(tzinfo=timezone.utc).astimezone(PHT_TZ)
        return updated_loan

    async def checkin_return_loan(
        self,
        operator_doc: Dict[str, Any],
        loan_id: Any,
        now_override: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        1-Click Circulation Desk Check-In Return (Restricted to Librarian and Admin).
        """
        require_permission(operator_doc, Permission.OPERATE_CIRCULATION_DESK)
        now = self._now_pht(now_override)

        str_lid = str(loan_id)
        if ObjectId.is_valid(str_lid):
            loan_query = {"$or": [{"_id": ObjectId(str_lid)}, {"_id": loan_id}, {"id": loan_id}]}
        else:
            loan_query = {"$or": [{"_id": loan_id}, {"id": loan_id}]}

        loan = await self.loans.find_one(loan_query)
        if not loan:
            raise ValueError("Loan record not found.")
        if loan.get("status") == "Returned":
            return loan

        updated_loan = await self.loans.find_one_and_update(
            {"_id": loan["_id"]},
            {
                "$set": {
                    "status": "Returned",
                    "returned_at": now,
                    "returned_by": operator_doc.get("institutional_id")
                    or operator_doc.get("username")
                    or "Staff",
                }
            },
            return_document=ReturnDocument.AFTER,
        )

        # Restore physical book copy availability
        book_id = loan.get("book_id")
        if book_id:
            str_bid = str(book_id)
            if ObjectId.is_valid(str_bid):
                b_query = {"$or": [{"_id": ObjectId(str_bid)}, {"_id": book_id}, {"id": book_id}]}
            else:
                b_query = {"$or": [{"_id": book_id}, {"id": book_id}]}
            await self.books.update_one(b_query, {"$inc": {"available_copies": 1}})

        return updated_loan

    async def list_active_loans(
        self,
        user_id: Optional[str] = None,
        now_override: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lists active loans and automatically flags any loan past its `due_at` timestamp as 'Overdue'.
        """
        now = self._now_pht(now_override)
        query: Dict[str, Any] = {"status": {"$in": ["Active", "Overdue"]}}
        if user_id:
            query["user_id"] = str(user_id)

        cursor = self.loans.find(query).sort("due_at", ASCENDING)
        results: List[Dict[str, Any]] = []
        async for doc in cursor:
            due_at = doc.get("due_at")
            if due_at:
                if due_at.tzinfo is None:
                    due_at = due_at.replace(tzinfo=timezone.utc).astimezone(PHT_TZ)
                    doc["due_at"] = due_at
                if now > due_at and doc.get("status") != "Overdue":
                    doc["status"] = "Overdue"
                    await self.loans.update_one(
                        {"_id": doc["_id"]}, {"$set": {"status": "Overdue"}}
                    )
            results.append(doc)
        return results

    # =========================================================================
    # 2. CURRICULAR BOOK REQUISITIONS (FORM FM-LIBS-002)
    # =========================================================================
    async def submit_requisition(
        self,
        faculty_doc: Dict[str, Any],
        course_code: str,
        title: str,
        author: str,
        edition: str = "Latest",
        isbn: str = "",
        priority: str = "High (Core Syllabus)",
        justification: str = "",
        copies_requested: int = 3,
        now_override: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Submits a formal Curricular Book Requisition (Form FM-LIBS-002).
        Strictly permitted for Faculty and Admin roles.
        """
        require_permission(faculty_doc, Permission.SUBMIT_REQUISITION_FM_LIBS_002)

        if not course_code.strip() or not title.strip() or not author.strip():
            raise ValueError("Course Code, Book Title, and Author are required for Form FM-LIBS-002.")
        if not justification.strip() or len(justification.strip()) < 10:
            raise ValueError(
                "Please provide an academic syllabus justification (at least 10 characters)."
            )

        now = self._now_pht(now_override)
        year_str = now.strftime("%Y")

        counter_doc = await self.counters.find_one_and_update(
            {"_id": f"req_seq_{year_str}"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        req_code = f"FM-LIBS-002-{year_str}-{counter_doc['seq']:04d}"

        req_doc: Dict[str, Any] = {
            "requisition_code": req_code,
            "requester_id": str(faculty_doc.get("_id") or faculty_doc.get("id")),
            "requester_inst_id": faculty_doc.get("institutional_id") or "N/A",
            "requester_name": faculty_doc.get("full_name") or faculty_doc.get("username"),
            "department": (
                faculty_doc.get("department")
                or faculty_doc.get("program")
                or "GENERAL"
            ).upper(),
            "course_code": course_code.strip().upper(),
            "title": title.strip(),
            "author": author.strip(),
            "edition": edition.strip() or "Latest",
            "isbn": isbn.strip() or "N/A",
            "priority": priority if priority in VALID_PRIORITIES else "Standard",
            "copies_requested": max(1, int(copies_requested)),
            "justification": justification.strip(),
            "status": "Pending Review",
            "review_notes": "",
            "reviewed_by": None,
            "reviewed_at": None,
            "created_at": now,
        }

        res = await self.requisitions.insert_one(req_doc)
        req_doc["_id"] = res.inserted_id
        return req_doc

    async def review_requisition(
        self,
        reviewer_doc: Dict[str, Any],
        requisition_id: Any,
        new_status: str,
        review_notes: str = "",
        now_override: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Reviews, approves, or rejects a Faculty Requisition (Form FM-LIBS-002).
        Strictly permitted for Librarian and Admin roles.
        """
        require_permission(reviewer_doc, Permission.REVIEW_REQUISITION_FM_LIBS_002)

        if new_status not in VALID_REQUISITION_STATUSES:
            raise ValueError(
                f"Invalid requisition status '{new_status}'. Expected one of {VALID_REQUISITION_STATUSES}."
            )

        now = self._now_pht(now_override)
        str_req_id = str(requisition_id)
        if ObjectId.is_valid(str_req_id):
            req_query = {"$or": [{"_id": ObjectId(str_req_id)}, {"_id": requisition_id}, {"id": requisition_id}]}
        else:
            req_query = {"$or": [{"_id": requisition_id}, {"id": requisition_id}]}

        updated = await self.requisitions.find_one_and_update(
            req_query,
            {
                "$set": {
                    "status": new_status,
                    "review_notes": review_notes.strip(),
                    "reviewed_by": reviewer_doc.get("full_name")
                    or reviewer_doc.get("username")
                    or "Librarian",
                    "reviewed_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            raise ValueError("Requisition record not found.")
        return updated

    async def list_requisitions(
        self,
        requester_id: Optional[str] = None,
        status_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if requester_id:
            query["requester_id"] = str(requester_id)
        if status_filter and status_filter != "All":
            query["status"] = status_filter

        cursor = self.requisitions.find(query).sort("created_at", DESCENDING)
        items: List[Dict[str, Any]] = []
        async for doc in cursor:
            items.append(doc)
        return items

    # =========================================================================
    # 3. CATALOG PURGING & COLLECTION FORMAT ANALYTICS (LIBRARIAN / ADMIN)
    # =========================================================================
    async def purge_catalog_book(
        self, operator_doc: Dict[str, Any], book_id: Any
    ) -> bool:
        """Purges a damaged or obsolete volume from the catalog (Librarian/Admin only)."""
        require_permission(operator_doc, Permission.PURGE_CATALOG_TITLES)
        str_bid = str(book_id)
        if ObjectId.is_valid(str_bid):
            b_query = {"$or": [{"_id": ObjectId(str_bid)}, {"_id": book_id}, {"id": book_id}]}
        else:
            b_query = {"$or": [{"_id": book_id}, {"id": book_id}]}
        res = await self.books.delete_one(b_query)
        return res.deleted_count > 0

    async def get_collection_format_analytics(self) -> Dict[str, int]:
        """Computes EPUB reflowable vs. fixed PDF distribution for the Librarian Console."""
        epub_count = await self.books.count_documents(
            {"$or": [{"format": "EPUB"}, {"file_type": "epub"}, {"local_path": {"$regex": r"\.epub$", "$options": "i"}}]}
        )
        pdf_count = await self.books.count_documents(
            {"$or": [{"format": "PDF"}, {"file_type": "pdf"}, {"local_path": {"$regex": r"\.pdf$", "$options": "i"}}]}
        )
        total = await self.books.count_documents({})
        other_count = max(0, total - (epub_count + pdf_count))
        return {
            "total_volumes": total,
            "epub_reflowable": epub_count,
            "pdf_fixed": pdf_count,
            "other_formats": other_count,
        }

    # =========================================================================
    # 4. ADMIN RBAC USER GOVERNANCE (ADMIN ONLY)
    # =========================================================================
    async def update_user_role(
        self,
        admin_doc: Dict[str, Any],
        target_user_id: Any,
        new_role: str,
    ) -> Dict[str, Any]:
        """
        Promotes or demotes a user account across ('student', 'faculty', 'librarian', 'admin').
        Strictly restricted to System Administrators.
        """
        require_permission(admin_doc, Permission.MANAGE_RBAC_USERS)

        normalized_role = UserRole.normalize(new_role)
        if normalized_role.value != new_role.strip().lower():
            raise ValueError(f"Invalid role '{new_role}'.")

        str_uid = str(target_user_id)
        if ObjectId.is_valid(str_uid):
            u_query = {"$or": [{"_id": ObjectId(str_uid)}, {"_id": target_user_id}, {"id": target_user_id}]}
        else:
            u_query = {"$or": [{"_id": target_user_id}, {"id": target_user_id}]}

        updated_user = await self.users.find_one_and_update(
            u_query,
            {
                "$set": {
                    "role": normalized_role.value,
                    "role_updated_at": self._now_pht(),
                    "role_updated_by": admin_doc.get("institutional_id")
                    or admin_doc.get("username"),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not updated_user:
            raise ValueError("Target user account not found.")
        return updated_user
