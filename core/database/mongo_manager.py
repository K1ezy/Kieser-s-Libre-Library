import asyncio
import logging
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from core.config import settings
from core.database.repositories import (
    BookRepository,
    ChatRepository,
    PlannerRepository,
    ProgressRepository,
    UserRepository,
)

logger = logging.getLogger("TARS_DB")

class MongoManager:
    """
    Modular Facade and Connection Coordinator for Libre-Library MongoDB.
    
    Delegates domain-specific persistence to focused repositories:
      - books: BookRepository (catalog, metadata, search, shelves, favorites)
      - chats: ChatRepository (messages, sessions, temporal history)
      - planner: PlannerRepository (tasks, schedules, flashcard decks)
      - progress: ProgressRepository (reading position, book summaries, system settings)
      - users: UserRepository (accounts, authentication, profiles, diagnostics)
    """

    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.collection = None

        # Domain Repositories
        self.books = BookRepository()
        self.chats = ChatRepository()
        self.chat = self.chats
        self.planner = PlannerRepository()
        self.progress = ProgressRepository()
        self.users = UserRepository()

    async def initialize(self):
        """Connects to MongoDB, configures optimized query indexes, and binds repositories."""
        try:
            self.client = AsyncIOMotorClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000)
            self.db = self.client[settings.DB_NAME]
            self.collection = self.db["chat_history"]

            # Bind database to domain repositories
            self.books.set_db(self.db)
            self.chats.set_db(self.db)
            self.planner.set_db(self.db)
            self.progress.set_db(self.db)
            self.users.set_db(self.db)

            # Confirm connection
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
                await self.users.normalize_existing_users()
                asyncio.create_task(self._ensure_covers_background())
            except Exception as idx_err:
                logger.warning(f"Index creation notice: {idx_err}")

        except Exception as e:
            logger.error(f"MongoDB Connection Failed: {e}")

    async def _ensure_covers_background(self):
        """Asynchronously checks and generates missing covers in background without blocking startup."""
        try:
            from core.utils.cover_manager import cover_manager
            await cover_manager.batch_generate_missing_covers(sync_mongodb=True)
        except Exception as e:
            logger.debug(f"Background cover check notice: {e}")

    # =========================================================================
    # 📚 BOOK DELEGATE METHODS (Backwards-compatible API)
    # =========================================================================
    async def get_total_book_count(self) -> int:
        return await self.books.get_total_book_count()

    async def get_recent_books(self, limit: int = 5) -> List[Dict[str, Any]]:
        return await self.books.get_recent_books(limit=limit)

    async def search_books(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        return await self.books.search_books(query=query, limit=limit)

    async def get_all_books(self, *args, **kwargs) -> List[Dict[str, Any]]:
        return await self.books.get_all_books(*args, **kwargs)

    async def get_book_by_id(self, book_id: str) -> Optional[Dict[str, Any]]:
        return await self.books.get_book_by_id(book_id)

    async def get_book_details(self, book_id: str) -> Optional[Dict[str, Any]]:
        return await self.books.get_book_details(book_id)

    async def add_book_metadata(self, book_data: dict) -> bool:
        return await self.books.add_book_metadata(book_data)

    async def update_book_metadata(self, book_id: str, updates: Dict[str, Any]) -> bool:
        return await self.books.update_book_metadata(book_id, updates)

    async def delete_book(self, book_id: str) -> bool:
        return await self.books.delete_book(book_id)

    def format_added_date(self, added_at: Any) -> str:
        return self.books.format_added_date(added_at)

    async def get_library_inventory_summary(self, limit: int = 10) -> str:
        return await self.books.get_library_inventory_summary(limit=limit)

    async def update_book_shelves(self, book_id: str, shelves: List[str]) -> bool:
        return await self.books.update_book_shelves(book_id, shelves)

    async def toggle_book_favorite(self, book_id: str) -> bool:
        return await self.books.toggle_book_favorite(book_id)

    async def update_book_reading_status(self, book_id: str, status: str) -> bool:
        return await self.books.update_book_reading_status(book_id, status)

    async def get_all_shelves(self) -> List[str]:
        return await self.books.get_all_shelves()

    # =========================================================================
    # 💬 CHAT DELEGATE METHODS
    # =========================================================================
    async def get_recent_history(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        return await self.chats.get_recent_history(session_id, limit=limit)

    async def add_message_to_session(self, session_id: str, role: str, content: str):
        await self.chats.add_message_to_session(session_id, role, content)

    async def save_chat_metadata(self, session_id: str, title: str, book_id: str = None, book_title: str = None, user_id: Optional[str] = None):
        await self.chats.save_chat_metadata(session_id, title, book_id, book_title, user_id)

    async def get_chat_sessions(self, limit: int = 50, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return await self.chats.get_chat_sessions(limit=limit, user_id=user_id)

    async def get_session_message_count(self, session_id: str) -> int:
        return await self.chats.get_session_message_count(session_id)

    async def delete_chat_session(self, session_id: str) -> bool:
        return await self.chats.delete_chat_session(session_id)

    async def get_full_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        return await self.chats.get_full_session_messages(session_id)

    # =========================================================================
    # 📅 PLANNER & FLASHCARD DELEGATE METHODS
    # =========================================================================
    async def add_task(self, title: str, user_id: Optional[str] = None, due_date: str = "", priority: str = "medium", subject: str = "", linked_book_id: str = None, linked_book_title: str = None) -> Optional[Dict[str, Any]]:
        return await self.planner.add_task(title, user_id, due_date, priority, subject, linked_book_id, linked_book_title)

    async def get_tasks(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return await self.planner.get_tasks(user_id)

    async def toggle_task_status(self, task_id: str, completed: Optional[bool] = None) -> bool:
        return await self.planner.toggle_task_status(task_id, completed)

    async def update_task_status(self, task_id: str, new_status: str) -> bool:
        return await self.planner.update_task_status(task_id, new_status)

    async def delete_task(self, task_id: str) -> bool:
        return await self.planner.delete_task(task_id)

    async def save_deck(self, task_id: str, source_file: str, cards: list) -> bool:
        return await self.planner.save_deck(task_id, source_file, cards)

    async def get_deck(self, task_id: str) -> Optional[Dict[str, Any]]:
        return await self.planner.get_deck(task_id)

    async def delete_deck(self, task_id: str):
        await self.planner.delete_deck(task_id)

    # =========================================================================
    # 📖 READING PROGRESS & SETTINGS DELEGATE METHODS
    # =========================================================================
    async def save_reading_progress(self, user_id: str, book_id: str, current_page: int = 1, total_pages: int = 1, status: str = "reading") -> bool:
        return await self.progress.save_reading_progress(user_id, book_id, current_page, total_pages, status)

    async def get_reading_progress(self, user_id: str, book_id: str) -> Optional[Dict[str, Any]]:
        return await self.progress.get_reading_progress(user_id, book_id)

    async def save_book_summary(self, book_id: str, summary_text: str) -> bool:
        return await self.progress.save_book_summary(book_id, summary_text)

    async def get_system_settings(self) -> Dict[str, Any]:
        return await self.progress.get_system_settings()

    async def save_system_settings(self, updates: Dict[str, Any]) -> bool:
        return await self.progress.save_system_settings(updates)

    # =========================================================================
    # 👤 USER & AUTHENTICATION DELEGATE METHODS
    # =========================================================================
    async def get_user_profile(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        return await self.users.get_user_profile(user_id)

    async def update_user_profile(self, user_id: Optional[str], name: str, bio: str, headline: Optional[str] = None) -> bool:
        return await self.users.update_user_profile(user_id, name, bio, headline)

    async def get_total_user_count(self) -> int:
        return await self.users.get_total_user_count()

    async def get_library_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        return await self.users.get_library_stats(user_id)

    async def update_user_role(self, user_id: str, new_role: str) -> bool:
        return await self.users.update_user_role(user_id, new_role)

    async def delete_user_by_id(self, user_id: str) -> bool:
        return await self.users.delete_user_by_id(user_id)

    async def get_system_diagnostics(self) -> Dict[str, Any]:
        return await self.users.get_system_diagnostics()

    async def create_user(self, username: str, email: str, hashed_password: str, role: str = "user") -> Optional[Dict[str, Any]]:
        return await self.users.create_user(username, email, hashed_password, role)

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return await self.users.get_user_by_email(email)

    async def get_user_by_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        return await self.users.get_user_by_identifier(identifier)

    async def get_users_by_identifier(self, identifier: str) -> List[Dict[str, Any]]:
        return await self.users.get_users_by_identifier(identifier)

    async def update_user_last_login(self, user_id: str):
        await self.users.update_user_last_login(user_id)

    async def get_all_users(self) -> List[Dict[str, Any]]:
        return await self.users.get_all_users()

    async def normalize_existing_users(self):
        await self.users.normalize_existing_users()

    async def get_user_reading_list(self, user_id: str, limit: int = 8) -> List[Dict[str, Any]]:
        return await self.users.get_user_reading_list(user_id, limit=limit)

    async def get_user_favorites(self, limit: int = 8) -> List[Dict[str, Any]]:
        return await self.users.get_user_favorites(limit=limit)

    async def change_user_password(self, user_id: str, old_pwd: str, new_pwd: str) -> tuple:
        return await self.users.change_user_password(user_id, old_pwd, new_pwd)

    async def update_user_preferences(self, user_id: str, prefs: Dict[str, Any]) -> bool:
        return await self.users.update_user_preferences(user_id, prefs)

    async def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        return await self.users.get_user_preferences(user_id)

# Global Singleton Instance
mongo_db = MongoManager()