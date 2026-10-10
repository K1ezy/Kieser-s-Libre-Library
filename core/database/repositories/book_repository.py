import re
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from bson import ObjectId

from core.config import settings
from core.database.repositories.base_repository import BaseRepository

logger = logging.getLogger("BOOK_REPOSITORY")

class BookRepository(BaseRepository):
    """
    Dedicated repository for book metadata, catalog queries, search indexing,
    shelving, reading statuses, and physical book file resolution.
    """

    async def get_total_book_count(self) -> int:
        """Returns the total number of books in the collection."""
        if self.db is None: return 0
        try:
            return await self.db['books'].count_documents({})
        except Exception:
            return 0

    async def get_recent_books(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Returns the N most recently added books with lightweight projection."""
        if self.db is None: return []
        try:
            proj = {
                "_id": 0, "id": 1, "title": 1, "display_author": 1,
                "authors": 1, "file_type": 1, "formats": 1, "cover_image": 1,
                "added_at": 1, "created_at": 1
            }
            cursor = self.db['books'].find({}, proj).sort('added_at', -1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Recent Books Error: {e}")
            return []

    async def search_books(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Fast server-side indexed search on title, author, and subjects.
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
        Retrieves books with optional server-side filtering, sorting, pagination, and projection.
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

    async def update_book_metadata(self, book_id: str, updates: Dict[str, Any]) -> bool:
        """Applies arbitrary partial updates to a book record."""
        if self.db is None or not book_id: return False
        try:
            res = await self.db['books'].update_one(
                {"id": book_id},
                {"$set": updates}
            )
            return res.modified_count > 0 or res.matched_count > 0
        except Exception as e:
            logger.error(f"Update Book Metadata Error: {e}")
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
            book = await self.get_book_by_id(book_id)

            await self.db['books'].delete_one({"id": book_id})

            books_root = (settings.BASE_DIR / 'data' / 'books').resolve()
            book_dir = (books_root / book_id).resolve()
            
            if book_dir != books_root and book_dir.is_relative_to(books_root) and book_dir.exists():
                shutil.rmtree(book_dir, ignore_errors=True)

            try:
                from core.ai_engine.rag_pipeline import tars_archive
                tars_archive.delete_source(book_id)
                if book:
                    local_p = book.get('local_path')
                    if local_p:
                        tars_archive.delete_source(Path(local_p).name)
            except Exception as vec_err:
                logger.warning(f"Vector cleanup notice for {book_id}: {vec_err}")

            await self.db['tasks'].delete_many({"linked_book_id": book_id})
            await self.db['planner'].delete_many({"linked_book_id": book_id})
            logger.info(f"Book deleted successfully: {book_id}")
            return True

        except Exception as e:
            logger.error(f"Delete Book Error for {book_id}: {e}")
            return False

    def format_added_date(self, added_at: Any) -> str:
        """Helper to format added_at cleanly regardless of timestamp type."""
        if isinstance(added_at, datetime):
            return added_at.strftime("%b %d, %Y")
        if isinstance(added_at, (int, float)):
            try: return datetime.fromtimestamp(added_at).strftime("%b %d, %Y")
            except Exception: return "Recently"
        if isinstance(added_at, str) and added_at.strip():
            return added_at[:10]
        return "Recently"

    async def get_library_inventory_summary(self, limit: int = 200, focus_book_id: Optional[str] = None) -> str:
        """Returns comprehensive catalog summary of library books for TARS AI prompt context."""
        if self.db is None:
            return "NO BOOKS CURRENTLY IN LIBRARY."
        try:
            cursor = self.db['books'].find({}, {"id": 1, "title": 1, "display_author": 1, "authors": 1, "file_type": 1, "genres": 1})\
                .sort("title", 1).limit(limit)
            books = await cursor.to_list(length=limit)
            if not books:
                return "NO BOOKS CURRENTLY IN LIBRARY."

            lines = ["CURRENT LIBRARY INVENTORY (AVAILABLE IN LOCAL DIGITAL ARCHIVE):"]
            for b in books:
                title = b.get('title', 'Untitled')
                author = b.get('display_author') or b.get('authors', 'Unknown')
                if isinstance(author, list) and author:
                    author = author[0].get('name', str(author[0])) if isinstance(author[0], dict) else str(author[0])
                ftype = (b.get('file_type') or 'E-Book').upper()
                is_focused = (focus_book_id and str(b.get('id')) == str(focus_book_id))
                prefix = "* [CURRENTLY FOCUSED] " if is_focused else "- "
                lines.append(f"{prefix}'{title}' by {author} ({ftype}) [Available]")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Inventory summary error: {e}")
            return "CURRENT LIBRARY INVENTORY UNAVAILABLE."

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

    def resolve_document_path(self, book_id: str, book_doc: Optional[dict] = None) -> Optional[str]:
        """
        Centralized helper to locate the physical book content file on disk.
        Searches local_path, static formats dictionary, and book folder directory.
        """
        # 1. From doc local_path
        if book_doc:
            lp = book_doc.get('local_path')
            if lp and Path(lp).exists():
                return str(Path(lp).resolve())

            # 2. From formats dict
            formats = book_doc.get('formats') or {}
            for fmt, url_path in formats.items():
                if url_path and '/static_books/' in url_path:
                    rel_part = url_path.split('/static_books/', 1)[1]
                    cand = settings.BASE_DIR / 'data' / 'books' / rel_part
                    if cand.exists():
                        return str(cand.resolve())

        # 3. Direct inspection of data/books/{book_id} folder
        if book_id:
            folder = settings.BASE_DIR / 'data' / 'books' / str(book_id)
            if folder.exists() and folder.is_dir():
                content_files = [
                    f for f in folder.iterdir()
                    if f.is_file() and f.suffix.lower() in ('.pdf', '.epub', '.pptx', '.ppt', '.docx', '.doc', '.txt', '.md')
                ]
                if content_files:
                    return str(content_files[0].resolve())

        return None
