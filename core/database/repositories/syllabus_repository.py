from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger("SYLLABUS_REPO")


class SyllabusRepository:
    """
    Manages course-syllabus mappings, book-to-course associations,
    and Form FM-LIBS-002 curricular textbook alignments.
    """

    def __init__(self, db=None) -> None:
        self.db = db
        self.books = db["books"] if db is not None else None
        self.requisitions = db["requisitions"] if db is not None else None

    def set_db(self, db) -> None:
        self.db = db
        self.books = db["books"] if db is not None else None
        self.requisitions = db["requisitions"] if db is not None else None

    async def sync_approved_requisitions_to_books(self) -> int:
        """
        Synchronizes approved faculty book requisitions (Form FM-LIBS-002)
        by attaching approved course codes to corresponding catalog books.
        """
        if self.requisitions is None or self.books is None:
            return 0

        cursor = self.requisitions.find(
            {"status": "Approved / In Acquisition"},
            {"course_code": 1, "title": 1, "isbn": 1, "department": 1, "course_title": 1},
        )
        synced_count = 0
        async for req in cursor:
            course_code = (req.get("course_code") or "").strip().upper()
            title = (req.get("title") or "").strip()
            isbn = (req.get("isbn") or "").strip()
            dept = (req.get("department") or "").strip().upper()
            c_title = (req.get("course_title") or "").strip()
            if not course_code or not title:
                continue

            match_clauses = [{"title": {"$regex": f"^{title}$", "$options": "i"}}]
            if isbn and isbn != "N/A":
                match_clauses.append({"isbn": isbn})

            update_doc: Dict[str, Any] = {
                "$addToSet": {"course_codes": course_code},
            }
            sets: Dict[str, Any] = {}
            if dept:
                sets["program"] = dept
            if c_title:
                sets[f"course_titles.{course_code}"] = c_title
            if sets:
                update_doc["$set"] = sets

            res = await self.books.update_many(
                {"$or": match_clauses},
                update_doc,
            )
            synced_count += res.modified_count
        return synced_count

    async def get_available_course_scopes(
        self, user_program: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns active course scopes with approved textbooks mapped to each course,
        sorted with user's enrolled department/program prioritized.
        """
        if self.books is None:
            return []

        cursor = self.books.find(
            {
                "course_codes": {"$exists": True, "$ne": []},
            },
            {
                "_id": 1,
                "title": 1,
                "course_codes": 1,
                "course_titles": 1,
                "program": 1,
                "category": 1,
                "subject": 1,
            },
        )

        courses_map: Dict[str, Dict[str, Any]] = {}
        async for book in cursor:
            bid = str(book["_id"])
            prog = (book.get("program") or book.get("category") or book.get("subject") or "GENERAL").upper()
            course_titles_dict = book.get("course_titles") or {}

            for raw_code in book.get("course_codes") or []:
                code = str(raw_code).strip().upper()
                if not code:
                    continue
                if code not in courses_map:
                    course_label = course_titles_dict.get(code) or book.get("category") or book.get("subject") or "Course Syllabus"
                    courses_map[code] = {
                        "course_code": code,
                        "display_name": f"{code} — {course_label}",
                        "program": prog,
                        "book_ids": [],
                        "book_titles": [],
                    }
                if bid not in courses_map[code]["book_ids"]:
                    courses_map[code]["book_ids"].append(bid)
                    courses_map[code]["book_titles"].append(book.get("title", "Book"))

        norm_user_prog = (user_program or "").strip().upper()

        def _sort_key(item: Dict[str, Any]):
            prog_match = 0
            if norm_user_prog:
                if item["program"] == norm_user_prog or (
                    norm_user_prog.endswith("CS") and item["course_code"].startswith("CS")
                ) or (
                    norm_user_prog.endswith("IT") and item["course_code"].startswith("IT")
                ):
                    prog_match = -1
            return (prog_match, item["course_code"])

        return sorted(courses_map.values(), key=_sort_key)

    async def get_book_ids_for_course(self, course_code: str) -> List[str]:
        """Returns all MongoDB book IDs approved for a given course syllabus code."""
        if not self.books or not course_code:
            return []
        norm_code = course_code.strip().upper()
        cursor = self.books.find(
            {"course_codes": norm_code},
            {"_id": 1}
        )
        return [str(b["_id"]) async for b in cursor]


async def get_course_syllabus_map(db) -> Dict[str, Dict[str, Any]]:
    """
    Aggregates active course codes and their mapped book_ids from both
    books.course_codes and approved Form FM-LIBS-002 records in requisitions
    (status == 'Approved / In Acquisition').
    """
    repo = SyllabusRepository(db)
    await repo.sync_approved_requisitions_to_books()
    scopes = await repo.get_available_course_scopes()
    return {item["course_code"]: item for item in scopes}

