import time
import uuid
import logging
from typing import Optional, Dict, Any, List
from bson import ObjectId

from core.database.repositories.base_repository import BaseRepository

logger = logging.getLogger("ANNOTATION_REPOSITORY")


class AnnotationRepository(BaseRepository):
    """
    Dedicated repository for interactive text highlights, student margin notes,
    and reading passage bookmarks.
    """

    async def create_annotation(
        self,
        user_id: str,
        book_id: str,
        selected_text: str,
        color: str = "yellow",
        cfi_range: Optional[str] = None,
        page_number: Optional[int] = 1,
        rects: Optional[List[Dict[str, Any]]] = None,
        note: Optional[str] = ""
    ) -> Dict[str, Any]:
        """Creates a new highlighted quote or student note."""
        if self.db is None:
            return {"success": False, "error": "Database not initialized"}

        clean_user = (user_id or "guest").strip()
        clean_book = str(book_id).strip()
        clean_text = str(selected_text or "").strip()
        clean_color = str(color or "yellow").lower()
        if clean_color not in ("yellow", "green", "blue", "pink", "purple"):
            clean_color = "yellow"

        if not clean_text:
            return {"success": False, "error": "Selected text cannot be empty"}

        ann_id = f"ann_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        now = time.time()

        doc = {
            "id": ann_id,
            "user_id": clean_user,
            "book_id": clean_book,
            "selected_text": clean_text,
            "color": clean_color,
            "cfi_range": cfi_range,
            "page_number": int(page_number) if page_number is not None else 1,
            "rects": rects or [],
            "note": str(note or "").strip(),
            "created_at": now,
            "updated_at": now
        }

        try:
            await self.db['annotations'].insert_one(doc)
            return {"success": True, "annotation": self.clean_doc(doc)}
        except Exception as e:
            logger.error(f"Create Annotation Error: {e}")
            return {"success": False, "error": str(e)}

    async def get_book_annotations(self, user_id: str, book_id: str) -> List[Dict[str, Any]]:
        """Retrieves all annotations created by a user for a given book, ordered chronologically."""
        if self.db is None or not book_id:
            return []
        clean_user = (user_id or "guest").strip()
        clean_book = str(book_id).strip()
        try:
            cursor = self.db['annotations'].find(
                {"user_id": clean_user, "book_id": clean_book}
            ).sort("created_at", 1)
            docs = await cursor.to_list(length=1000)
            return self.clean_docs(docs)
        except Exception as e:
            logger.error(f"Get Book Annotations Error: {e}")
            return []

    async def get_annotation(self, annotation_id: str) -> Optional[Dict[str, Any]]:
        """Finds a single annotation by its public alphanumeric id."""
        if self.db is None or not annotation_id:
            return None
        clean_id = str(annotation_id).strip()
        try:
            doc = await self.db['annotations'].find_one({"id": clean_id})
            return self.clean_doc(doc)
        except Exception as e:
            logger.error(f"Get Annotation Error: {e}")
            return None

    async def update_annotation(self, annotation_id: str, updates: Dict[str, Any], user_id: Optional[str] = None) -> bool:
        """Modifies note commentary or color for an existing annotation with ownership validation."""
        if self.db is None or not annotation_id:
            return False
        clean_id = str(annotation_id).strip()
        allowed_updates = {}
        if "color" in updates and str(updates["color"]).lower() in ("yellow", "green", "blue", "pink", "purple"):
            allowed_updates["color"] = str(updates["color"]).lower()
        if "note" in updates:
            allowed_updates["note"] = str(updates["note"]).strip()

        if not allowed_updates:
            return True

        allowed_updates["updated_at"] = time.time()
        query = {"id": clean_id}
        if user_id:
            query["user_id"] = user_id.strip()
        try:
            res = await self.db['annotations'].update_one(
                query,
                {"$set": allowed_updates}
            )
            return res.acknowledged and res.matched_count > 0
        except Exception as e:
            logger.error(f"Update Annotation Error: {e}")
            return False

    async def delete_annotation(self, annotation_id: str, user_id: Optional[str] = None) -> bool:
        """Removes an annotation by ID."""
        if self.db is None or not annotation_id:
            return False
        clean_id = str(annotation_id).strip()
        query = {"id": clean_id}
        if user_id:
            query["user_id"] = user_id.strip()

        try:
            res = await self.db['annotations'].delete_one(query)
            return res.acknowledged and res.deleted_count > 0
        except Exception as e:
            logger.error(f"Delete Annotation Error: {e}")
            return False

    def generate_markdown_export(self, annotations: List[Dict[str, Any]], book_title: str = "Document") -> str:
        """Generates a clean, portable Markdown study guide from saved highlights and notes."""
        lines = [
            f"# 📚 Reading Notes & Highlights: {book_title}",
            f"*Exported from Libre-Library on {time.strftime('%Y-%m-%d %H:%M')}*",
            f"**Total Annotations:** {len(annotations)}",
            "",
            "---",
            ""
        ]

        if not annotations:
            lines.append("*No highlights or annotations recorded for this document.*")
            return "\n".join(lines)

        for i, ann in enumerate(annotations, 1):
            color = ann.get("color", "yellow").capitalize()
            page = ann.get("page_number", 1)
            text = ann.get("selected_text", "").strip()
            note = ann.get("note", "").strip()
            created = time.strftime("%Y-%m-%d %H:%M", time.localtime(ann.get("created_at", time.time())))

            lines.append(f"### {i}. [{color}] Page {page} ({created})")
            lines.append(f"> \"{text}\"")
            if note:
                lines.append("")
                lines.append(f"**Note:** {note}")
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)
