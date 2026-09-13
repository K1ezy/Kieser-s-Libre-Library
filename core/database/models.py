from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
import uuid

class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str  # "system", "user", "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ChatSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = "New Conversation"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    messages: List[Message] = []
    
    class Config:
        # This ensures ObjectId handling if we need it later
        arbitrary_types_allowed = True