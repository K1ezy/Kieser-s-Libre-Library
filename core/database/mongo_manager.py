from motor.motor_asyncio import AsyncIOMotorClient
from core.config import settings
from datetime import datetime
from typing import Optional, List, Dict, Any
import logging
import time
import uuid
import os
import shutil
import re
from pathlib import Path

# Setup Logger
logger = logging.getLogger("TARS_DB")

class MongoManager:
    """
    Optimized asynchronous MongoDB manager for Libre-Library.
    Handles books, chat history, planner tasks, flashcard decks, and user accounts.
    """
    def __init__(self):
        self.client = None
        self.db = None
        self.collection = None 

    async def initialize(self):
        """Connects to the MongoDB server and ensures indexes."""
        try:
            self.client = AsyncIOMotorClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000)
            self.db = self.client[settings.DB_NAME]
            
            # Primary collection reference (chat history)
            self.collection = self.db["chat_history"]
            
            # Test connection first
            await self.client.admin.command('ping')
            logger.info("MongoDB connection established successfully.")

            # Optimized Indexes for high-speed queries
            try:
                await self.collection.create_index([("session_id", 1), ("timestamp", 1)])
                await self.db['books'].create_index("id", unique=True)
                await self.db['books'].create_index([("added_at", -1)])
                await self.db['books'].create_index("title")
                await self.db['planner'].create_index("id", unique=True)
                await self.db['planner'].create_index([("created_at", -1)])
                await self.db['users'].create_index("email", unique=True, sparse=True)
                await self.db['users'].create_index("username", sparse=True)
                await self.db['decks'].create_index("task_id")
                await self.normalize_existing_users()
            except Exception as idx_err:
                logger.warning(f"Index creation notice: {idx_err}")
            
        except Exception as e:
            logger.error(f"MongoDB Connection Failed: {e}")

    # ==========================================
    # 📚 BOOK MANAGEMENT
    # ==========================================

    async def get_total_book_count(self) -> int:
        """Returns the total number of books."""
        if self.db is None: return 0
        try:
            return await self.db['books'].count_documents({})
        except Exception:
            return 0

    async def get_recent_books(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Returns the N most recently added books."""
        if self.db is None: return []
        try:
            cursor = self.db['books'].find().sort('added_at', -1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Recent Books Error: {e}")
            return []

    async def search_books(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Fast server-side indexed search on title, author, and subjects.
        Replaces slow in-memory filtering of 1000s of books.
        """
        if self.db is None or not query: return []
        try:
            escaped = re.escape(query.strip())
            regex = {"$regex": escaped, "$options": "i"}
            filter_spec = {
                "$or": [
                    {"title": regex},
                    {"authors": regex},
                    {"display_author": regex},
                    {"subjects": regex}
                ]
            }
            cursor = self.db['books'].find(filter_spec).sort("added_at", -1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Search Books Error: {e}")
            return []

    async def get_all_books(
        self,
        skip: int = 0,
        limit: int = 1000,
        sort_by: str = 'newest',
        format_filter: str = 'All',
        author_filter: str = 'All',
        search_query: str = ''
    ) -> List[Dict[str, Any]]:
        """
        Retrieves books with optional server-side filtering, sorting, and pagination.
        """
        if self.db is None: return []
        try:
            filter_doc = {}
            if search_query and search_query.strip():
                escaped = re.escape(search_query.strip())
                regex = {"$regex": escaped, "$options": "i"}
                filter_doc["$or"] = [
                    {"title": regex},
                    {"authors": regex},
                    {"display_author": regex},
                    {"subjects": regex}
                ]

            if format_filter and format_filter != 'All':
                # Matches format key in formats dictionary or file_type
                filter_doc["$or"] = [
                    {f"formats.{format_filter.lower()}": {"$exists": True}},
                    {"file_type": {"$regex": f"^{re.escape(format_filter)}$", "$options": "i"}}
                ]

            if author_filter and author_filter != 'All':
                filter_doc["$or"] = [
                    {"authors": author_filter},
                    {"display_author": author_filter}
                ]

            # Sorting logic
            sort_field = [("added_at", -1)]
            if sort_by.lower() == 'oldest':
                sort_field = [("added_at", 1)]
            elif sort_by.lower() in ('a-z', 'title'):
                sort_field = [("title", 1)]
            elif sort_by.lower() == 'author':
                sort_field = [("display_author", 1), ("authors", 1)]

            cursor = self.db['books'].find(filter_doc).sort(sort_field).skip(skip).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Get All Books Error: {e}")
            return []

    async def get_book_by_id(self, book_id: str) -> Optional[Dict[str, Any]]:
        """Finds a book by its unique ID."""
        if self.db is None: return None
        try:
            return await self.db['books'].find_one({"id": book_id})
        except Exception:
            return None

    async def get_book_details(self, book_id: str) -> Optional[Dict[str, Any]]:
        """Alias for get_book_by_id."""
        return await self.get_book_by_id(book_id)

    async def add_book_metadata(self, book_data: dict) -> bool:
        """Updates or inserts book metadata."""
        if self.db is None: return False
        try:
            if 'id' not in book_data: return False
            await self.db['books'].update_one(
                {"id": book_data['id']},
                {"$set": book_data},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Add Book Metadata Error: {e}")
            return False

    async def delete_book(self, book_id: str) -> bool:
        """
        Deletes a book completely:
        1. Removes from MongoDB 'books' collection.
        2. Removes physical folder from 'data/books/{book_id}'.
        3. Removes vector embeddings from ChromaDB.
        4. Removes any associated planner tasks and decks.
        """
        if self.db is None: return False
        try:
            # 1. Fetch book data first to get path or source name
            book = await self.get_book_by_id(book_id)

            # 2. Remove document from DB
            await self.db['books'].delete_one({"id": book_id})

            # 3. Remove physical files on disk
            book_dir = settings.BASE_DIR / 'data' / 'books' / book_id
            if book_dir.exists():
                shutil.rmtree(book_dir, ignore_errors=True)

            # 4. Remove ChromaDB vectors
            try:
                from core.ai_engine.rag_pipeline import tars_archive
                tars_archive.delete_source(book_id)
                if book:
                    # Also try filename if stored
                    local_p = book.get('local_path')
                    if local_p:
                        tars_archive.delete_source(Path(local_p).name)
            except Exception as vec_err:
                logger.warning(f"Vector cleanup notice for {book_id}: {vec_err}")

            # 5. Clean up associated planner tasks / decks
            await self.db['planner'].delete_many({"linked_book_id": book_id})
            logger.info(f"Book deleted successfully: {book_id}")
            return True

        except Exception as e:
            logger.error(f"Delete Book Error for {book_id}: {e}")
            return False

    def format_added_date(self, added_at: Any) -> str:
        """Helper to format added_at cleanly regardless of timestamp type."""
        if isinstance(added_at, (int, float)):
            try: return datetime.fromtimestamp(added_at).strftime("%b %d, %Y")
            except Exception: return "Recently"
        elif hasattr(added_at, 'strftime'):
            return added_at.strftime("%b %d, %Y")
        return "Unknown"

    # ==========================================
    # 💬 CHAT HISTORY
    # ==========================================

    async def get_recent_history(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        if self.collection is None: return []
        try:
            cursor = self.collection.find({"session_id": session_id}).sort("timestamp", 1)
            history = await cursor.to_list(length=100)
            return history[-limit:]
        except Exception as e:
            logger.error(f"History Error: {e}")
            return []

    async def add_message_to_session(self, session_id: str, role: str, content: str):
        if self.collection is None: return
        try:
            doc = {
                "session_id": session_id,
                "role": role,
                "content": content,
                "timestamp": time.time()
            }
            await self.collection.insert_one(doc)
        except Exception as e:
            logger.error(f"Save Message Error: {e}")
            
    async def save_chat_metadata(self, session_id: str, title: str):
        if self.db is None: return
        try:
            await self.db['chats'].update_one(
                {'id': session_id},
                {'$set': {'id': session_id, 'title': title, 'timestamp': time.time()}},
                upsert=True
            )
        except Exception: pass

    async def get_library_inventory_summary(self, limit: int = 10) -> str:
        """Returns dynamic string of real library books for TARS AI prompt context."""
        books = await self.get_recent_books(limit=limit)
        if not books:
            return "NO BOOKS CURRENTLY IN LIBRARY."
        lines = ["CURRENT LIBRARY INVENTORY:"]
        for b in books:
            title = b.get('title', 'Untitled')
            author = b.get('display_author') or b.get('authors', 'Unknown')
            if isinstance(author, list) and author: author = str(author[0])
            ftype = b.get('file_type', 'E-Book')
            lines.append(f"- '{title}' by {author} ({ftype}) [Available]")
        return "\n".join(lines)

    # ==========================================
    # 📅 PLANNER & FLASHCARDS
    # ==========================================

    async def add_task(
        self,
        title: str,
        subject: str,
        due_date: str,
        priority: str,
        linked_book_id: str = None,
        linked_book_title: str = None
    ) -> bool:
        if self.db is None: return False
        try:
            task = {
                "id": str(uuid.uuid4()),
                "title": title,
                "subject": subject,
                "due_date": due_date,
                "priority": priority,
                "status": "todo",
                "linked_book_id": linked_book_id,
                "linked_book_title": linked_book_title,
                "created_at": time.time()
            }
            await self.db['planner'].insert_one(task)
            return True
        except Exception as e:
            logger.error(f"Add Task Error: {e}")
            return False

    async def get_tasks(self) -> List[Dict[str, Any]]:
        if self.db is None: return []
        try:
            cursor = self.db['planner'].find({}).sort("created_at", -1)
            return await cursor.to_list(length=200)
        except Exception: return []

    async def update_task_status(self, task_id: str, new_status: str):
        if self.db is None: return
        try:
            await self.db['planner'].update_one({"id": task_id}, {"$set": {"status": new_status}})
        except Exception: pass

    async def delete_task(self, task_id: str):
        if self.db is None: return
        try:
            await self.db['planner'].delete_one({"id": task_id})
            await self.delete_deck(task_id)
        except Exception: pass

    async def save_deck(self, task_id: str, source_file: str, cards: list) -> bool:
        """Saves a flashcard deck linked to a planner task."""
        if self.db is None: return False
        try:
            deck_document = {
                'id': str(uuid.uuid4()),
                'task_id': task_id,
                'created_at': datetime.utcnow(),
                'source_file': source_file,
                'cards': cards
            }
            await self.db['decks'].delete_many({'task_id': task_id})
            await self.db['decks'].insert_one(deck_document)
            return True
        except Exception as e:
            logger.error(f"Save Deck Error: {e}")
            return False

    async def get_deck(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves flashcard deck for a task."""
        if self.db is None: return None
        try:
            return await self.db['decks'].find_one({'task_id': task_id})
        except Exception: return None

    async def delete_deck(self, task_id: str):
        """Removes a deck by task ID."""
        if self.db is None: return
        try:
            await self.db['decks'].delete_many({'task_id': task_id})
        except Exception: pass

    # ==========================================
    # 👤 USER & AUTH
    # ==========================================

    async def get_user_profile(self) -> Dict[str, Any]:
        if self.db is None: return {}
        try:
            profile = await self.db['users'].find_one({"type": "owner"})
            if not profile:
                profile = {
                    "type": "owner",
                    "name": "Library User",
                    "role": "Student",
                    "bio": "Exploring knowledge with Libre-Library.",
                    "joined_at": time.time()
                }
            return profile
        except Exception: return {}

    async def update_user_profile(self, name: str, role: str, bio: str) -> bool:
        if self.db is None: return False
        try:
            await self.db['users'].update_one(
                {"type": "owner"},
                {"$set": {"name": name, "role": role, "bio": bio}},
                upsert=True
            )
            return True
        except Exception: return False

    async def get_library_stats(self) -> Dict[str, Any]:
        if self.db is None: return {"books": 0, "tasks_done": 0}
        try:
            book_count = await self.db['books'].count_documents({})
            done_tasks = await self.db['planner'].count_documents({"status": "done"})
            return {"books": book_count, "tasks_done": done_tasks}
        except Exception: return {"books": 0, "tasks_done": 0}

    async def create_user(self, username: str, email: str, hashed_password: str, role: str = "user") -> Optional[Dict[str, Any]]:
        """Creates a new user account with normalized email, username, and password hash."""
        if self.db is None: return None
        try:
            clean_username = username.strip()
            clean_email = email.strip().lower()
            
            # Ensure hashed_password is a str
            hp_str = hashed_password.decode('utf-8') if isinstance(hashed_password, bytes) else str(hashed_password)
            
            # Double-check case-insensitively before inserting
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
        Safely handles legacy duplicate records.
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
                    doc_list.sort(key=lambda d: d.get('created_at', 0), reverse=True)
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

# Singleton instance
mongo_db = MongoManager()