import time
import re
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from core.database.mongo_manager import mongo_db

logger = logging.getLogger("PROGRESS_ROUTER")

progress_router = APIRouter(prefix="/api/progress", tags=["Progress"])

class ProgressSyncRequest(BaseModel):
    book_id: str = Field(..., description="Unique alphanumeric identifier of the book")
    user_id: Optional[str] = Field("guest", description="User ID or session identifier")
    current_page: int = Field(1, ge=1, description="Active page or virtual location index")
    total_pages: int = Field(1, ge=1, description="Total book pages or virtual locations")
    progress_percent: Optional[float] = Field(None, ge=0.0, le=100.0, description="Reading percentage")
    cfi: Optional[str] = Field(None, description="EPUB Canonical Fragment Identifier (CFI)")
    status: Optional[str] = Field("reading", description="Reading status: reading, completed, want_to_read")
    client_timestamp: Optional[float] = Field(None, description="Client-side epoch timestamp in seconds")

@progress_router.post("/sync")
async def sync_reading_progress(payload: ProgressSyncRequest):
    """
    Authoritative, high-throughput endpoint for asynchronous reading progress persistence.
    Called automatically by reader engines (EPUB.js, PDF, DOCX/PPTX scroll trackers).
    """
    book_id = payload.book_id.strip()
    if not re.match(r'^[a-zA-Z0-9_-]+$', book_id):
        raise HTTPException(status_code=400, detail="Invalid book identifier format.")

    user_id = (payload.user_id or "guest").strip()
    tot_pages = max(1, payload.total_pages)
    cur_page = max(1, min(tot_pages, payload.current_page))
    
    pct = payload.progress_percent
    if pct is None:
        pct = round((cur_page / max(tot_pages, 1)) * 100.0, 1) if tot_pages > 0 else 0.0
    pct = max(0.0, min(100.0, round(float(pct), 1)))

    status = payload.status or "reading"
    if cur_page >= tot_pages and tot_pages > 1:
        status = "completed"
    elif status not in ("reading", "completed", "want_to_read"):
        status = "reading"

    logger.info(
        f"[ProgressSync] book={book_id} user={user_id} page={cur_page}/{tot_pages} "
        f"({pct}%) cfi={'Yes' if payload.cfi else 'None'} status={status}"
    )

    success = await mongo_db.save_reading_progress(
        user_id=user_id,
        book_id=book_id,
        current_page=cur_page,
        total_pages=tot_pages,
        status=status,
        cfi=payload.cfi,
        client_timestamp=payload.client_timestamp,
        progress_percent=pct
    )

    if success:
        try:
            await mongo_db.update_book_reading_status(book_id, status)
        except Exception:
            pass

    return {
        "status": "ok" if success else "error",
        "book_id": book_id,
        "user_id": user_id,
        "current_page": cur_page,
        "total_pages": tot_pages,
        "progress_percent": pct,
        "cfi": payload.cfi,
        "reading_status": status,
        "synced_at": time.time()
    }

@progress_router.get("/{book_id}")
async def get_book_progress(book_id: str, user_id: Optional[str] = "guest"):
    """Fetches saved persistent reading progress for a given book and user."""
    book_id = book_id.strip()
    if not re.match(r'^[a-zA-Z0-9_-]+$', book_id):
        raise HTTPException(status_code=400, detail="Invalid book identifier format.")

    user_id = (user_id or "guest").strip()
    prog = await mongo_db.get_reading_progress(user_id, book_id)
    if not prog:
        return {
            "book_id": book_id,
            "user_id": user_id,
            "current_page": 1,
            "total_pages": 1,
            "progress_percent": 0.0,
            "cfi": None,
            "status": "want_to_read"
        }

    return {
        "book_id": book_id,
        "user_id": user_id,
        "current_page": prog.get("current_page", 1),
        "total_pages": prog.get("total_pages", 1),
        "progress_percent": prog.get("progress_percent", 0.0),
        "cfi": prog.get("cfi"),
        "status": prog.get("status", "reading"),
        "last_read_at": prog.get("last_read_at")
    }
