import time
import logging
from typing import Optional, List, Dict, Any
from core.database.repositories.base_repository import BaseRepository

logger = logging.getLogger("CHAT_REPOSITORY")

class ChatRepository(BaseRepository):
    """
    Dedicated repository for conversational message history, chat sessions,
    and metadata persistence.
    """

    @property
    def collection(self):
        """Reference to the primary chat_history messages collection."""
        if self.db is not None:
            return self.db["chat_history"]
        return None

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
        book_id: Optional[str] = None,
        book_title: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        if self.db is None: return
        try:
            update_data: Dict[str, Any] = {
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
                except Exception:
                    pass

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
