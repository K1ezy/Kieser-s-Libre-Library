import re
import time
import shutil
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from bson import ObjectId

from core.config import settings
from core.database.repositories.base_repository import BaseRepository
from core.utils.security_utils import is_valid_book_id

logger = logging.getLogger("BOOK_REPOSITORY")

class BookRepository(BaseRepository):
    """
    Dedicated repository for book metadata, catalog queries, search indexing,
    shelving, reading statuses, and physical book file resolution.
    """

    _format_counts_cache: Optional[Dict[str, int]] = None
    _format_counts_cache_time: float = 0.0
    _total_count_cache: Optional[int] = None
    _total_count_cache_time: float = 0.0
    CACHE_TTL: float = 60.0  # seconds

    def invalidate_cache(self):
        """Clears in-memory catalog statistic caches."""
        self._format_counts_cache = None
        self._format_counts_cache_time = 0.0
        self._total_count_cache = None
        self._total_count_cache_time = 0.0

    async def get_total_book_count(self) -> int:
        """Returns the total number of books in the collection with TTL caching."""
        if self.db is None: return 0
        now = time.time()
        if self._total_count_cache is not None and (now - self._total_count_cache_time) < self.CACHE_TTL:
            return self._total_count_cache
        try:
            count = await self.db['books'].count_documents({})
            self._total_count_cache = count
            self._total_count_cache_time = now
            return count
        except Exception:
            return 0

    async def get_catalog_format_counts(self) -> Dict[str, int]:
        """Returns catalog format breakdown counts (epub, pdf, total) with parallel counts and TTL caching."""
        if self.db is None: return {"total": 0, "epub": 0, "pdf": 0}
        now = time.time()
        if self._format_counts_cache is not None and (now - self._format_counts_cache_time) < self.CACHE_TTL:
            return self._format_counts_cache.copy()
        try:
            total, epub, pdf = await asyncio.gather(
                self.db['books'].count_documents({}),
                self.db['books'].count_documents({"file_type": {"$regex": "epub", "$options": "i"}}),
                self.db['books'].count_documents({"file_type": {"$regex": "pdf", "$options": "i"}})
            )
            res = {"total": total, "epub": epub, "pdf": pdf}
            self._format_counts_cache = res
            self._format_counts_cache_time = now
            return res
        except Exception as e:
            logger.error(f"Format Counts Error: {e}")
            return {"total": 0, "epub": 0, "pdf": 0}

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

    async def get_books_by_ids(self, book_ids: List[str], projection: Optional[Dict[str, int]] = None) -> Dict[str, Dict[str, Any]]:
        """
        Batches multiple book lookups into a single indexed query.
        Returns a dictionary mapping book id to book document.
        """
        if self.db is None or not book_ids:
            return {}
        try:
            clean_ids = [str(bid).strip() for bid in book_ids if bid]
            if not clean_ids:
                return {}
            or_conditions: List[Dict[str, Any]] = [{"id": {"$in": clean_ids}}]
            valid_obj_ids = [ObjectId(bid) for bid in clean_ids if ObjectId.is_valid(bid)]
            if valid_obj_ids:
                or_conditions.append({"_id": {"$in": valid_obj_ids}})

            cursor = self.db['books'].find({"$or": or_conditions}, projection)
            docs = await cursor.to_list(length=len(clean_ids) * 2)
            result = {}
            for doc in docs:
                c_doc = self.clean_doc(doc)
                if c_doc:
                    if 'id' in c_doc:
                        result[str(c_doc['id'])] = c_doc
                    if '_id' in c_doc:
                        result[str(c_doc['_id'])] = c_doc
            return result
        except Exception as e:
            logger.error(f"Batch Get Books Error: {e}")
            return {}

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
            self.invalidate_cache()
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
            self.invalidate_cache()
            return res.modified_count > 0 or res.matched_count > 0
        except Exception as e:
            logger.error(f"Update Book Metadata Error: {e}")
            return False

    update_book = update_book_metadata


    @staticmethod
    def _cleanup_disk_and_vectors(book_dir: Path, books_root: Path, book_id: str, local_path: Optional[str]):
        """Helper to run synchronous disk cleanup and vector purge in a worker thread without blocking the event loop."""
        try:
            if book_dir != books_root and book_dir.is_relative_to(books_root) and book_dir.exists():
                shutil.rmtree(book_dir, ignore_errors=True)
        except Exception as fs_err:
            logger.warning(f"Disk cleanup notice for {book_id}: {fs_err}")

        try:
            from core.ai_engine.rag_pipeline import tars_archive
            tars_archive.delete_source(source_name=book_id, book_id=book_id)
            if local_path:
                source_name = Path(local_path).name
                if source_name and source_name != book_id:
                    tars_archive.delete_source(source_name=source_name, book_id=book_id)
        except Exception as vec_err:
            logger.warning(f"Vector cleanup notice for {book_id}: {vec_err}")

    async def delete_book(self, book_id: str) -> bool:
        """
        Deletes a book completely and instantly (<1-2 seconds):
        1. Validates book_id format to prevent path traversal attacks.
        2. Retrieves local path for complete cleanup.
        3. Concurrently purges MongoDB book, tasks, planner, and reading_progress records.
        4. Offloads disk directory removal and ChromaDB vector deletion to a worker thread.
        """
        if self.db is None or not book_id:
            return False

        # Security: Prevent path traversal in book_id
        if not is_valid_book_id(str(book_id)):
            logger.warning(f"Rejected delete_book with suspicious ID: {book_id}")
            return False

        try:
            book = await self.get_book_by_id(book_id)
            local_p = book.get('local_path') if book else None

            books_root = (settings.BASE_DIR / 'data' / 'books').resolve()
            book_dir = (books_root / book_id).resolve()

            # Concurrently delete MongoDB documents across collections
            await asyncio.gather(
                self.db['books'].delete_one({"id": book_id}),
                self.db['tasks'].delete_many({"linked_book_id": book_id}),
                self.db['planner'].delete_many({"linked_book_id": book_id}),
                self.db['reading_progress'].delete_many({"book_id": book_id}),
                self.db['annotations'].delete_many({"book_id": book_id}),
                self.db['user_favorites'].delete_many({"book_id": book_id}),
                self.db['faculty_requisitions'].update_many({"catalog_book_id": book_id}, {"$set": {"catalog_book_id": None}}),
                return_exceptions=True
            )

            # Offload blocking filesystem removal & ChromaDB vector purge to worker thread
            await asyncio.to_thread(
                self._cleanup_disk_and_vectors,
                book_dir, books_root, book_id, local_p
            )

            logger.info(f"Book deleted successfully in optimized workflow: {book_id}")
            self.invalidate_cache()
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

    async def get_library_inventory_summary(self, limit: int = 30, focus_book_id: Optional[str] = None) -> str:
        """Returns concise catalog summary of library books for TARS AI prompt context."""
        if self.db is None:
            return "NO BOOKS CURRENTLY IN LIBRARY."
        try:
            cursor = self.db['books'].find({}, {"id": 1, "title": 1, "display_author": 1, "authors": 1, "file_type": 1})\
                .sort("title", 1).limit(limit)
            books = await cursor.to_list(length=limit)
            if not books:
                return "NO BOOKS CURRENTLY IN LIBRARY."

            lines = ["AVAILABLE TITLES IN LIBRARY:"]
            for b in books:
                title = b.get('title', 'Untitled')
                author = b.get('display_author') or b.get('authors', 'Unknown')
                if isinstance(author, list) and author:
                    author = author[0].get('name', str(author[0])) if isinstance(author[0], dict) else str(author[0])
                ftype = (b.get('file_type') or 'E-Book').upper()
                lines.append(f"- '{title}' by {author} ({ftype})")
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

    async def toggle_book_favorite(self, book_id: str, user_id: Optional[str] = None) -> bool:
        """Toggles favorite status on a book. Scopes to user_favorites if user_id is provided."""
        if self.db is None or not book_id: return False
        try:
            if user_id:
                clean_user = str(user_id).strip()
                clean_book = str(book_id).strip()
                existing = await self.db['user_favorites'].find_one({"user_id": clean_user, "book_id": clean_book})
                if existing:
                    await self.db['user_favorites'].delete_one({"user_id": clean_user, "book_id": clean_book})
                    return False
                else:
                    await self.db['user_favorites'].insert_one({
                        "user_id": clean_user,
                        "book_id": clean_book,
                        "added_at": time.time()
                    })
                    return True
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

    async def get_or_resolve_page_count(self, book_id: str, book_doc: Optional[dict] = None) -> int:
        """
        Determines and caches true document page count across PDF, EPUB, DOCX, PPTX, and text formats.
        Persists newly discovered page count to MongoDB to avoid repeated disk reads.
        """
        # 1. Check in-memory doc
        if book_doc and isinstance(book_doc.get('page_count'), (int, float)) and book_doc['page_count'] > 0:
            return int(book_doc['page_count'])

        # 2. Check database record if book_doc wasn't provided or didn't have it
        if self.db is not None and book_id:
            try:
                db_doc = await self.get_book_by_id(book_id)
                if db_doc and isinstance(db_doc.get('page_count'), (int, float)) and db_doc['page_count'] > 0:
                    if book_doc:
                        book_doc['page_count'] = int(db_doc['page_count'])
                    return int(db_doc['page_count'])
            except Exception:
                pass

        # 3. Resolve physical file path on disk
        file_path_str = self.resolve_document_path(book_id, book_doc)
        if not file_path_str or not Path(file_path_str).exists():
            return 0

        p = Path(file_path_str)
        ext = p.suffix.lower()
        pages = 0

        try:
            if ext == '.pdf':
                try:
                    import fitz
                    with fitz.open(str(p)) as doc:
                        pages = max(1, doc.page_count)
                except Exception:
                    try:
                        from pypdf import PdfReader
                        pages = max(1, len(PdfReader(str(p)).pages))
                    except Exception:
                        pages = 0
            elif ext in ('.pptx', '.ppt'):
                try:
                    from pptx import Presentation
                    pages = max(1, len(Presentation(str(p)).slides))
                except Exception:
                    pages = 0
            elif ext == '.docx':
                try:
                    import docx
                    doc = docx.Document(str(p))
                    total_words = sum(len(para.text.split()) for para in doc.paragraphs)
                    pages = max(1, round(total_words / 250))
                except Exception:
                    pages = 0
            elif ext == '.epub':
                try:
                    import ebooklib
                    from ebooklib import epub
                    from bs4 import BeautifulSoup
                    book = epub.read_epub(str(p))
                    total_words = 0
                    item_count = 0
                    for item in book.get_items():
                        if item.get_type() == ebooklib.ITEM_DOCUMENT:
                            item_count += 1
                            soup = BeautifulSoup(item.get_content(), 'html.parser')
                            total_words += len(soup.get_text().split())
                    if total_words > 0:
                        pages = max(1, round(total_words / 250))
                    elif item_count > 0:
                        pages = item_count
                except Exception:
                    pages = 0
            elif ext in ('.txt', '.md'):
                try:
                    with open(str(p), 'r', encoding='utf-8', errors='ignore') as f:
                        words = len(f.read().split())
                    pages = max(1, round(words / 250))
                except Exception:
                    pages = 0
        except Exception as e:
            logger.debug(f"Could not calculate page count for {book_id}: {e}")

        # 4. Cache resolved count in MongoDB and book_doc
        if pages > 0:
            if book_doc:
                book_doc['page_count'] = pages
            if self.db is not None and book_id:
                try:
                    await self.update_book_metadata(book_id, {"page_count": pages})
                except Exception:
                    pass

        return pages

