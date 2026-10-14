import io
import csv
import time
import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from core.database.repositories.base_repository import BaseRepository

logger = logging.getLogger("REQUISITION_REPOSITORY")

class RequisitionRepository(BaseRepository):
    """
    Dedicated repository for Faculty Book Requisition & Curriculum Acquisition Portal.
    Complies with SRS Chapter 1 (Obj. 4), Chapter 2 (FR 4), and Form FM-LIBS-002.
    Tracks curriculum-aligned book requests with real-time procurement workflow.
    """

    VALID_STATUSES = [
        "Pending Review",
        "Approved",
        "In Procurement",
        "Available in Library",
        "Declined"
    ]

    async def create_requisition(
        self,
        faculty_id: str,
        faculty_name: str,
        email: str,
        department: str,
        book_title: str,
        author: str,
        course_code: str,
        course_title: str,
        edition_year: str = "",
        isbn: str = "",
        urgency: str = "Normal",
        justification: str = "",
        publisher: str = "",
        copyright_date: str = "",
        price: float = 0.0,
        copies: int = 1,
        college: str = ""
    ) -> Dict[str, Any]:
        """Submits a new faculty book requisition for collection acquisition (FM-LIBS-002)."""
        if self.db is None:
            return {"success": False, "error": "Database unavailable."}

        req_id = str(uuid.uuid4())
        now = time.time()

        doc = {
            "id": req_id,
            "faculty_id": str(faculty_id),
            "faculty_name": faculty_name.strip(),
            "email": email.strip().lower(),
            "department": department.strip().upper() or "CS/IT",
            "college": college.strip() or "College of Information Technology Education (CITE)",
            "book_title": book_title.strip(),
            "author": author.strip(),
            "publisher": publisher.strip(),
            "edition_year": edition_year.strip(),
            "copyright_date": copyright_date.strip(),
            "price": float(price or 0.0),
            "copies": int(copies or 1),
            "isbn": isbn.strip(),
            "course_code": course_code.strip().upper(),
            "course_title": course_title.strip(),
            "urgency": urgency.strip() or "Normal",
            "justification": justification.strip(),
            "status": "Pending Review",
            "dean_approved": False,
            "reader_services_received": False,
            "college_librarian_noted": False,
            "admin_notes": "",
            "catalog_book_id": None,
            "created_at": now,
            "updated_at": now
        }

        try:
            await self.db['faculty_requisitions'].insert_one(doc)
            return {"success": True, "requisition": self.clean_doc(doc)}
        except Exception as e:
            logger.error(f"Create Requisition Error: {e}")
            return {"success": False, "error": str(e)}

    def generate_fmlibs002_csv(self, requisitions: List[Dict[str, Any]]) -> str:
        """Generates institutional FM-LIBS-002 Book Request Form compliant export."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Republic of the Philippines"])
        writer.writerow(["NORTH EASTERN MINDANAO STATE UNIVERSITY (NEMSU) - TANDAG CAMPUS"])
        writer.writerow(["BOOK REQUEST FORM (FM-LIBS-002)"])
        writer.writerow([f"Generated: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}"])
        writer.writerow([])
        writer.writerow([
            "REQ ID", "TITLE", "AUTHOR", "EDITION", "PUBLISHER", "COPYRIGHT DATE",
            "EST. PRICE (PHP)", "COPIES", "SELECTED BY (FACULTY)", "COLLEGE / DEPT",
            "COURSE CODE", "COURSE TITLE", "STATUS", "JUSTIFICATION"
        ])
        for r in requisitions:
            writer.writerow([
                r.get("id", ""),
                r.get("book_title", ""),
                r.get("author", ""),
                r.get("edition_year", "-"),
                r.get("publisher", "-"),
                r.get("copyright_date", "-"),
                r.get("price", 0.0),
                r.get("copies", 1),
                r.get("faculty_name", ""),
                r.get("department", ""),
                r.get("course_code", ""),
                r.get("course_title", ""),
                r.get("status", "Pending Review"),
                r.get("justification", "")
            ])
        return output.getvalue()

    async def get_requisitions(
        self,
        faculty_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 150
    ) -> List[Dict[str, Any]]:
        """Queries requisitions with optional faculty ID or status filter."""
        if self.db is None: return []
        try:
            query: Dict[str, Any] = {}
            if faculty_id and faculty_id.strip():
                query["faculty_id"] = str(faculty_id).strip()
            if status and status.strip() and status.strip() != "All":
                query["status"] = status.strip()

            cursor = self.db['faculty_requisitions'].find(query).sort("created_at", -1).limit(limit)
            docs = await cursor.to_list(length=limit)
            return [self.clean_doc(d) for d in docs]
        except Exception as e:
            logger.error(f"Get Requisitions Error: {e}")
            return []

    async def update_status(
        self,
        req_id: str,
        new_status: str,
        admin_notes: str = "",
        catalog_book_id: Optional[str] = None
    ) -> bool:
        """Updates procurement status and administrative notes."""
        if self.db is None or not req_id: return False
        try:
            updates: Dict[str, Any] = {
                "status": new_status,
                "updated_at": time.time()
            }
            if admin_notes:
                updates["admin_notes"] = admin_notes.strip()
            if catalog_book_id:
                updates["catalog_book_id"] = catalog_book_id.strip()

            result = await self.db['faculty_requisitions'].update_one(
                {"id": req_id},
                {"$set": updates}
            )
            return result.modified_count > 0 or result.matched_count > 0
        except Exception as e:
            logger.error(f"Update Requisition Status Error: {e}")
            return False

    async def get_status_counts(self) -> Dict[str, int]:
        """Returns total counts grouped by requisition status."""
        if self.db is None:
            return {"Pending Review": 0, "Approved": 0, "In Procurement": 0, "Available in Library": 0, "Declined": 0}
        try:
            counts = {s: 0 for s in self.VALID_STATUSES}
            pipeline = [
                {"$group": {"_id": "$status", "count": {"$sum": 1}}}
            ]
            results = await self.db['faculty_requisitions'].aggregate(pipeline).to_list(length=20)
            for r in results:
                st = r.get("_id")
                if st in counts:
                    counts[st] = r.get("count", 0)
            return counts
        except Exception as e:
            logger.error(f"Status Counts Error: {e}")
            return {"Pending Review": 0, "Approved": 0, "In Procurement": 0, "Available in Library": 0, "Declined": 0}

    async def get_department_requisition_counts(self) -> Dict[str, int]:
        """Aggregates faculty requests by academic department."""
        if self.db is None: return {}
        try:
            pipeline = [
                {"$group": {"_id": "$department", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            results = await self.db['faculty_requisitions'].aggregate(pipeline).to_list(length=20)
            return {r["_id"] or "GENERAL": r["count"] for r in results}
        except Exception as e:
            logger.error(f"Department Requisition Counts Error: {e}")
            return {}
