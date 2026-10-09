from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Optional, Any, Dict, List
from bson import ObjectId


def sanitize_mongo_doc(data: Any) -> Any:
    """Recursively converts BSON ObjectId and other non-JSON types to strings."""
    if isinstance(data, dict):
        return {k: sanitize_mongo_doc(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_mongo_doc(item) for item in data]
    elif isinstance(data, ObjectId):
        return str(data)
    return data


class BaseRepository:
    """Base class for all domain-specific MongoDB repositories."""
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None):
        self.db = db

    def set_db(self, db: AsyncIOMotorDatabase):
        self.db = db

    @staticmethod
    def clean_doc(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Sanitizes a single MongoDB document, ensuring all ObjectIds are strings."""
        if doc is None:
            return None
        return sanitize_mongo_doc(doc)

    @staticmethod
    def clean_docs(docs: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Sanitizes a list of MongoDB documents, ensuring all ObjectIds are strings."""
        if not docs:
            return []
        return [sanitize_mongo_doc(d) for d in docs]
