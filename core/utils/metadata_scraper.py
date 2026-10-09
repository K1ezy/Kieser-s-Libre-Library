import logging
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
import urllib.parse
import httpx

logger = logging.getLogger("METADATA_SCRAPER")

def extract_local_file_metadata(file_path: Path) -> Dict[str, Any]:
    """
    Extracts embedded metadata and covers directly from local EPUB or PDF files.
    """
    meta = {
        "title": None,
        "authors": [],
        "description": "",
        "subjects": [],
        "language": "en"
    }

    if not file_path.exists() or file_path.stat().st_size == 0:
        return meta

    ext = file_path.suffix.lower()

    if ext == '.epub':
        try:
            import ebooklib
            from ebooklib import epub
            from bs4 import BeautifulSoup

            book = epub.read_epub(str(file_path))

            # 1. Title
            titles = book.get_metadata('DC', 'title')
            if titles:
                meta['title'] = titles[0][0].strip()

            # 2. Authors
            creators = book.get_metadata('DC', 'creator')
            if creators:
                meta['authors'] = [c[0].strip() for c in creators if c[0].strip()]

            # 3. Description
            descriptions = book.get_metadata('DC', 'description')
            if descriptions:
                soup = BeautifulSoup(descriptions[0][0], 'html.parser')
                meta['description'] = soup.get_text().strip()

            # 4. Subjects / Categories
            subjects = book.get_metadata('DC', 'subject')
            if subjects:
                meta['subjects'] = [s[0].strip() for s in subjects if s[0].strip()]

            # 5. Language
            langs = book.get_metadata('DC', 'language')
            if langs:
                meta['language'] = langs[0][0].strip()

            # 6. Extract Cover Image if available
            cover_dest = file_path.parent / "cover.jpg"
            if not cover_dest.exists():
                from core.utils.cover_manager import cover_manager
                cover_manager.extract_or_generate_cover(
                    file_path=file_path,
                    output_path=cover_dest,
                    title=meta.get('title') or '',
                    author=(meta.get('authors') or [''])[0],
                    file_type='EPUB'
                )

        except Exception as e:
            logger.warning(f"Local EPUB metadata extraction notice: {e}")

    elif ext == '.pdf':
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(file_path))
            info = reader.metadata or {}
            
            if info.title and info.title.strip():
                meta['title'] = info.title.strip()
            if info.author and info.author.strip():
                # Split multiple authors if separated by comma or semicolon
                author_str = info.author.strip()
                if ',' in author_str and not author_str.endswith(','):
                    meta['authors'] = [a.strip() for a in author_str.split(',') if a.strip()]
                else:
                    meta['authors'] = [author_str]
            if info.subject and info.subject.strip():
                meta['subjects'] = [s.strip() for s in info.subject.split(',') if s.strip()]

        except Exception as e:
            logger.warning(f"Local PDF metadata extraction notice: {e}")

    return meta


async def fetch_online_metadata(query_title: str, query_author: str = "") -> Optional[Dict[str, Any]]:
    """
    Asynchronously queries Open Library and Google Books API for high-quality
    cover art, official titles, author biographies, categories, and synopses.
    Zero API keys required for Open Library.
    """
    if not query_title or len(query_title.strip()) < 2:
        return None

    clean_title = query_title.strip()
    
    # 1. Primary: Open Library Search API
    try:
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            params = {"title": clean_title, "limit": 1}
            if query_author:
                params["author"] = query_author.strip()

            resp = await client.get("https://openlibrary.org/search.json", params=params)
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("docs", [])
                if docs:
                    doc = docs[0]
                    title = doc.get("title", clean_title)
                    authors = doc.get("author_name", [])
                    subjects = doc.get("subject", [])[:6]
                    first_publish = doc.get("first_publish_year")
                    cover_i = doc.get("cover_i")
                    cover_url = f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg" if cover_i else None

                    # If OpenLibrary has a work key, try fetching description
                    description = ""
                    work_key = doc.get("key")
                    if work_key:
                        try:
                            w_resp = await client.get(f"https://openlibrary.org{work_key}.json", timeout=4.0)
                            if w_resp.status_code == 200:
                                w_data = w_resp.json()
                                desc_val = w_data.get("description")
                                if isinstance(desc_val, dict):
                                    description = desc_val.get("value", "")
                                elif isinstance(desc_val, str):
                                    description = desc_val
                        except Exception:
                            pass

                    if not description and doc.get("first_sentence"):
                        fs = doc.get("first_sentence")
                        description = fs[0] if isinstance(fs, list) else str(fs)

                    return {
                        "source": "Open Library",
                        "title": title,
                        "authors": authors,
                        "display_author": authors[0] if authors else "Unknown",
                        "description": description or f"Published in {first_publish}." if first_publish else "",
                        "subjects": subjects,
                        "cover_url": cover_url,
                        "publish_year": first_publish
                    }
    except Exception as ol_err:
        logger.debug(f"OpenLibrary query notice: {ol_err}")

    # 2. Secondary Fallback: Google Books Public API
    try:
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            q = f"intitle:{clean_title}"
            if query_author:
                q += f"+inauthor:{query_author}"

            resp = await client.get("https://www.googleapis.com/books/v1/volumes", params={"q": q, "maxResults": 1})
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                if items:
                    v_info = items[0].get("volumeInfo", {})
                    title = v_info.get("title", clean_title)
                    authors = v_info.get("authors", [])
                    desc = v_info.get("description", "")
                    categories = v_info.get("categories", [])
                    image_links = v_info.get("imageLinks", {})
                    cover_url = image_links.get("thumbnail") or image_links.get("smallThumbnail")
                    if cover_url and cover_url.startswith("http://"):
                        cover_url = cover_url.replace("http://", "https://")

                    return {
                        "source": "Google Books",
                        "title": title,
                        "authors": authors,
                        "display_author": authors[0] if authors else "Unknown",
                        "description": desc,
                        "subjects": categories,
                        "cover_url": cover_url,
                        "publish_year": (v_info.get("publishedDate") or "")[:4]
                    }
    except Exception as gb_err:
        logger.debug(f"Google Books query notice: {gb_err}")

    return None
