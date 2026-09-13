import httpx
import asyncio
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path  # <-- FIX 1: Import Path type
import aiofiles          # <-- FIX 2: Import aiofiles library

# Setup Logger
logger = logging.getLogger("DBooks_API")

# --- BASE URLS ---
BASE_URL = "https://www.dbooks.org/api/"
RECENT_URL = BASE_URL + "recent"
SEARCH_URL = BASE_URL + "search/"  # Needs {query} appended
BOOK_DETAIL_URL = BASE_URL + "book/" # Needs {id} appended

# --- CLIENT ---
# Use httpx.AsyncClient for asynchronous requests
client = httpx.AsyncClient(timeout=10)


async def fetch_api(url: str) -> Optional[Dict[str, Any]]:
    """Generic async function to fetch JSON data from a given API URL."""
    try:
        response = await client.get(url)
        response.raise_for_status() # Raises an HTTPStatusError for bad responses (4xx or 5xx)
        return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP Error for {url}: {e.response.status_code}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request Error for {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return None


async def get_recent_books() -> List[Dict[str, Any]]:
    """Fetches the list of recently added books."""
    logger.info("Fetching recent books from dbooks.org...")
    data = await fetch_api(RECENT_URL)
    
    if data and data.get('status') == 'ok':
        return data.get('books', [])
    return []


async def search_books(query: str) -> List[Dict[str, Any]]:
    """Searches the dbooks.org catalog for a given query."""
    if not query:
        return []
    
    encoded_query = httpx.URL(query).path # Simple encoding for URL safety
    url = f"{SEARCH_URL}{encoded_query}"
    
    logger.info(f"Searching dbooks.org for: '{query}'")
    data = await fetch_api(url)
    
    if data and data.get('status') == 'ok':
        # API note: maximum search results = 100 books
        return data.get('books', [])
    return []


async def get_book_details(book_id: str) -> Optional[Dict[str, Any]]:
    """Fetches detailed information and the temporary download URL for a specific book ID."""
    if not book_id:
        return None
    
    url = f"{BOOK_DETAIL_URL}{book_id}"
    logger.info(f"Fetching details for book ID: {book_id}")
    data = await fetch_api(url)
    
    if data and data.get('status') == 'ok':
        # Critical note: book download URL expires in 2 hours
        return data
    return None


async def download_book_file(book_details: Dict[str, Any], save_path: Path) -> bool:
    """
    Downloads the actual book file using the temporary download URL and saves it locally.
    
    Args:
        book_details: The dictionary returned by get_book_details.
        save_path: The full Path object where the file should be saved (e.g., Path('/uploads/book.pdf')).
        
    Returns:
        True if the download was successful, False otherwise.
    """
    download_url = book_details.get('download')
    
    if not download_url:
        logger.error(f"Download URL missing for book ID: {book_details.get('id', 'N/A')}")
        return False
        
    logger.info(f"Starting download for {book_details.get('title')}")
    
    try:
        # Use streaming download for potentially large files
        async with client.stream("GET", download_url) as response:
            response.raise_for_status()
            
            # Use aiofiles to write asynchronously/io-bound
            async with aiofiles.open(save_path, 'wb') as f:
                async for chunk in response.aiter_bytes():
                    await f.write(chunk)
            
        logger.info(f"Successfully downloaded to: {save_path}")
        return True
        
    except httpx.HTTPStatusError as e:
        logger.error(f"Download failed (Status {e.response.status_code}): URL may have expired or is invalid.")
        return False
    except httpx.RequestError as e:
        logger.error(f"Download request error: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected download error occurred: {e}")
        return False

# Close the HTTPX client when the application shuts down
async def shutdown_client():
    await client.aclose()