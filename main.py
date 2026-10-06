from nicegui import ui, app
from ui.theme import apply_theme
from core.config import settings
from core.database.mongo_manager import mongo_db 
from core.external_api.dbooks_manager import shutdown_client
from core.auth.jwt_handler import is_user_authenticated
from components.chat_floating import FloatingChat 
from core.external_api.opds_router import opds_router
from core.ai_engine.llm_engine import tars_engine
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
import asyncio

# Secure CORS policy: Restrict to configured origins, localhost, LAN, and ngrok tunnels
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|.*\.ngrok-free\.app|.*\.ngrok\.io|.*\.ngrok\.app)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Register OPDS 1.2 Catalog Router for E-Readers (KOReader, Moon+ Reader, Apple Books)
app.include_router(opds_router)

# --- PAGE IMPORTS ---
import ui.pages.home as home
import ui.pages.auth as auth
import ui.pages.planner as planner
import ui.pages.admin as admin
import ui.pages.summarizer as summarizer 
import ui.pages.reader_interface as reader
import ui.pages.upload as upload
import ui.pages.chat as chat  
import ui.pages.book_details as book_details
import ui.pages.book_collection as books_collection
import ui.pages.profile as profile

BASE_DIR = Path(__file__).resolve().parent

# --- STATIC FILES ---
ORGANIZED_BOOKS_DIR = BASE_DIR / 'data' / 'books'
if not ORGANIZED_BOOKS_DIR.exists():
    ORGANIZED_BOOKS_DIR.mkdir(parents=True, exist_ok=True)
app.add_static_files('/static_books', ORGANIZED_BOOKS_DIR)

STATIC_DIR = BASE_DIR / 'static'
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.add_static_files('/static', STATIC_DIR)

# --- AUTH GUARD HELPER ---
def check_auth() -> bool:
    """Verifies that user has a valid, non-expired authentication token."""
    if not is_user_authenticated():
        ui.navigate.to('/login')
        return False
    return True

# --- ROUTES ---

@ui.page('/login')
async def login_route():
    apply_theme()
    await auth.login_page()

@ui.page('/signup')
async def signup_route():
    apply_theme()
    await auth.signup_page()

@ui.page('/')
async def index_page():
    if not check_auth(): return
    app.storage.client['page_path'] = '/' 
    apply_theme()
    await home.home_page() 
    FloatingChat()

@ui.page('/books')
async def books_route():
    if not check_auth(): return
    app.storage.client['page_path'] = '/books'
    apply_theme()
    await books_collection.books_page() 
    FloatingChat()

@ui.page('/read/{book_id}')
async def reader_route(book_id: str):
    if not check_auth(): return
    app.storage.client['page_path'] = '/read'
    apply_theme()
    await reader.reader_page(book_id)

@ui.page('/profile')
async def profile_route():
    if not check_auth(): return
    app.storage.client['page_path'] = '/profile'
    apply_theme()
    await profile.profile_page()
    FloatingChat()

@ui.page('/book/{book_id}')
async def book_detail_route(book_id: str):
    if not check_auth(): return
    app.storage.client['page_path'] = '/book' 
    apply_theme()
    await book_details.book_page(book_id)
    FloatingChat()

@ui.page('/planner')
async def planner_route():
    if not check_auth(): return
    app.storage.client['page_path'] = '/planner'
    apply_theme()
    await planner.planner_page()
    FloatingChat()

@ui.page('/upload')
async def upload_page():
    if not check_auth(): return
    app.storage.client['page_path'] = '/upload'
    apply_theme()
    await upload.upload_page() 
    FloatingChat()

@ui.page('/chat')
async def chat_route():
    if not check_auth(): return
    app.storage.client['page_path'] = '/chat'
    apply_theme()
    await chat.chat_page()

@ui.page('/summarizer')
async def summarizer_route():
    if not check_auth(): return
    app.storage.client['page_path'] = '/summarizer'
    apply_theme()
    await summarizer.summarizer_page()
    FloatingChat()

@ui.page('/admin')
async def admin_route():
    if not check_auth(): return
    if app.storage.user.get('role') != 'admin':
        ui.notify("Administrator access required.", type='warning')
        return ui.navigate.to('/')
    app.storage.client['page_path'] = '/admin'
    apply_theme()
    await admin.admin_dashboard()
    FloatingChat()

# --- STARTUP ---
@app.on_startup
async def startup():
    await mongo_db.initialize()
    await tars_engine.ensure_db_settings_loaded()

if __name__ in {"__main__", "__mp_main__"}:
    app.on_shutdown(shutdown_client) 
    ui.run(
        title="Libre Library",
        favicon="📚",
        host="0.0.0.0",
        port=8080,
        storage_secret=settings.SECRET_KEY,
        dark=False,
        reload=settings.RELOAD,
        uvicorn_reload_excludes=["data/*", "data/**", "chroma_db/*", "*.log"]
    )