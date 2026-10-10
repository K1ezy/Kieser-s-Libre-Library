import time
import logging
from typing import Optional, Dict, Any, List
from bson import ObjectId

from core.database.repositories.base_repository import BaseRepository

logger = logging.getLogger("PROGRESS_REPOSITORY")

class ProgressRepository(BaseRepository):
    """
    Dedicated repository for user reading progress, active page tracking,
    book summary persistence, and system-wide persistent settings.
    """

    async def save_reading_progress(
        self,
        user_id: str,
        book_id: str,
        current_page: int = 1,
        total_pages: int = 1,
        status: str = "reading"
    ) -> bool:
        """Saves persistent reading position, percentage and state for a user."""
        if self.db is None or not user_id or not book_id: return False
        try:
            percent = round((current_page / max(total_pages, 1)) * 100, 1) if total_pages > 0 else 0
            doc = {
                "user_id": user_id,
                "book_id": book_id,
                "current_page": current_page,
                "total_pages": total_pages,
                "progress_percent": percent,
                "status": status,
                "last_read_at": time.time()
            }
            await self.db['reading_progress'].update_one(
                {"user_id": user_id, "book_id": book_id},
                {"$set": doc},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Save Reading Progress Error: {e}")
            return False

    async def get_reading_progress(self, user_id: str, book_id: str) -> Optional[Dict[str, Any]]:
        if self.db is None or not user_id or not book_id: return None
        try:
            return await self.db['reading_progress'].find_one({"user_id": user_id, "book_id": book_id})
        except Exception: return None

    async def get_reading_history(self, user_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """Returns reading progress records for a user."""
        if self.db is None or not user_id: return []
        try:
            cursor = self.db['reading_progress'].find({"user_id": user_id}).sort("last_read_at", -1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Get Reading History Error: {e}")
            return []

    async def save_book_summary(self, book_id: str, summary_text: str) -> bool:
        """Saves AI generated summary directly onto the book record."""
        if self.db is None or not book_id: return False
        try:
            q = {"id": book_id}
            if ObjectId.is_valid(book_id):
                existing = await self.db['books'].find_one({"id": book_id})
                if not existing:
                    q = {"_id": ObjectId(book_id)}

            await self.db['books'].update_one(
                q,
                {
                    "$set": {"description": summary_text, "updated_at": time.time()},
                    "$push": {"summaries": {"$each": [summary_text], "$slice": -5}}
                }
            )
            return True
        except Exception as e:
            logger.error(f"Save Book Summary Error: {e}")
            return False

    async def get_system_settings(self) -> Dict[str, Any]:
        """Loads persistent system configuration (e.g. AI Provider)."""
        if self.db is None: return {}
        try:
            doc = await self.db['system_settings'].find_one({"key": "global_config"})
            return doc.get("settings", {}) if doc else {}
        except Exception as e:
            logger.error(f"Get System Settings Error: {e}")
            return {}

    async def save_system_settings(self, updates: Dict[str, Any]) -> bool:
        """Saves persistent system configuration."""
        if self.db is None: return False
        try:
            await self.db['system_settings'].update_one(
                {"key": "global_config"},
                {"$set": {"settings": updates, "updated_at": time.time()}},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Save System Settings Error: {e}")
            return False
