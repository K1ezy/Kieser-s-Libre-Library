from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Optional

class BaseRepository:
    """Base class for all domain-specific MongoDB repositories."""
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None):
        self.db = db

    def set_db(self, db: AsyncIOMotorDatabase):
        self.db = db
