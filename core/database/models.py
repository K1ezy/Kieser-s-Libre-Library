from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
import time
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid_str() -> str:
    return str(uuid.uuid4())


# =====================================================================
# 1. CHAT & CONVERSATION MODELS (100% backward-compatible)
# =====================================================================
class Message(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    id: str = Field(default_factory=_uuid_str)
    role: str  # "system", "user", "assistant"
    content: str
    timestamp: datetime = Field(default_factory=_utc_now)


class ChatSession(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    session_id: str = Field(default_factory=_uuid_str)
    user_id: Optional[str] = None
    title: str = "New Conversation"
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    messages: List[Message] = Field(default_factory=list)


# =====================================================================
# 2. BOOK CATALOG & INGESTION MODELS
# =====================================================================
class BookMetadata(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    id: str = Field(default_factory=_uuid_str)
    title: str
    authors: List[str] = Field(default_factory=lambda: ["Unknown"])
    display_author: str = "Unknown"
    description: str = ""
    subjects: List[str] = Field(default_factory=list)
    isbn: Optional[str] = None
    shelf: Optional[str] = "General"
    added_at: float = Field(default_factory=time.time)
    file_type: str = "PDF"
    formats: Dict[str, str] = Field(default_factory=dict)
    local_path: str = ""
    cover_image: str = "/static/default_cover.svg"
    status: str = "Ready"
    indexing_status: Literal["indexed", "pending", "failed"] = "pending"
    indexing_error: Optional[str] = None
    file_size: int = 0
    chunk_count: int = 0
    file_signature: Optional[str] = None
    is_indexed: bool = False

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: str) -> str:
        cleaned = (v or "").strip()
        return cleaned if cleaned else "Untitled Document"


# =====================================================================
# 3. USER & 4-TIER RBAC MODELS
# =====================================================================
RoleType = Literal["Student", "Faculty", "Librarian", "Admin IT"]


class UserAccount(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    id: str = Field(default_factory=_uuid_str)
    username: str
    email: Optional[str] = None
    full_name: str = ""
    role: RoleType = "Student"
    institutional_id: Optional[str] = None
    department: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool = True
    token_version: int = 1
    created_at: datetime = Field(default_factory=_utc_now)
    last_login: Optional[datetime] = None


# =====================================================================
# 4. READING PROGRESS, ANNOTATIONS, PLANNER, ATTENDANCE & REQUISITIONS
# =====================================================================
class ReadingProgress(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    user_id: str
    book_id: str
    current_page: int = 1
    total_pages: int = 1
    percentage: float = 0.0
    cfi: Optional[str] = None
    status: Literal["reading", "completed", "on_hold", "plan_to_read"] = "reading"
    updated_at: datetime = Field(default_factory=_utc_now)


class ReaderAnnotation(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    id: str = Field(default_factory=_uuid_str)
    user_id: str
    book_id: str
    page: Optional[int] = 1
    cfi_range: Optional[str] = None
    highlighted_text: str = ""
    note: str = ""
    color: str = "yellow"
    created_at: datetime = Field(default_factory=_utc_now)


class PlannerTask(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    id: str = Field(default_factory=_uuid_str)
    user_id: str
    title: str
    description: str = ""
    book_id: Optional[str] = None
    due_date: Optional[str] = None
    priority: Literal["low", "medium", "high"] = "medium"
    completed: bool = False
    created_at: datetime = Field(default_factory=_utc_now)


class AttendanceLog(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    id: str = Field(default_factory=_uuid_str)
    user_id: str
    institutional_id: Optional[str] = None
    full_name: str = ""
    role: str = "Student"
    purpose: str = "Study / Reading"
    check_in: datetime = Field(default_factory=_utc_now)
    check_out: Optional[datetime] = None


class RequisitionRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    id: str = Field(default_factory=_uuid_str)
    requester_id: str
    requester_name: str = ""
    requester_role: str = "Student"
    title: str
    author: str = ""
    isbn: Optional[str] = None
    reason: str = ""
    status: Literal["pending", "approved", "acquired", "rejected"] = "pending"
    reviewed_by: Optional[str] = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)