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
        status: str = "reading",
        cfi: Optional[str] = None,
        client_timestamp: Optional[float] = None,
        progress_percent: Optional[float] = None,
        theme: Optional[str] = None,
        font_size: Optional[int] = None,
        font_family: Optional[str] = None,
        line_height: Optional[float] = None
    ) -> bool:
        """Saves persistent reading position, percentage, CFI, and state for a user."""
        if self.db is None or not user_id or not book_id: return False
        try:
            req_time = client_timestamp or time.time()
            existing = await self.db['reading_progress'].find_one({"user_id": user_id, "book_id": book_id})
            if existing and existing.get("last_read_at", 0) > req_time + 1.0:
                logger.warning(f"Discarding stale reading progress update for user={user_id}, book={book_id}")
                return True

            if progress_percent is not None:
                percent = round(float(progress_percent), 1)
            else:
                percent = round((current_page / max(total_pages, 1)) * 100, 1) if total_pages > 0 else 0
            doc = {
                "user_id": user_id,
                "book_id": book_id,
                "current_page": current_page,
                "total_pages": total_pages,
                "progress_percent": percent,
                "status": status,
                "last_read_at": req_time
            }
            if cfi:
                doc["cfi"] = cfi
            elif existing and existing.get("cfi"):
                doc["cfi"] = existing["cfi"]

            # Persistent reader appearance preferences
            if theme:
                doc["theme"] = theme
            elif existing and existing.get("theme"):
                doc["theme"] = existing["theme"]

            if font_size is not None:
                doc["font_size"] = font_size
            elif existing and existing.get("font_size") is not None:
                doc["font_size"] = existing["font_size"]

            if font_family:
                doc["font_family"] = font_family
            elif existing and existing.get("font_family"):
                doc["font_family"] = existing["font_family"]

            if line_height is not None:
                doc["line_height"] = line_height
            elif existing and existing.get("line_height") is not None:
                doc["line_height"] = existing["line_height"]

            await self.db['reading_progress'].update_one(
                {"user_id": user_id, "book_id": book_id},
                {"$set": doc},
                upsert=True
            )
            try:
                from core.services.user_telemetry import telemetry_engine
                telemetry_engine.record_reading_activity(
                    user_id=user_id,
                    book_id=book_id,
                    current_page=current_page,
                    total_pages=total_pages,
                    pages_delta=1
                )
            except Exception as te_err:
                logger.debug(f"Telemetry recording skipped: {te_err}")
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

    async def get_reader_preferences(self, user_id: str) -> Dict[str, Any]:
        """Fetches cross-device reader appearance preferences for a user."""
        default_prefs = {
            "theme": "light",
            "font_size": 16,
            "font_family": "sans",
            "line_height": 1.65
        }
        if self.db is None or not user_id:
            return default_prefs
        try:
            doc = await self.db['system_settings'].find_one({"key": f"reader_prefs_{user_id}"})
            if doc and "preferences" in doc:
                merged = dict(default_prefs)
                merged.update(doc["preferences"])
                return merged
            return default_prefs
        except Exception as e:
            logger.error(f"Get Reader Preferences Error: {e}")
            return default_prefs

    async def save_reader_preferences(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """Saves cross-device reader appearance preferences for a user."""
        if self.db is None or not user_id:
            return False
        try:
            clean_updates = {}
            if "theme" in updates and str(updates["theme"]).lower() in ("light", "sepia", "dark", "black"):
                clean_updates["theme"] = str(updates["theme"]).lower()
            if "font_size" in updates and updates["font_size"] is not None:
                try:
                    clean_updates["font_size"] = max(10, min(40, int(updates["font_size"])))
                except (ValueError, TypeError):
                    pass
            if "font_family" in updates and str(updates["font_family"]).lower() in ("sans", "serif", "dyslexic"):
                clean_updates["font_family"] = str(updates["font_family"]).lower()
            if "line_height" in updates and updates["line_height"] is not None:
                try:
                    clean_updates["line_height"] = max(1.0, min(3.0, round(float(updates["line_height"]), 2)))
                except (ValueError, TypeError):
                    pass

            if not clean_updates:
                return True

            await self.db['system_settings'].update_one(
                {"key": f"reader_prefs_{user_id}"},
                {
                    "$set": {
                        "preferences": clean_updates,
                        "updated_at": time.time()
                    }
                },
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Save Reader Preferences Error: {e}")
            return False
