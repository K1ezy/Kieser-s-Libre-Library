import time
import re
import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from core.database.mongo_manager import mongo_db
from core.ai_engine.llm_engine import tars_engine

logger = logging.getLogger("ANNOTATIONS_ROUTER")

annotations_router = APIRouter(prefix="/api/annotations", tags=["Annotations"])


class CreateAnnotationRequest(BaseModel):
    book_id: str = Field(..., description="Unique alphanumeric identifier of the book")
    user_id: Optional[str] = Field("guest", description="User identifier")
    selected_text: str = Field(..., description="The highlighted text excerpt")
    color: Optional[str] = Field("yellow", description="Highlight color: yellow, green, blue, pink, purple")
    cfi_range: Optional[str] = Field(None, description="EPUB Canonical Fragment Identifier range")
    page_number: Optional[int] = Field(1, description="Active page number in document")
    rects: Optional[List[Dict[str, Any]]] = Field(None, description="Bounding client rects for PDF rendering")
    note: Optional[str] = Field("", description="Optional margin note or comment")


class UpdateAnnotationRequest(BaseModel):
    color: Optional[str] = Field(None, description="Updated highlight color")
    note: Optional[str] = Field(None, description="Updated student note text")


class ExplainPassageRequest(BaseModel):
    passage_text: str = Field(..., description="Passage or excerpt to explain")
    book_id: Optional[str] = Field(None, description="Book ID for contextual reference")
    context_title: Optional[str] = Field(None, description="Title of the active document")


@annotations_router.get("/{book_id}")
async def get_annotations_for_book(book_id: str, user_id: Optional[str] = "guest"):
    """Fetches all highlights and notes created by the user for this book."""
    clean_book = book_id.strip()
    if not re.match(r'^[a-zA-Z0-9_-]+$', clean_book):
        raise HTTPException(status_code=400, detail="Invalid book identifier format.")

    clean_user = (user_id or "guest").strip()
    annotations = await mongo_db.get_book_annotations(clean_user, clean_book)
    return {
        "status": "ok",
        "book_id": clean_book,
        "user_id": clean_user,
        "count": len(annotations),
        "annotations": annotations
    }


@annotations_router.post("/")
async def create_annotation(payload: CreateAnnotationRequest):
    """Creates and persists a new text highlight or note."""
    clean_book = payload.book_id.strip()
    if not re.match(r'^[a-zA-Z0-9_-]+$', clean_book):
        raise HTTPException(status_code=400, detail="Invalid book identifier format.")

    clean_user = (payload.user_id or "guest").strip()
    res = await mongo_db.create_annotation(
        user_id=clean_user,
        book_id=clean_book,
        selected_text=payload.selected_text,
        color=payload.color or "yellow",
        cfi_range=payload.cfi_range,
        page_number=payload.page_number,
        rects=payload.rects,
        note=payload.note or ""
    )

    if not res.get("success"):
        raise HTTPException(status_code=500, detail=res.get("error", "Failed to create annotation"))

    return {
        "status": "ok",
        "annotation": res.get("annotation")
    }


@annotations_router.put("/{annotation_id}")
async def update_annotation(annotation_id: str, payload: UpdateAnnotationRequest):
    """Modifies the color or note of an existing highlight."""
    clean_id = annotation_id.strip()
    updates = {}
    if payload.color is not None:
        updates["color"] = payload.color
    if payload.note is not None:
        updates["note"] = payload.note

    success = await mongo_db.update_annotation(clean_id, updates)
    if not success:
        raise HTTPException(status_code=404, detail="Annotation not found or could not be updated")

    updated_doc = await mongo_db.get_annotation(clean_id)
    return {
        "status": "ok",
        "annotation": updated_doc
    }


@annotations_router.delete("/{annotation_id}")
async def delete_annotation(annotation_id: str, user_id: Optional[str] = None):
    """Deletes an annotation by ID."""
    clean_id = annotation_id.strip()
    success = await mongo_db.delete_annotation(clean_id, user_id=user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Annotation not found or delete unauthorized")

    return {"status": "ok", "deleted_id": clean_id}


@annotations_router.get("/{book_id}/export")
async def export_annotations_markdown(book_id: str, user_id: Optional[str] = "guest"):
    """Generates and downloads a clean Markdown study guide of all student notes."""
    clean_book = book_id.strip()
    if not re.match(r'^[a-zA-Z0-9_-]+$', clean_book):
        raise HTTPException(status_code=400, detail="Invalid book identifier format.")

    clean_user = (user_id or "guest").strip()
    annotations = await mongo_db.get_book_annotations(clean_user, clean_book)
    
    # Try resolving title
    book_title = "Document"
    try:
        book_doc = await mongo_db.get_book_details(clean_book)
        if book_doc and book_doc.get("title"):
            book_title = book_doc["title"]
    except Exception:
        pass

    md_content = mongo_db.generate_annotations_markdown(annotations, book_title=book_title)
    filename = f"notes_{clean_book}_{int(time.time())}.md"

    return Response(
        content=md_content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@annotations_router.post("/explain")
async def explain_passage(payload: ExplainPassageRequest):
    """
    Rapid, in-reader Socratic explanation of a selected passage (2-3 sentences).
    Provides instant academic clarity without requiring full page navigation.
    """
    passage = payload.passage_text.strip()
    if not passage:
        raise HTTPException(status_code=400, detail="Passage text cannot be empty.")

    title_ref = f" from '{payload.context_title}'" if payload.context_title else ""
    prompt = (
        f"You are TARS, the Socratic AI Academic Librarian at Libre-Library. "
        f"A university student highlighted the following passage{title_ref}:\n\n"
        f"\"{passage[:800]}\"\n\n"
        f"Provide a clear, pedagogical, 2-to-3 sentence explanation explaining what this concept means "
        f"in simple terms. Be encouraging and concise."
    )

    try:
        response_chunks = []
        messages = [
            {"role": "system", "content": "You are TARS, a concise and brilliant academic AI assistant. Keep explanations strictly within 2 to 3 sentences."},
            {"role": "user", "content": prompt}
        ]
        async for chunk in tars_engine.stream_response(messages, max_tokens=150):
            response_chunks.append(chunk)

        explanation = "".join(response_chunks).strip()
        if not explanation:
            explanation = "This passage introduces key concepts foundational to the topic. Consider breaking down the main terminology to understand its broader academic application."

        return {
            "status": "ok",
            "passage": passage,
            "explanation": explanation
        }
    except Exception as e:
        logger.error(f"Error generating passage explanation: {e}")
        return {
            "status": "fallback",
            "passage": passage,
            "explanation": "This excerpt highlights a central concept in the text. For a comprehensive walkthrough, explore this passage in the TARS AI conversational workstation."
        }
