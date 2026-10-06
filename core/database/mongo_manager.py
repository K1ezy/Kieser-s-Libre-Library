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
from bson import ObjectId

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
                await self.db['books'].create_index([("file_type", 1), ("added_at", -1)])
                await self.db['books'].create_index([("display_author", 1), ("added_at", -1)])
                await self.db['books'].create_index("shelves")
                await self.db['chats'].create_index("id", unique=True)
                await self.db['chats'].create_index([("user_id", 1), ("timestamp", -1)])
                await self.db['tasks'].create_index("id", unique=True)
                await self.db['tasks'].create_index([("user_id", 1), ("created_at", -1)])
                await self.db['planner'].create_index("id", unique=True)
                await self.db['planner'].create_index([("created_at", -1)])
                await self.db['reading_progress'].create_index([("user_id", 1), ("book_id", 1)], unique=True)
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
        search_query: str = '',
        projection: Optional[Dict[str, int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves books with optional server-side filtering, sorting, pagination, and field projection.
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

            cursor = self.db['books'].find(filter_doc, projection).sort(sort_field).skip(skip).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Get All Books Error: {e}")
            return []

    async def get_book_by_id(self, book_id: str) -> Optional[Dict[str, Any]]:
        """Finds a book by its unique ID, supporting both UUID id and MongoDB _id."""
        if self.db is None or not book_id: return None
        try:
            doc = await self.db['books'].find_one({"id": book_id})
            if not doc and ObjectId.is_valid(book_id):
                doc = await self.db['books'].find_one({"_id": ObjectId(book_id)})
            return doc
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
        1. Validates book_id format to prevent path traversal attacks.
        2. Removes from MongoDB 'books' collection.
        3. Safely removes physical folder from 'data/books/{book_id}'.
        4. Removes vector embeddings from ChromaDB.
        5. Removes any associated planner tasks and decks.
        """
        if self.db is None or not book_id: return False
        
        # Security: Prevent path traversal in book_id
        if not re.match(r'^[a-zA-Z0-9_-]+$', str(book_id)):
            logger.warning(f"Rejected delete_book with suspicious ID: {book_id}")
            return False

        try:
            # 1. Fetch book data first to get path or source name
            book = await self.get_book_by_id(book_id)

            # 2. Remove document from DB
            await self.db['books'].delete_one({"id": book_id})

            # 3. Remove physical files on disk with strict boundary validation
            books_root = (settings.BASE_DIR / 'data' / 'books').resolve()
            book_dir = (books_root / book_id).resolve()
            
            if book_dir != books_root and book_dir.is_relative_to(books_root) and book_dir.exists():
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
            await self.db['tasks'].delete_many({"linked_book_id": book_id})
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
            
    async def save_chat_metadata(
        self,
        session_id: str,
        title: str,
        book_id: str = None,
        book_title: str = None,
        user_id: Optional[str] = None
    ):
        if self.db is None: return
        try:
            update_data = {
                'id': session_id,
                'title': title,
                'timestamp': time.time()
            }
            if user_id:
                update_data['user_id'] = user_id
            if book_id:
                update_data['book_id'] = book_id
            if book_title:
                update_data['book_title'] = book_title
            if self.collection is not None:
                try:
                    cnt = await self.collection.count_documents({'session_id': session_id})
                    update_data['message_count'] = cnt
                except Exception: pass

            await self.db['chats'].update_one(
                {'id': session_id},
                {'$set': update_data},
                upsert=True
            )
        except Exception as e:
            logger.warning(f"Save Chat Metadata Error: {e}")

    async def get_chat_sessions(self, limit: int = 50, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.db is None: return []
        try:
            query: Dict[str, Any] = {'title': {'$exists': True, '$ne': ''}}
            if user_id:
                query['user_id'] = user_id
            cursor = self.db['chats'].find(query).sort('timestamp', -1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Get Chat Sessions Error: {e}")
            return []

    async def get_session_message_count(self, session_id: str) -> int:
        if self.collection is None: return 0
        try:
            return await self.collection.count_documents({'session_id': session_id})
        except Exception:
            return 0

    async def delete_chat_session(self, session_id: str) -> bool:
        if self.db is None: return False
        try:
            await self.db['chats'].delete_one({'id': session_id})
            if self.collection is not None:
                await self.collection.delete_many({'session_id': session_id})
            return True
        except Exception as e:
            logger.error(f"Delete Chat Session Error: {e}")
            return False

    async def get_full_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        if self.collection is None: return []
        try:
            cursor = self.collection.find({"session_id": session_id}).sort("timestamp", 1)
            return await cursor.to_list(length=500)
        except Exception as e:
            logger.error(f"Full Session Error: {e}")
            return []

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
        user_id: Optional[str] = None,
        due_date: str = "",
        priority: str = "medium",
        subject: str = "",
        linked_book_id: str = None,
        linked_book_title: str = None
    ) -> Optional[Dict[str, Any]]:
        """Creates a planner task indexed by user_id and synchronized across UI."""
        if self.db is None or not title: return None
        try:
            task = {
                "id": str(uuid.uuid4()),
                "user_id": str(user_id) if user_id else "default",
                "title": title.strip(),
                "subject": subject or "General",
                "due_date": due_date or "No date",
                "priority": priority or "medium",
                "completed": False,
                "status": "todo",
                "linked_book_id": linked_book_id,
                "linked_book_title": linked_book_title,
                "created_at": datetime.utcnow()
            }
            await self.db['tasks'].insert_one(task)
            return task
        except Exception as e:
            logger.error(f"Add Task Error: {e}")
            return None

    async def get_tasks(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves tasks for a specific user, with fallback to all tasks or legacy planner."""
        if self.db is None: return []
        try:
            query = {"user_id": user_id} if user_id else {}
            cursor = self.db['tasks'].find(query).sort("created_at", -1)
            tasks = await cursor.to_list(length=300)
            if not tasks:
                # Check legacy planner collection for backward compatibility
                cursor2 = self.db['planner'].find({}).sort("created_at", -1)
                tasks = await cursor2.to_list(length=300)
            return tasks
        except Exception as e:
            logger.error(f"Get Tasks Error: {e}")
            return []

    async def toggle_task_status(self, task_id: str, completed: Optional[bool] = None) -> bool:
        """Toggles or updates completion status on tasks."""
        if self.db is None: return False
        try:
            task = await self.db['tasks'].find_one({"id": task_id})
            target_coll = 'tasks'
            if not task:
                task = await self.db['planner'].find_one({"id": task_id})
                target_coll = 'planner'
            if not task: return False

            new_val = not task.get('completed', False) if completed is None else completed
            new_status = "done" if new_val else "todo"
            await self.db[target_coll].update_one(
                {"id": task_id},
                {"$set": {"completed": new_val, "status": new_status}}
            )
            return True
        except Exception as e:
            logger.error(f"Toggle Task Error: {e}")
            return False

    async def update_task_status(self, task_id: str, new_status: str) -> bool:
        is_done = new_status.lower() in ("done", "completed", "true")
        return await self.toggle_task_status(task_id, completed=is_done)

    async def delete_task(self, task_id: str) -> bool:
        if self.db is None: return False
        try:
            await self.db['tasks'].delete_one({"id": task_id})
            await self.db['planner'].delete_one({"id": task_id})
            await self.delete_deck(task_id)
            return True
        except Exception as e:
            logger.error(f"Delete Task Error: {e}")
            return False

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
    # 📖 READING PROGRESS & METADATA
    # ==========================================

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

    async def update_book_metadata(self, book_id: str, updates: Dict[str, Any]) -> bool:
        """Updates title, authors, genres, or other metadata."""
        if self.db is None or not book_id or not updates: return False
        try:
            q = {"id": book_id}
            if ObjectId.is_valid(book_id):
                existing = await self.db['books'].find_one({"id": book_id})
                if not existing:
                    q = {"_id": ObjectId(book_id)}

            await self.db['books'].update_one(q, {"$set": updates})
            return True
        except Exception as e:
            logger.error(f"Update Book Metadata Error: {e}")
            return False

    # ==========================================
    # 👤 USER & AUTH
    # ==========================================

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
            
            task_filter = {"$or": [{"completed": True}, {"status": "done"}]}
            total_filter = {}
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

    # ==========================================
    # ⚙️ SYSTEM SETTINGS & COLLECTIONS / SHELVES
    # ==========================================

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

    async def update_book_shelves(self, book_id: str, shelves: List[str]) -> bool:
        """Assigns custom user shelves/tags to a book."""
        if self.db is None or not book_id: return False
        try:
            clean_shelves = [s.strip() for s in shelves if s and s.strip()]
            return await self.update_book_metadata(book_id, {"shelves": clean_shelves})
        except Exception as e:
            logger.error(f"Update Shelves Error: {e}")
            return False

    async def toggle_book_favorite(self, book_id: str) -> bool:
        """Toggles favorite status on a book."""
        if self.db is None or not book_id: return False
        try:
            book = await self.get_book_by_id(book_id)
            if not book: return False
            curr = book.get("is_favorite", False)
            return await self.update_book_metadata(book_id, {"is_favorite": not curr})
        except Exception as e:
            logger.error(f"Toggle Favorite Error: {e}")
            return False

    async def update_book_reading_status(self, book_id: str, status: str) -> bool:
        """Updates reading status: 'to_read', 'reading', 'completed', 'none'."""
        if self.db is None or not book_id: return False
        try:
            return await self.update_book_metadata(book_id, {"reading_status": status.lower()})
        except Exception as e:
            logger.error(f"Update Reading Status Error: {e}")
            return False

    async def get_all_shelves(self) -> List[str]:
        """Returns distinct custom shelf names across all books."""
        if self.db is None: return []
        try:
            shelves = await self.db['books'].distinct("shelves")
            return sorted([s for s in shelves if s and isinstance(s, str)])
        except Exception:
            return []

    # ==========================================
    # 👤 EXTENDED USER PROFILE & READING HABITS
    # ==========================================

    async def get_user_reading_list(self, user_id: str, limit: int = 8) -> List[Dict[str, Any]]:
        """Returns in-progress reading records enriched with book metadata."""
        if self.db is None or not user_id: return []
        try:
            cursor = self.db['reading_progress'].find({"user_id": user_id}).sort("last_read_at", -1).limit(limit)
            progress_items = await cursor.to_list(length=limit)
            enriched = []
            for item in progress_items:
                b_id = item.get('book_id')
                book = await self.get_book_by_id(b_id)
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

            # Check old password
            if not bcrypt.checkpw(old_pwd.strip().encode('utf-8'), stored_hash.encode('utf-8')):
                return False, "Incorrect current password"

            # Hash new password
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

# Singleton instance
mongo_db = MongoManager()