from fastapi import APIRouter, Response, Request
from xml.sax.saxutils import escape
from datetime import datetime, timezone
from typing import List, Dict, Any
import base64
import bcrypt
import re
from core.database.mongo_manager import mongo_db
from core.config import settings

opds_router = APIRouter(prefix="/opds", tags=["OPDS"])

async def check_opds_auth(request: Request) -> bool:
    """
    Verifies HTTP Basic authentication or Bearer token for OPDS access.
    Compatible with KOReader, Moon+ Reader, Apple Books, and standard e-readers.
    """
    user_count = await mongo_db.get_total_user_count()
    if user_count == 0:
        # Permit access during initial zero-user setup
        return True

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return False

    if auth_header.startswith("Basic "):
        try:
            b64_creds = auth_header[6:].strip()
            decoded = base64.b64decode(b64_creds).decode("utf-8")
            if ":" in decoded:
                username, password = decoded.split(":", 1)
                matched_user = await mongo_db.get_user_by_identifier(username.strip())
                if matched_user and matched_user.get("hashed_password"):
                    hp = matched_user["hashed_password"]
                    hp_bytes = hp.encode("utf-8") if isinstance(hp, str) else hp
                    if bcrypt.checkpw(password.strip().encode("utf-8"), hp_bytes):
                        return True
        except Exception:
            pass

    elif auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        from core.auth.jwt_handler import verify_token
        if verify_token(token):
            return True

    return False

def unauthorized_opds_response() -> Response:
    return Response(
        content="Unauthorized: Access to OPDS catalog requires valid Libre-Library credentials.",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Libre-Library OPDS Catalog"'},
        media_type="text/plain"
    )

def format_iso(ts: Any) -> str:
    """Formats timestamp into valid ISO-8601 string."""
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        elif isinstance(ts, datetime):
            return ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_mime_type(file_type: str, url: str) -> str:
    """Returns correct MIME type for OPDS acquisition links."""
    ft = (file_type or "").lower()
    if 'epub' in ft or url.endswith('.epub'):
        return "application/epub+zip"
    elif 'pdf' in ft or url.endswith('.pdf'):
        return "application/pdf"
    elif 'docx' in ft or url.endswith('.docx'):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"

def generate_entry_xml(book: Dict[str, Any], base_url: str) -> str:
    """Generates an Atom/OPDS entry for a single book."""
    raw_id = str(book.get('id', ''))
    if not re.match(r'^[a-zA-Z0-9_-]+$', raw_id):
        return ""

    b_id = escape(raw_id)
    title = escape(str(book.get('title', 'Untitled')))
    author = escape(str(book.get('display_author') or 'Unknown Author'))
    summary = escape(str(book.get('description') or 'No synopsis available.'))
    updated = format_iso(book.get('added_at'))
    ftype = book.get('file_type', 'EPUB')

    # Acquisition links (e-book download)
    acq_links = []
    formats = book.get('formats') or {}
    for fmt_name, fmt_path in formats.items():
        if fmt_path:
            full_url = f"{base_url}{fmt_path}" if fmt_path.startswith('/') else fmt_path
            mime = get_mime_type(fmt_name, fmt_path)
            acq_links.append(f'<link rel="http://opds-spec.org/acquisition" href="{escape(full_url)}" type="{mime}" />')

    if not acq_links and book.get('local_path'):
        # Fallback to direct download
        mime = get_mime_type(ftype, book.get('local_path', ''))
        download_url = f"{base_url}/read/{b_id}"
        acq_links.append(f'<link rel="http://opds-spec.org/acquisition" href="{escape(download_url)}" type="{mime}" />')

    # Thumbnail link
    cover_url = book.get('cover_image') or f"/static_books/{b_id}/cover.jpg"
    if cover_url.startswith('/'):
        cover_url = f"{base_url}{cover_url}"
    thumb_link = f'<link rel="http://opds-spec.org/image/thumbnail" href="{escape(cover_url)}" type="image/jpeg" />'
    image_link = f'<link rel="http://opds-spec.org/image" href="{escape(cover_url)}" type="image/jpeg" />'

    # Categories
    categories = []
    for g in book.get('genres', []) or book.get('subjects', []):
        categories.append(f'<category term="{escape(str(g))}" label="{escape(str(g))}" />')

    links_xml = "\n    ".join(acq_links + [thumb_link, image_link])
    cats_xml = "\n    ".join(categories)

    return f"""  <entry>
    <title>{title}</title>
    <id>urn:uuid:{b_id}</id>
    <updated>{updated}</updated>
    <author>
      <name>{author}</name>
    </author>
    <summary>{summary[:400]}</summary>
    {cats_xml}
    {links_xml}
  </entry>"""

@opds_router.get("", response_class=Response)
@opds_router.get("/v1.2/catalog.xml", response_class=Response)
async def opds_root(request: Request):
    """OPDS Root Navigation Catalog (Auth Protected)."""
    if not await check_opds_auth(request):
        return unauthorized_opds_response()

    base_url = str(request.base_url).rstrip('/')
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">
  <id>urn:uuid:libre-library-root</id>
  <title>Libre-Library E-Book Catalog</title>
  <updated>{now}</updated>
  <icon>{base_url}/static/default_cover.png</icon>
  <author>
    <name>Libre-Library</name>
  </author>
  
  <link rel="self" href="{base_url}/opds/v1.2/catalog.xml" type="application/atom+xml;profile=opds-catalog;kind=navigation" />
  <link rel="start" href="{base_url}/opds/v1.2/catalog.xml" type="application/atom+xml;profile=opds-catalog;kind=navigation" />
  <link rel="search" href="{base_url}/opds/v1.2/search.xml?q={{searchTerms}}" type="application/atom+xml" />

  <entry>
    <title>All Books</title>
    <id>urn:uuid:libre-library-all-books</id>
    <updated>{now}</updated>
    <content type="text">Browse all documents and books in Libre-Library.</content>
    <link rel="subsection" href="{base_url}/opds/v1.2/all.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition" />
  </entry>

  <entry>
    <title>Recent Additions</title>
    <id>urn:uuid:libre-library-recent</id>
    <updated>{now}</updated>
    <content type="text">Latest materials added to the digital collection.</content>
    <link rel="subsection" href="{base_url}/opds/v1.2/new.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition" />
  </entry>
</feed>"""
    return Response(content=xml, media_type="application/atom+xml;profile=opds-catalog;kind=navigation;charset=utf-8")

@opds_router.get("/v1.2/all.xml", response_class=Response)
async def opds_all_books(request: Request):
    """OPDS Acquisition Feed: All Books (Auth Protected)."""
    if not await check_opds_auth(request):
        return unauthorized_opds_response()

    base_url = str(request.base_url).rstrip('/')
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    books = await mongo_db.get_all_books(limit=500, sort_by='newest') or []
    entries = [generate_entry_xml(b, base_url) for b in books if b]
    valid_entries = [e for e in entries if e]

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">
  <id>urn:uuid:libre-library-all-books</id>
  <title>All Books - Libre-Library</title>
  <updated>{now}</updated>
  <link rel="self" href="{base_url}/opds/v1.2/all.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition" />
  <link rel="start" href="{base_url}/opds/v1.2/catalog.xml" type="application/atom+xml;profile=opds-catalog;kind=navigation" />
  <link rel="up" href="{base_url}/opds/v1.2/catalog.xml" type="application/atom+xml;profile=opds-catalog;kind=navigation" />
  
{chr(10).join(valid_entries)}
</feed>"""
    return Response(content=xml, media_type="application/atom+xml;profile=opds-catalog;kind=acquisition;charset=utf-8")

@opds_router.get("/v1.2/new.xml", response_class=Response)
async def opds_recent_books(request: Request):
    """OPDS Acquisition Feed: Recent Additions (Auth Protected)."""
    if not await check_opds_auth(request):
        return unauthorized_opds_response()

    base_url = str(request.base_url).rstrip('/')
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    books = await mongo_db.get_recent_books(limit=30) or []
    entries = [generate_entry_xml(b, base_url) for b in books if b]
    valid_entries = [e for e in entries if e]

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">
  <id>urn:uuid:libre-library-recent</id>
  <title>Recent Additions - Libre-Library</title>
  <updated>{now}</updated>
  <link rel="self" href="{base_url}/opds/v1.2/new.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition" />
  <link rel="start" href="{base_url}/opds/v1.2/catalog.xml" type="application/atom+xml;profile=opds-catalog;kind=navigation" />
  <link rel="up" href="{base_url}/opds/v1.2/catalog.xml" type="application/atom+xml;profile=opds-catalog;kind=navigation" />
  
{chr(10).join(valid_entries)}
</feed>"""
    return Response(content=xml, media_type="application/atom+xml;profile=opds-catalog;kind=acquisition;charset=utf-8")

@opds_router.get("/v1.2/search.xml", response_class=Response)
async def opds_search(request: Request, q: str = ""):
    """OPDS Search Feed (Auth Protected)."""
    if not await check_opds_auth(request):
        return unauthorized_opds_response()

    base_url = str(request.base_url).rstrip('/')
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    books = await mongo_db.search_books(q, limit=30) if q else []
    entries = [generate_entry_xml(b, base_url) for b in books if b]
    valid_entries = [e for e in entries if e]

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">
  <id>urn:uuid:libre-library-search-{escape(q)}</id>
  <title>Search: {escape(q)}</title>
  <updated>{now}</updated>
  <link rel="self" href="{base_url}/opds/v1.2/search.xml?q={escape(q)}" type="application/atom+xml;profile=opds-catalog;kind=acquisition" />
  <link rel="up" href="{base_url}/opds/v1.2/catalog.xml" type="application/atom+xml;profile=opds-catalog;kind=navigation" />
  
{chr(10).join(valid_entries)}
</feed>"""
    return Response(content=xml, media_type="application/atom+xml;profile=opds-catalog;kind=acquisition;charset=utf-8")

