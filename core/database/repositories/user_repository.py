import re
import time
import uuid
import logging
from typing import Optional, List, Dict, Any

from core.database.repositories.base_repository import BaseRepository

logger = logging.getLogger("USER_REPOSITORY")

class UserRepository(BaseRepository):
    """
    Dedicated repository for user authentication, accounts, roles, profiles,
    security credentials, personal preferences, and administrative diagnostics.
    """

    async def get_user_profile(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Gets user profile strictly isolated by user ID."""
        if self.db is None: return {}
        try:
            if user_id:
                user = await self.db['users'].find_one({"id": user_id, "type": "account"})
                if user:
                    return {
                        "id": user_id,
                        "name": user.get("name") or user.get("username", "Library User"),
                        "username": user.get("username", "user"),
                        "email": user.get("email", ""),
                        "role": user.get("role", "user"),
                        "headline": user.get("headline", "Student / Researcher"),
                        "bio": user.get("bio", "Exploring knowledge with Libre-Library."),
                        "joined_at": user.get("created_at", time.time())
                    }
            return {
                "name": "Library User",
                "username": "user",
                "email": "",
                "role": "user",
                "headline": "Student / Researcher",
                "bio": "Exploring knowledge with Libre-Library.",
                "joined_at": time.time()
            }
        except Exception: return {}

    async def update_user_profile(self, user_id: Optional[str], name: str, bio: str, headline: Optional[str] = None) -> bool:
        """
        Updates profile strictly isolated to the specified user account.
        SECURITY: Role permissions cannot be modified through profile updates.
        """
        if self.db is None or not user_id: return False
        try:
            updates = {
                "name": name.strip(),
                "bio": bio.strip()
            }
            if headline is not None:
                updates["headline"] = headline.strip()

            result = await self.db['users'].update_one(
                {"id": user_id, "type": "account"},
                {"$set": updates}
            )
            return result.modified_count > 0 or result.matched_count > 0
        except Exception as e:
            logger.error(f"Update User Profile Error: {e}")
            return False

    async def get_total_user_count(self) -> int:
        """Returns total registered user accounts."""
        if self.db is None: return 0
        try:
            return await self.db['users'].count_documents({"type": "account"})
        except Exception:
            return 0

    async def get_library_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Calculates real-time library, study and task completion statistics."""
        if self.db is None: return {"books": 0, "tasks_done": 0, "total_tasks": 0, "reading_count": 0}
        try:
            book_count = await self.db['books'].count_documents({})
            
            task_filter: Dict[str, Any] = {"$or": [{"completed": True}, {"status": "done"}]}
            total_filter: Dict[str, Any] = {}
            if user_id:
                task_filter["user_id"] = user_id
                total_filter["user_id"] = user_id

            done_tasks = await self.db['tasks'].count_documents(task_filter)
            if done_tasks == 0 and not user_id:
                done_tasks = await self.db['planner'].count_documents({"status": "done"})

            total_tasks = await self.db['tasks'].count_documents(total_filter)
            if total_tasks == 0 and not user_id:
                total_tasks = await self.db['planner'].count_documents({})

            reading_count = 0
            if 'reading_progress' in await self.db.list_collection_names():
                reading_q = {"user_id": user_id} if user_id else {}
                reading_count = await self.db['reading_progress'].count_documents(reading_q)

            return {
                "books": book_count,
                "tasks_done": done_tasks,
                "total_tasks": total_tasks,
                "reading_count": reading_count
            }
        except Exception as e:
            logger.error(f"Stats Error: {e}")
            return {"books": 0, "tasks_done": 0, "total_tasks": 0, "reading_count": 0}

    async def update_user_role(self, user_id: str, new_role: str) -> bool:
        """Promotes or demotes user role (admin/user)."""
        if self.db is None: return False
        try:
            await self.db['users'].update_one({"id": user_id}, {"$set": {"role": new_role}})
            return True
        except Exception as e:
            logger.error(f"Update User Role Error: {e}")
            return False

    async def delete_user_by_id(self, user_id: str) -> bool:
        """Deletes user account and associated personal study data."""
        if self.db is None: return False
        try:
            await self.db['users'].delete_one({"id": user_id})
            await self.db['tasks'].delete_many({"user_id": user_id})
            await self.db['reading_progress'].delete_many({"user_id": user_id})
            return True
        except Exception as e:
            logger.error(f"Delete User Error: {e}")
            return False

    async def get_system_diagnostics(self) -> Dict[str, Any]:
        """Provides holistic system diagnostic metrics for the Admin Console."""
        if self.db is None: return {}
        try:
            user_count = await self.db['users'].count_documents({"type": "account"})
            book_count = await self.db['books'].count_documents({})
            task_count = await self.db['tasks'].count_documents({})
            deck_count = await self.db['decks'].count_documents({})
            chat_count = await self.db['chat_history'].count_documents({})
            return {
                "users": user_count,
                "books": book_count,
                "tasks": task_count,
                "decks": deck_count,
                "chat_messages": chat_count
            }
        except Exception as e:
            logger.error(f"System Diagnostics Error: {e}")
            return {}

    async def create_user(self, username: str, email: str, hashed_password: str, role: str = "user") -> Optional[Dict[str, Any]]:
        """Creates a new user account with normalized email, username, and password hash."""
        if self.db is None: return None
        try:
            clean_username = username.strip()
            clean_email = email.strip().lower()
            
            hp_str = hashed_password.decode('utf-8') if isinstance(hashed_password, bytes) else str(hashed_password)
            
            existing_email = await self.get_user_by_email(clean_email)
            if existing_email:
                logger.warning(f"Attempted to create duplicate user for email: {clean_email}")
                return None

            existing_user = await self.get_user_by_identifier(clean_username)
            if existing_user:
                logger.warning(f"Attempted to create duplicate user for username: {clean_username}")
                return None

            user = {
                "id": str(uuid.uuid4()),
                "username": clean_username,
                "email": clean_email,
                "hashed_password": hp_str,
                "role": role,
                "created_at": time.time(),
                "last_login": None,
                "type": "account"
            }
            await self.db['users'].insert_one(user)
            return user
        except Exception as e:
            logger.error(f"Create User Error: {e}")
            return None

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Case-insensitive search for a user by email."""
        if self.db is None or not email: return None
        try:
            clean = email.strip()
            regex = {"$regex": f"^{re.escape(clean)}$", "$options": "i"}
            return await self.db['users'].find_one({"email": regex, "type": "account"})
        except Exception as e:
            logger.error(f"Get User By Email Error: {e}")
            return None

    async def get_user_by_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a user by email or username (case-insensitive & trimmed).
        Returns the primary user record.
        """
        if self.db is None or not identifier: return None
        try:
            clean = identifier.strip()
            regex = {"$regex": f"^{re.escape(clean)}$", "$options": "i"}
            return await self.db['users'].find_one({
                "$or": [
                    {"email": regex},
                    {"username": regex}
                ],
                "type": "account"
            })
        except Exception as e:
            logger.error(f"Get User By Identifier Error: {e}")
            return None

    async def get_users_by_identifier(self, identifier: str) -> List[Dict[str, Any]]:
        """
        Retrieves all matching user accounts by email or username (case-insensitive).
        """
        if self.db is None or not identifier: return []
        try:
            clean = identifier.strip()
            regex = {"$regex": f"^{re.escape(clean)}$", "$options": "i"}
            cursor = self.db['users'].find({
                "$or": [
                    {"email": regex},
                    {"username": regex}
                ],
                "type": "account"
            })
            return await cursor.to_list(length=10)
        except Exception as e:
            logger.error(f"Get Users By Identifier Error: {e}")
            return []

    async def update_user_last_login(self, user_id: str):
        if self.db is None: return
        try:
            await self.db['users'].update_one({"id": user_id}, {"$set": {"last_login": time.time()}})
        except Exception: pass

    async def get_all_users(self) -> List[Dict[str, Any]]:
        if self.db is None: return []
        try:
            cursor = self.db['users'].find({"type": "account"})
            return await cursor.to_list(length=100)
        except Exception: return []

    async def normalize_existing_users(self):
        """
        One-time maintenance to normalize whitespace and casing across existing user accounts.
        Also resolves duplicate casing accounts so users have a single unified account with admin privileges.
        """
        if self.db is None: return
        try:
            users = await self.db['users'].find({"type": "account"}).to_list(length=200)
            by_email: Dict[str, List[Dict[str, Any]]] = {}
            for u in users:
                raw_email = u.get('email')
                if not raw_email: continue
                clean = raw_email.strip().lower()
                by_email.setdefault(clean, []).append(u)

            for clean_email, doc_list in by_email.items():
                if len(doc_list) > 1:
                    has_admin = any(d.get('role') == 'admin' for d in doc_list)
                    def _safe_user_ts(d):
                        c = d.get('created_at')
                        if hasattr(c, 'timestamp'): return c.timestamp()
                        try: return float(c or 0)
                        except Exception: return 0.0
                    doc_list.sort(key=_safe_user_ts, reverse=True)
                    keeper = doc_list[0]
                    duplicates = doc_list[1:]

                    dup_ids = [d["_id"] for d in duplicates]
                    await self.db['users'].delete_many({"_id": {"$in": dup_ids}})

                    new_role = "admin" if has_admin else keeper.get('role', 'user')
                    await self.db['users'].update_one(
                        {"_id": keeper["_id"]},
                        {"$set": {
                            "email": clean_email,
                            "username": keeper.get("username", clean_email.split('@')[0]).strip(),
                            "role": new_role
                        }}
                    )
                    logger.info(f"Reconciled duplicate user account for email: {clean_email} (preserved {new_role} role)")
                else:
                    u = doc_list[0]
                    clean_username = (u.get("username") or "").strip() or clean_email.split('@')[0]
                    await self.db['users'].update_one(
                        {"_id": u["_id"]},
                        {"$set": {"email": clean_email, "username": clean_username}}
                    )
            logger.info("User accounts normalized successfully.")
        except Exception as e:
            logger.warning(f"User normalization note: {e}")

    async def get_user_reading_list(self, user_id: str, limit: int = 8) -> List[Dict[str, Any]]:
        """Returns in-progress reading records enriched with book metadata."""
        if self.db is None or not user_id: return []
        try:
            cursor = self.db['reading_progress'].find({"user_id": user_id}).sort("last_read_at", -1).limit(limit)
            progress_items = await cursor.to_list(length=limit)
            enriched = []
            for item in progress_items:
                b_id = item.get('book_id')
                book = await self.db['books'].find_one({"id": b_id})
                if book:
                    enriched.append({
                        "book_id": b_id,
                        "title": book.get('title', 'Untitled'),
                        "display_author": book.get('display_author') or 'Unknown Author',
                        "cover_image": book.get('cover_image') or f"/static_books/{b_id}/cover.jpg",
                        "file_type": book.get('file_type', 'E-BOOK'),
                        "current_page": item.get('current_page', 1),
                        "total_pages": item.get('total_pages', 1),
                        "progress_percent": item.get('progress_percent', 0),
                        "status": item.get('status', 'reading'),
                        "last_read_at": item.get('last_read_at', time.time())
                    })
            return enriched
        except Exception as e:
            logger.error(f"Get User Reading List Error: {e}")
            return []

    async def get_user_favorites(self, limit: int = 8) -> List[Dict[str, Any]]:
        """Returns books marked as favorites."""
        if self.db is None: return []
        try:
            cursor = self.db['books'].find({"is_favorite": True}).sort("added_at", -1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Get Favorites Error: {e}")
            return []

    async def change_user_password(self, user_id: str, old_pwd: str, new_pwd: str) -> tuple:
        """Verifies current password and updates password hash."""
        if self.db is None or not user_id: return False, "Database unavailable"
        if len(new_pwd.strip()) < 6: return False, "New password must be at least 6 characters"
        try:
            import bcrypt
            user = await self.db['users'].find_one({"id": user_id})
            if not user: return False, "User account not found"

            stored_hash = user.get('hashed_password', '')
            if not stored_hash: return False, "Account has no password configured"

            if not bcrypt.checkpw(old_pwd.strip().encode('utf-8'), stored_hash.encode('utf-8')):
                return False, "Incorrect current password"

            new_hash = bcrypt.hashpw(new_pwd.strip().encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            await self.db['users'].update_one(
                {"id": user_id},
                {"$set": {"hashed_password": new_hash, "updated_at": time.time()}}
            )
            return True, "Password successfully updated!"
        except Exception as e:
            logger.error(f"Change Password Error: {e}")
            return False, f"Password change error: {e}"

    async def update_user_preferences(self, user_id: str, prefs: Dict[str, Any]) -> bool:
        """Updates user preferences (theme, reading goal, AI tone, avatar icon)."""
        if self.db is None or not user_id: return False
        try:
            await self.db['users'].update_one(
                {"id": user_id},
                {"$set": {"preferences": prefs}}
            )
            return True
        except Exception as e:
            logger.error(f"Update Preferences Error: {e}")
            return False

    async def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Loads user preferences."""
        if self.db is None or not user_id: return {}
        try:
            user = await self.db['users'].find_one({"id": user_id})
            if user:
                return user.get("preferences", {})
            return {}
        except Exception:
            return {}
