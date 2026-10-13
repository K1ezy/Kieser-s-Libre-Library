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
    theme: Optional[str] = Field(None, description="Reader theme: light, sepia, dark, black")
    font_size: Optional[int] = Field(None, ge=10, le=40, description="Preferred font size in px")
    font_family: Optional[str] = Field(None, description="Preferred font family: sans, serif, dyslexic")
    line_height: Optional[float] = Field(None, ge=1.0, le=3.0, description="Line height multiplier")

class ReaderPreferencesPayload(BaseModel):
    theme: Optional[str] = Field("light", description="Reader theme: light, sepia, dark, black")
    font_size: Optional[int] = Field(16, ge=10, le=40, description="Preferred font size in px")
    font_family: Optional[str] = Field("sans", description="Preferred font family: sans, serif, dyslexic")
    line_height: Optional[float] = Field(1.65, ge=1.0, le=3.0, description="Line height multiplier")

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
        f"({pct}%) cfi={'Yes' if payload.cfi else 'None'} status={status} theme={payload.theme}"
    )

    success = await mongo_db.save_reading_progress(
        user_id=user_id,
        book_id=book_id,
        current_page=cur_page,
        total_pages=tot_pages,
        status=status,
        cfi=payload.cfi,
        client_timestamp=payload.client_timestamp,
        progress_percent=pct,
        theme=payload.theme,
        font_size=payload.font_size,
        font_family=payload.font_family,
        line_height=payload.line_height
    )

    if success:
        try:
            await mongo_db.update_book_reading_status(book_id, status)
        except Exception:
            pass

        # Also update user global appearance settings if preferences were provided
        if payload.theme or payload.font_size or payload.font_family or payload.line_height:
            try:
                pref_updates = {}
                if payload.theme: pref_updates["theme"] = payload.theme
                if payload.font_size is not None: pref_updates["font_size"] = payload.font_size
                if payload.font_family: pref_updates["font_family"] = payload.font_family
                if payload.line_height is not None: pref_updates["line_height"] = payload.line_height
                await mongo_db.save_reader_preferences(user_id, pref_updates)
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
        "theme": payload.theme,
        "font_size": payload.font_size,
        "font_family": payload.font_family,
        "line_height": payload.line_height,
        "synced_at": time.time()
    }

@progress_router.get("/preferences/{user_id}")
async def get_user_reader_preferences(user_id: str):
    """Fetches user global reader appearance preferences."""
    clean_user = user_id.strip() if user_id else "guest"
    prefs = await mongo_db.get_reader_preferences(clean_user)
    return {"user_id": clean_user, "preferences": prefs}

@progress_router.post("/preferences/{user_id}")
async def save_user_reader_preferences(user_id: str, payload: ReaderPreferencesPayload):
    """Saves user global reader appearance preferences across sessions."""
    clean_user = user_id.strip() if user_id else "guest"
    updates = payload.model_dump(exclude_none=True) if hasattr(payload, 'model_dump') else payload.dict(exclude_none=True)
    success = await mongo_db.save_reader_preferences(clean_user, updates)
    return {"status": "ok" if success else "error", "user_id": clean_user, "preferences": updates}

@progress_router.get("/{book_id}")
async def get_book_progress(book_id: str, user_id: Optional[str] = "guest"):
    """Fetches saved persistent reading progress for a given book and user."""
    book_id = book_id.strip()
    if not re.match(r'^[a-zA-Z0-9_-]+$', book_id):
        raise HTTPException(status_code=400, detail="Invalid book identifier format.")

    user_id = (user_id or "guest").strip()
    prog = await mongo_db.get_reading_progress(user_id, book_id)
    if not prog:
        global_prefs = await mongo_db.get_reader_preferences(user_id)
        return {
            "book_id": book_id,
            "user_id": user_id,
            "current_page": 1,
            "total_pages": 1,
            "progress_percent": 0.0,
            "cfi": None,
            "status": "want_to_read",
            "theme": global_prefs.get("theme", "light"),
            "font_size": global_prefs.get("font_size", 16),
            "font_family": global_prefs.get("font_family", "sans"),
            "line_height": global_prefs.get("line_height", 1.65)
        }

    return {
        "book_id": book_id,
        "user_id": user_id,
        "current_page": prog.get("current_page", 1),
        "total_pages": prog.get("total_pages", 1),
        "progress_percent": prog.get("progress_percent", 0.0),
        "cfi": prog.get("cfi"),
        "status": prog.get("status", "reading"),
        "theme": prog.get("theme", "light"),
        "font_size": prog.get("font_size", 16),
        "font_family": prog.get("font_family", "sans"),
        "line_height": prog.get("line_height", 1.65),
        "last_read_at": prog.get("last_read_at")
    }
