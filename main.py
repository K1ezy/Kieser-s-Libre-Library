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

# Enable NiceGUI orjson serializer to transparently handle BSON ObjectId as strings
try:
    import nicegui.json.orjson_wrapper as nicegui_json
    from bson import ObjectId
    _orig_orjson_converter = nicegui_json._orjson_converter

    def _safe_orjson_converter(obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return _orig_orjson_converter(obj)

    nicegui_json._orjson_converter = _safe_orjson_converter
except Exception:
    pass

# High-Performance HTTP Compression: Gzip compresses HTML, JSON, CSS, and JS over mobile network
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

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
import ui.pages.attendance as attendance
import ui.pages.requisitions as requisitions
import ui.pages.analytics as analytics

BASE_DIR = Path(__file__).resolve().parent

# --- STATIC FILES (30-day client browser caching for zero-latency asset loads) ---
ORGANIZED_BOOKS_DIR = BASE_DIR / 'data' / 'books'
if not ORGANIZED_BOOKS_DIR.exists():
    ORGANIZED_BOOKS_DIR.mkdir(parents=True, exist_ok=True)
app.add_static_files('/static_books', ORGANIZED_BOOKS_DIR, max_cache_age=2592000)

STATIC_DIR = BASE_DIR / 'static'
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.add_static_files('/static', STATIC_DIR, max_cache_age=2592000)

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

@ui.page('/attendance')
async def attendance_route():
    if not check_auth(): return
    app.storage.client['page_path'] = '/attendance'
    apply_theme()
    await attendance.attendance_page()
    FloatingChat()

@ui.page('/requisitions')
async def requisitions_route():
    if not check_auth(): return
    app.storage.client['page_path'] = '/requisitions'
    apply_theme()
    await requisitions.requisitions_page()
    FloatingChat()

@ui.page('/analytics')
async def analytics_route():
    if not check_auth(): return
    app.storage.client['page_path'] = '/analytics'
    apply_theme()
    await analytics.analytics_page()
    FloatingChat()

@ui.page('/admin')
async def admin_route():
    if not check_auth(): return
    user_role = app.storage.user.get('role', 'student').lower()
    if user_role not in ['admin', 'librarian']:
        ui.notify("Administrator or Librarian access required.", type='warning')
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

def _ensure_port_available(port: int = 8080):
    """Releases port if occupied by a stale process on Windows to prevent Errno 10048."""
    import socket, subprocess, os, time
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(('127.0.0.1', port)) != 0:
            return
    try:
        out = subprocess.check_output(f'netstat -ano -p tcp | findstr :{port}', shell=True, text=True)
        for line in out.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[3] == 'LISTENING':
                target_pid = int(parts[4])
                if target_pid != os.getpid() and target_pid != 0:
                    subprocess.run(f'taskkill /F /PID {target_pid}', shell=True, capture_output=True)
                    time.sleep(0.3)
    except Exception:
        pass

if __name__ in {"__main__", "__mp_main__"}:
    _ensure_port_available(8080)
    app.on_shutdown(shutdown_client) 
    ui.run(
        title="Libre Library",
        favicon="📚",
        host="0.0.0.0",
        port=8080,
        storage_secret=settings.SECRET_KEY,
        session_middleware_kwargs={"max_age": None},
        dark=False,
        reload=settings.RELOAD,
        uvicorn_reload_excludes=["data/*", "data/**", "chroma_db/*", "*.log"]
    )