from nicegui import ui, run, app
from core.database.mongo_manager import mongo_db
from core.ai_engine.llm_engine import tars_engine
from core.ai_engine.rag_pipeline import tars_archive
from core.services.ingestion_service import ingestion_service
from core.config import settings
from pathlib import Path
from datetime import datetime
import asyncio
import time
import uuid
import logging
import string

# Responsive Layout Components
from components.sidebar import sidebar
from components.header import header

# Setup Interface Logger
logger = logging.getLogger("TARS_UI")

# ==========================================
# 📑 SERVICE INTEGRATION & HELPERS
# ==========================================

from ui.pages.chat_service import (
    chat_service,
    STYLE_PROMPTS,
    STARTER_PROMPTS_BOOK,
    STARTER_PROMPTS_LIBRARY,
    group_sessions_chronologically,
)


def setup_message_actions(content: str, copy_btn, tts_btn):
    """Binds 1-click clipboard copy and text-to-speech audio playback."""
    if not content:
        return

    # Clipboard action
    copy_btn.on('click', lambda c=content: (
        ui.run_javascript(f"navigator.clipboard.writeText({repr(c)});"),
        ui.notify("Response copied to clipboard!", type='positive')
    ))

    # Text-to-speech action
    clean_text = content.replace("`", "").replace("*", "").replace("#", "")
    tts_btn.on('click', lambda c=clean_text: ui.run_javascript(f"""
        if (window.speechSynthesis.speaking) {{
            window.speechSynthesis.cancel();
        }} else {{
            const u = new SpeechSynthesisUtterance({repr(c[:1500])});
            u.rate = 1.0;
            window.speechSynthesis.speak(u);
        }}
    """))



# ==========================================
# 🤖 CHAT INTERFACE CONTROLLER
# ==========================================

class ChatInterface:
    """
    Clean, modular controller for TARS AI Librarian Chat:
    - Scoped Document RAG & Cross-Library Synthesis
    - Multi-provider Streaming Response Engine
    - Slide-over History Drawer & Conversation Management
    - Responsive Layout (Mobile-first to 4K displays)
    - Clean light mode with cohesive color theory matching
    """
    def __init__(self):
        # 1. Session Identification
        url_id = app.storage.user.get('url_chat_id')
        if url_id:
            self.session_id = url_id
            app.storage.user['session_id'] = url_id
            del app.storage.user['url_chat_id']
        elif 'session_id' not in app.storage.user:
            app.storage.user['session_id'] = str(uuid.uuid4())
            self.session_id = app.storage.user['session_id']
        else:
            self.session_id = app.storage.user['session_id']

        # 2. Scoped Book Focus State
        self.focus_book_id = app.storage.user.get('chat_focus_book_id')
        self.focus_book_title = app.storage.user.get('chat_focus_book_title')
        self.focus_badge_row = None
        self.default_badge_row = None
        self.focus_title_label = None
        self.teaching_btn = None
        self.style_select = None

        # 3. UI References
        self.log_container = None
        self.scroll_container = None
        self.scroll_anchor = None
        self.welcome_container = None
        self.text_input = None
        self.send_btn = None
        self.stop_btn = None
        self.continue_btn = None

        # Dialog References
        self.upload_dialog = None
        self.book_picker_dialog = None
        self.book_picker_list = None
        self.history_drawer = None
        self.history_list_container = None
        self.history_search_input = None
        self.history_top_badge = None
        self.history_drawer_badge = None

        # 4. State & Caches
        self.cached_sessions = []
        self.cached_books = []
        self.current_search_query = ""
        self.thinking = False
        self.abort_trigger = False
        self.teaching_mode = app.storage.user.get('teaching_mode', False)
        self.chat_style = app.storage.user.get('chat_style', 'Balanced')
        self.last_response_text = ""

    # ==========================================
    # 🎛️ UI STATE & VISIBILITY HELPERS
    # ==========================================

    def _set_generating_state(self, is_generating: bool):
        """Toggles interface state between generation and idle."""
        self.thinking = is_generating
        if self.send_btn:
            self.send_btn.set_visibility(not is_generating)
        if self.stop_btn:
            self.stop_btn.set_visibility(is_generating)
        if self.continue_btn and is_generating:
            self.continue_btn.disable()

    def scroll_to_bottom(self):
        """Smoothly scrolls the chat log container to the latest message."""
        if self.scroll_anchor:
            self.scroll_anchor.run_method('scrollIntoView', {'behavior': 'smooth', 'block': 'end'})

    def update_focus_badges(self):
        """Synchronizes top bar pills with active document focus."""
        has_focus = bool(self.focus_book_title)
        if self.focus_title_label and self.focus_book_title:
            self.focus_title_label.text = f"Focus: {self.focus_book_title}"
        if self.focus_badge_row:
            self.focus_badge_row.set_visibility(has_focus)
        if self.default_badge_row:
            self.default_badge_row.set_visibility(not has_focus)

    def clear_book_focus(self):
        """Resets scoped retrieval back to the entire digital library."""
        self.focus_book_id = None
        self.focus_book_title = None
        app.storage.user.pop('chat_focus_book_id', None)
        app.storage.user.pop('chat_focus_book_title', None)
        self.update_focus_badges()
        ui.notify("Chat focus reset to entire library.", type='info')
        if hasattr(self, 'welcome_container') and self.welcome_container:
            self.render_welcome_state()

    def set_book_focus(self, book: dict):
        """Scopes chat queries exclusively to the selected book."""
        self.focus_book_id = book.get('id')
        self.focus_book_title = book.get('title', 'Selected Document')
        app.storage.user['chat_focus_book_id'] = self.focus_book_id
        app.storage.user['chat_focus_book_title'] = self.focus_book_title
        self.update_focus_badges()
        if self.book_picker_dialog:
            self.book_picker_dialog.close()
        ui.notify(f"Chat focused on: '{self.focus_book_title}'", type='positive')
        if hasattr(self, 'welcome_container') and self.welcome_container:
            self.render_welcome_state()

    # ==========================================
    # 📚 BOOK SCOPE PICKER
    # ==========================================

    async def open_book_picker(self):
        """Opens modal dialog for choosing or changing the scoped book."""
        if not self.book_picker_dialog:
            return
        self.book_picker_dialog.open()
        await self.populate_book_picker("")

    async def populate_book_picker(self, query: str = ""):
        """Filters and renders available library books in the picker modal."""
        if not self.book_picker_list:
            return
        self.book_picker_list.clear()

        try:
            if not self.cached_books:
                self.cached_books = await mongo_db.get_recent_books(limit=100)

            books = self.cached_books
            if query:
                q = query.lower().strip()
                books = [
                    b for b in books
                    if q in b.get('title', '').lower()
                    or q in str(b.get('display_author', '')).lower()
                    or q in str(b.get('authors', '')).lower()
                ]

            with self.book_picker_list:
                if not books:
                    with ui.column().classes('w-full items-center py-8 text-center text-slate-400'):
                        ui.icon('search_off', size='2.5em').classes('mb-1')
                        ui.label("No documents matching filter.").classes('text-xs font-semibold')
                    return

                for b in books:
                    self._render_book_picker_item(b)

        except Exception as e:
            logger.error(f"Book Picker Load Error: {e}")

    def _render_book_picker_item(self, book: dict):
        """Renders an individual book row in the book scope picker."""
        title = book.get('title', 'Untitled')
        author = book.get('display_author') or book.get('authors') or 'Unknown'
        if isinstance(author, list) and author:
            author = str(author[0])
        ftype = book.get('file_type', 'PDF').upper()
        is_active = (book.get('id') == self.focus_book_id)

        card_border = (
            'border-indigo-400 bg-indigo-50/50'
            if is_active else
            'border-slate-200 bg-white'
        )

        with ui.card().classes(f'w-full p-2.5 sm:p-3 rounded-2xl border {card_border} transition-all hover:border-indigo-400 cursor-pointer shadow-none'):
            with ui.row().classes('w-full items-center justify-between no-wrap gap-2'):
                with ui.row().classes('items-center gap-2.5 flex-grow min-w-0'):
                    with ui.element('div').classes('p-2 rounded-xl bg-indigo-50 text-indigo-600 shrink-0 border border-indigo-100'):
                        ui.icon('menu_book', size='18px')
                    with ui.column().classes('gap-0 flex-grow min-w-0'):
                        ui.label(title).classes('text-xs font-bold text-slate-900 truncate w-full')
                        ui.label(f"{author} • {ftype}").classes('text-[10px] text-slate-400 truncate')

                if is_active:
                    ui.label('Current Focus').classes('text-[10px] font-bold text-indigo-700 bg-indigo-100 px-2.5 py-1 rounded-full shrink-0')
                else:
                    ui.button('Focus', on_click=lambda b=book: self.set_book_focus(b)) \
                        .props('unelevated rounded-xl dense size=xs color=indigo').classes('font-bold shrink-0')

    # ==========================================
    # 🕒 CHAT HISTORY & SESSION MANAGEMENT
    # ==========================================

    def toggle_history(self):
        """Opens or closes the universal Chat History slide-over panel."""
        if self.history_drawer:
            self.history_drawer.toggle()

    async def load_and_refresh_history(self):
        """Fetches all sessions from MongoDB, caches them, and refreshes UI badges and list."""
        try:
            uid = app.storage.user.get('user_id')
            sessions = await mongo_db.get_chat_sessions(limit=60, user_id=uid)
            self.cached_sessions = sessions or []
            count_str = str(len(self.cached_sessions))
            if self.history_top_badge:
                self.history_top_badge.text = count_str
            if self.history_drawer_badge:
                self.history_drawer_badge.text = count_str
            self.render_history_list(self.current_search_query)
        except Exception as e:
            logger.error(f"History refresh error: {e}")

    def render_history_list(self, filter_query: str = ""):
        """Renders cached sessions into the history drawer container."""
        if not self.history_list_container:
            return
        self.current_search_query = filter_query.strip().lower()
        sessions = self.cached_sessions

        if self.current_search_query:
            sessions = [
                s for s in sessions
                if self.current_search_query in s.get('title', '').lower()
                or self.current_search_query in str(s.get('book_title', '')).lower()
            ]

        self.history_list_container.clear()
        grouped = group_sessions_chronologically(sessions)

        with self.history_list_container:
            if not sessions:
                self._render_empty_history()
                return

            for group_name, group_items in grouped.items():
                self._render_history_group_header(group_name, len(group_items))
                for s in group_items:
                    self._render_history_item(s)

    def _render_empty_history(self):
        """Renders placeholder when no conversations exist or match filter."""
        with ui.column().classes('w-full items-center justify-center py-12 text-center px-4'):
            ui.icon('chat_bubble_outline', size='3em').classes('text-slate-300 mb-2')
            ui.label("No conversations found").classes('text-xs font-bold text-slate-600')
            ui.label("Conversations you create will appear here.").classes('text-[11px] text-slate-400 max-w-[200px]')

    def _render_history_group_header(self, group_name: str, count: int):
        """Renders clean section header in history drawer."""
        with ui.row().classes('w-full items-center justify-between px-2 pt-3 pb-1'):
            ui.label(group_name).classes('text-[10px] font-black text-slate-400 uppercase tracking-widest')
            ui.label(f"{count}").classes('text-[9px] font-bold text-slate-500 bg-slate-100 px-1.5 py-0.2 rounded-full')

    def _render_history_item(self, session_data: dict):
        """Renders an individual conversation item card in the history drawer."""
        sid = session_data.get('id')
        title = session_data.get('title', 'Conversation')
        ts = session_data.get('timestamp')
        book_t = session_data.get('book_title')
        msg_cnt = session_data.get('message_count')
        is_active = (sid == self.session_id)

        time_str = ""
        if ts:
            try:
                time_str = datetime.fromtimestamp(ts).strftime("%b %d, %H:%M")
            except Exception:
                time_str = ""

        if is_active:
            card_classes = (
                'w-full p-3 rounded-2xl border-l-4 border-indigo-600 '
                'bg-indigo-50/80 border-y border-r border-indigo-200 '
                'shadow-sm group transition-all'
            )
            title_classes = 'text-xs font-bold text-indigo-950 truncate w-full'
            icon_classes = 'text-indigo-600'
        else:
            card_classes = (
                'w-full p-3 rounded-2xl border border-slate-200/80 '
                'bg-white hover:bg-slate-50 '
                'hover:border-indigo-300 cursor-pointer group transition-all shadow-sm'
            )
            title_classes = 'text-xs font-semibold text-slate-700 group-hover:text-indigo-600 truncate w-full'
            icon_classes = 'text-slate-400 group-hover:text-indigo-500'

        with ui.card().classes(card_classes):
            with ui.row().classes('w-full items-center justify-between no-wrap gap-2'):
                # Clickable Session Row
                with ui.row().classes('items-center gap-2.5 flex-grow min-w-0 cursor-pointer').on('click', lambda s=sid: self.switch_session(s)):
                    ui.icon('chat_bubble', size='16px').classes(f'{icon_classes} shrink-0')
                    with ui.column().classes('gap-0.5 flex-grow min-w-0'):
                        ui.label(title).classes(title_classes)
                        with ui.row().classes('items-center gap-1.5 flex-wrap'):
                            if time_str:
                                ui.label(time_str).classes('text-[10px] text-slate-400 font-medium')
                            if msg_cnt:
                                ui.label(f"• {msg_cnt} msgs").classes('text-[10px] text-slate-400 font-semibold')
                            if book_t:
                                with ui.row().classes('items-center gap-0.5 bg-indigo-100 text-indigo-700 px-1.5 py-0.2 rounded text-[9px] font-bold max-w-[120px] truncate'):
                                    ui.icon('book', size='10px')
                                    ui.label(book_t).classes('truncate')

                # Delete Button
                with ui.row().classes('items-center gap-0.5 shrink-0 opacity-80 group-hover:opacity-100 transition-opacity'):
                    with ui.button(icon='delete_outline', on_click=lambda s=sid: self.delete_session_ui(s)) \
                            .props('flat round dense size=xs color=grey-7').classes('hover:text-rose-600'):
                        ui.tooltip('Delete conversation')

    async def switch_session(self, session_id: str):
        """Switches active conversation session and loads all its messages."""
        if self.session_id == session_id and self.log_container and len(self.log_container.default_slot.children) > 0:
            if self.history_drawer:
                self.history_drawer.hide()
            return

        self.session_id = session_id
        app.storage.user['session_id'] = session_id
        if self.history_drawer:
            self.history_drawer.hide()

        sess_data = next((s for s in self.cached_sessions if s.get('id') == session_id), None)
        if sess_data and sess_data.get('book_id'):
            self.focus_book_id = sess_data.get('book_id')
            self.focus_book_title = sess_data.get('book_title')
            app.storage.user['chat_focus_book_id'] = self.focus_book_id
            app.storage.user['chat_focus_book_title'] = self.focus_book_title
        elif sess_data and not sess_data.get('book_id'):
            self.focus_book_id = None
            self.focus_book_title = None
            app.storage.user.pop('chat_focus_book_id', None)
            app.storage.user.pop('chat_focus_book_title', None)

        self.update_focus_badges()
        await self.initialize()
        self.render_history_list(self.current_search_query)
        ui.notify("Loaded conversation history.", type='info')

    async def delete_session_ui(self, sid: str):
        """Deletes a conversation from MongoDB and UI without lingering ghosts."""
        await mongo_db.delete_chat_session(sid)
        ui.notify("Chat session deleted.", type='info')
        if sid == self.session_id:
            await self.start_new_chat()
        else:
            await self.load_and_refresh_history()

    async def start_new_chat(self):
        """Starts a clean, empty chat session without stacking or duplicating."""
        new_id = str(uuid.uuid4())
        app.storage.user['session_id'] = new_id
        self.session_id = new_id
        self.last_response_text = ""

        if self.log_container:
            self.log_container.clear()

        self.render_welcome_state()
        self.render_history_list(self.current_search_query)
        if self.history_drawer:
            self.history_drawer.hide()
        ui.notify("New chat started.", type='positive')

    async def export_chat(self):
        """Exports the active conversation as a clean Markdown document and downloads it."""
        try:
            messages = await mongo_db.get_full_session_messages(self.session_id)
            if not messages:
                ui.notify("No conversation to export.", type='warning')
                return

            md_content = chat_service.export_chat_markdown(messages, self.focus_book_title, self.session_id)
            ui.download(md_content.encode('utf-8'), f"tars_chat_{self.session_id[:8]}.md")
            ui.run_javascript(f"navigator.clipboard.writeText({repr(md_content)});")
            ui.notify("Chat exported to Markdown & copied to clipboard!", type='positive')
        except Exception as e:
            ui.notify(f"Export failed: {e}", type='negative')

    async def clear_current_chat(self):
        """Clears messages in this session and resets to welcome hero."""
        try:
            await mongo_db.delete_chat_session(self.session_id)
            if self.log_container:
                self.log_container.clear()
            self.render_welcome_state()
            await self.load_and_refresh_history()
            ui.notify("Conversation cleared.", type='info')
        except Exception as e:
            ui.notify(f"Clear failed: {e}", type='negative')

    def open_upload_dialog(self):
        """Opens document upload modal."""
        if self.upload_dialog:
            self.upload_dialog.open()
        else:
            ui.notify("Upload system not initialized.", type='negative')

    def on_style_change(self, e):
        """Updates AI persona style."""
        self.chat_style = e.value
        app.storage.user['chat_style'] = self.chat_style
        ui.notify(f"Response style set to: {self.chat_style}", type='info')

    def toggle_teaching_mode(self, e=None):
        """Toggles Socratic tutoring persona."""
        val = e.value if (e is not None and hasattr(e, 'value')) else not self.teaching_mode
        self.teaching_mode = val
        app.storage.user['teaching_mode'] = self.teaching_mode
        if hasattr(self, 'teaching_btn') and self.teaching_btn:
            self.teaching_btn.text = f"🎓 Teaching: {'ON' if self.teaching_mode else 'OFF'}"
            self.teaching_btn.props(f'color={"indigo" if self.teaching_mode else "grey-7"}')
        status = "ENABLED (Socratic Tutoring)" if self.teaching_mode else "DISABLED"
        color = "positive" if self.teaching_mode else "info"
        ui.notify(f"Teaching Mode {status}.", type=color)

    def show_engine_info(self):
        """Displays dialog explaining local AI architecture."""
        with ui.dialog() as d, ui.card().classes('max-w-md p-6 rounded-3xl bg-white border border-slate-200 shadow-2xl'):
            with ui.row().classes('items-center gap-2 mb-2'):
                ui.icon('memory', size='24px').classes('text-indigo-600')
                ui.label("TARS AI Architecture").classes('text-base font-bold text-slate-900')
            ui.label("• Engine: Multi-provider Local GGUF, Ollama, & OpenAI endpoints").classes('text-xs text-slate-600')
            ui.label("• Vector DB: ChromaDB with all-MiniLM-L6-v2 embeddings").classes('text-xs text-slate-600')
            ui.label("• Scoped RAG: Document-level & Library-wide semantic retrieval").classes('text-xs text-slate-600')
            ui.label("• Citations: Clickable document page references").classes('text-xs text-slate-600')
            ui.button("Close", on_click=d.close).props('unelevated rounded-xl color=indigo size=sm font-bold').classes('mt-4 w-full shadow-md')
        d.open()

    async def handle_upload(self, e):
        """Integrates file uploads directly into the unified ingestion pipeline."""
        try:
            from ui.pages.upload import SmartFileAdapter
            adapter = SmartFileAdapter(e)
            fname = adapter.name

            ui.notify(f"Ingesting '{fname}'...", type='info')
            result = await ingestion_service.process_upload(adapter, fname)

            if result.get('success'):
                ui.notify(result.get('message', 'File ingested successfully.'), type='positive')
                self.upload_dialog.close()
                self.cached_books = []
            else:
                ui.notify(f"Ingestion failed: {result.get('error')}", type='negative')
        except Exception as err:
            logger.error(f"Upload Error: {err}")
            ui.notify(f"Upload Error: {err}", type='negative')

    # ==========================================
    # 💬 CHAT RENDERING & MESSAGE LOGIC
    # ==========================================

    def render_welcome_state(self):
        """Displays a SINGLE rich greeting hero and starter prompt cards strictly inside log_container."""
        if not self.log_container:
            return

        self.log_container.clear()
        self.welcome_container = None

        with self.log_container:
            self.welcome_container = ui.column().classes('w-full items-center justify-center py-8 sm:py-12 text-center')
            with self.welcome_container:
                # Glowing TARS Icon
                with ui.element('div').classes(
                    'p-4 sm:p-5 rounded-3xl bg-indigo-50 text-indigo-600 '
                    'border border-indigo-200 shadow-md mb-3 animate-pulse'
                ):
                    ui.icon('smart_toy', size='3em')

                if self.focus_book_title:
                    ui.label(f"Chatting with '{self.focus_book_title}'").classes('text-xl sm:text-2xl font-black text-slate-900 tracking-tight mb-1')
                    ui.label("Ask questions, explore core themes, or test your comprehension of this document.").classes('text-xs sm:text-sm text-slate-500 max-w-lg mb-6')
                    prompts = STARTER_PROMPTS_BOOK
                else:
                    ui.label("TARS AI Digital Librarian").classes('text-xl sm:text-2xl font-black text-slate-900 tracking-tight mb-1')
                    ui.label("Your intelligent companion for research, synthesis, and deep learning across your library.").classes('text-xs sm:text-sm text-slate-500 max-w-lg mb-6')
                    prompts = STARTER_PROMPTS_LIBRARY

                with ui.grid().classes('w-full max-w-2xl grid-cols-1 sm:grid-cols-2 gap-2.5 sm:gap-3 text-left'):
                    for label, prompt_text in prompts:
                        self._render_starter_card(label, prompt_text)

    def _render_starter_card(self, label: str, prompt_text: str):
        """Renders an individual interactive starter prompt card."""
        with ui.card().classes(
            'p-3.5 sm:p-4 rounded-2xl bg-white border border-slate-200 '
            'shadow-sm hover:shadow-md hover:border-indigo-400 '
            'hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group'
        ).on('click', lambda p=prompt_text: self.submit_preset_prompt(p)):
            with ui.row().classes('items-center justify-between w-full mb-1'):
                ui.label(label).classes('text-xs font-bold text-indigo-600')
                ui.icon('arrow_forward', size='14px').classes('text-slate-300 group-hover:text-indigo-500 group-hover:translate-x-1 transition-all')
            ui.label(prompt_text).classes('text-[11px] sm:text-xs text-slate-500 font-medium line-clamp-2 leading-snug')

    async def submit_preset_prompt(self, prompt_text: str):
        """Immediately executes a clicked starter prompt chip."""
        if self.thinking:
            return
        if self.text_input:
            self.text_input.value = prompt_text
        await self.send_message()

    def render_user_message(self, text: str):
        """Renders user message bubble with modern indigo gradient and rounded styling."""
        with self.log_container:
            with ui.row().classes('w-full justify-end mb-4'):
                with ui.row().classes('items-start gap-2 max-w-[88%] sm:max-w-[78%] justify-end'):
                    with ui.column().classes('p-3.5 sm:p-4 bg-gradient-to-r from-indigo-600 to-indigo-700 text-white rounded-2xl rounded-tr-sm shadow-md'):
                        ui.label(text).classes('text-sm text-white break-words')

    def render_assistant_message(self, content: str = "", citations: list = None, in_progress: bool = False):
        """Renders assistant message card with avatar, model badge, 1-click copy, TTS, and citations."""
        with self.log_container:
            with ui.row().classes('w-full justify-start mb-4'):
                with ui.column().classes(
                    'p-4 sm:p-5 bg-white border border-slate-200 '
                    'rounded-2xl rounded-tl-sm shadow-sm max-w-[95%] sm:max-w-[85%] break-words w-full'
                ) as card:
                    # Assistant Header
                    with ui.row().classes('w-full justify-between items-center mb-2.5 pb-2 border-b border-slate-100'):
                        with ui.row().classes('items-center gap-2'):
                            with ui.element('div').classes('p-1 sm:p-1.5 rounded-lg bg-indigo-50 text-indigo-600 border border-indigo-100'):
                                ui.icon('smart_toy', size='18px')
                            ui.label('TARS AI').classes('text-xs font-bold text-slate-900')
                            ui.label('Librarian').classes('text-[10px] font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-100')
                            if self.teaching_mode:
                                ui.label('Socratic Tutor').classes('text-[10px] font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200')

                        with ui.row().classes('items-center gap-1'):
                            tts_btn = ui.button(icon='volume_up').props('flat round dense size=xs color=grey-7').tooltip('Read Aloud (TTS)')
                            copy_btn = ui.button(icon='content_copy').props('flat round dense size=xs color=grey-7').tooltip('Copy Response')

                    status_label = None
                    if in_progress:
                        status_label = ui.label("Consulting archives...").classes('text-xs text-indigo-600 animate-pulse font-medium mb-1')

                    message_md = ui.markdown(content).classes('text-sm text-slate-800 prose max-w-none break-words overflow-x-auto')

                    if not in_progress and content:
                        setup_message_actions(content, copy_btn, tts_btn)

                    citations_container = ui.row().classes('gap-1.5 mt-3 pt-2.5 border-t border-slate-100 flex-wrap items-center')
                    if citations:
                        self._render_citation_chips(citations, citations_container)
                    else:
                        citations_container.set_visibility(False)

                    return card, status_label, message_md, copy_btn, tts_btn, citations_container

    def _render_citation_chips(self, citations: list, container):
        """Renders interactive citation chips linking to document reader."""
        container.set_visibility(True)
        with container:
            ui.label("Sources & Citations:").classes('text-[10px] font-bold uppercase tracking-wider text-slate-400')
            for cit in citations:
                label_txt = cit.get('title') or cit.get('source', 'Document')
                if len(label_txt) > 28:
                    label_txt = label_txt[:28] + '...'
                if cit.get('page'):
                    label_txt += f" (p.{cit['page']})"

                b_id = cit.get('book_id')
                badge_row = ui.row().classes(
                    'items-center gap-1 px-2.5 py-0.5 rounded-full bg-indigo-50 '
                    'border border-indigo-200 text-[11px] text-indigo-700 '
                    'font-semibold shadow-sm transition-all hover:scale-105'
                )
                if b_id:
                    badge_row.classes('cursor-pointer hover:bg-indigo-100')
                    badge_row.on('click', lambda b=b_id: ui.navigate.to(f'/read/{b}'))
                    badge_row.tooltip("Click to open document in Reader")

                with badge_row:
                    ui.icon('menu_book' if b_id else 'description', size='12px').classes('text-indigo-500')
                    ui.label(label_txt)

    async def initialize(self):
        """Loads and displays the full message history for the active session."""
        if not self.log_container:
            return
        self.log_container.clear()
        self.welcome_container = None

        try:
            history = await mongo_db.get_full_session_messages(self.session_id)
            if not history:
                self.render_welcome_state()
            else:
                for msg in history:
                    if msg.get('role') == 'user':
                        self.render_user_message(msg.get('content', ''))
                    else:
                        self.render_assistant_message(msg.get('content', ''))
            self.scroll_to_bottom()
        except Exception as e:
            ui.notify(f"History Load Error: {e}", type='warning')

        if self.continue_btn:
            self.continue_btn.disable()
        await self.load_and_refresh_history()

    def stop_generation(self):
        """Cancels active LLM generation stream."""
        if self.thinking:
            self.abort_trigger = True
            ui.notify("Stopping...", type='warning')

    # ==========================================
    # 🧠 RAG & PROMPT ORCHESTRATION
    # ==========================================

    def _should_skip_rag(self, text: str) -> bool:
        """Determines if query is a simple greeting or identity question where RAG should be skipped."""
        return chat_service.should_skip_rag(text)

    async def _perform_rag_search(self, text: str, status_label) -> tuple[str, list]:
        """Executes vector retrieval and formats context snippets and citations via ChatService."""
        focus_desc = f"'{self.focus_book_title}'" if self.focus_book_title else "knowledge base"
        if status_label:
            status_label.text = f"Searching {focus_desc}..."
        return await chat_service.perform_rag_search(text, self.focus_book_id, self.focus_book_title)

    def _build_system_persona(self, inventory: str, rag_text: str, is_review_mode: bool = False) -> str:
        """Constructs system prompt combining library inventory, retrieved RAG context, and persona instructions via ChatService."""
        return chat_service.build_system_persona(
            chat_style=self.chat_style,
            focus_book_title=self.focus_book_title,
            teaching_mode=self.teaching_mode,
            is_review_mode=is_review_mode,
            inventory=inventory,
            rag_text=rag_text
        )

    # ==========================================
    # ⚡ CORE GENERATION & STREAMING
    # ==========================================

    async def continue_generation(self):
        """Continue generating where TARS left off."""
        if not self.last_response_text or self.thinking:
            return

        self._set_generating_state(True)
        self.abort_trigger = False

        card, status_label, message_content, copy_btn, tts_btn, _ = self.render_assistant_message(in_progress=True)
        if status_label:
            status_label.text = "Continuing response..."

        history_context = await mongo_db.get_recent_history(self.session_id, limit=6)
        persona_text = (
            "You are TARS, the Digital Librarian. CONTINUE your last response exactly where it left off. "
            "Maintain tone and formatting. Do not repeat the beginning."
        )

        messages_payload = chat_service.build_messages_payload(persona_text, history_context)

        await asyncio.sleep(0.1)
        response_buffer = ""
        try:
            first_token = True
            async for token in tars_engine.stream_response(messages_payload):
                if self.abort_trigger:
                    response_buffer += " ... [STOPPED]"
                    message_content.content = response_buffer
                    break
                if first_token:
                    if status_label:
                        status_label.delete()
                    first_token = False
                response_buffer += token
                message_content.content = response_buffer

            self.last_response_text = response_buffer
            await mongo_db.add_message_to_session(self.session_id, "assistant", response_buffer)
            self.scroll_to_bottom()
            setup_message_actions(response_buffer, copy_btn, tts_btn)

            if self.continue_btn:
                has_ended = response_buffer.strip().endswith(('.', '!', '?', ':', ';', '```'))
                if not has_ended:
                    self.continue_btn.enable()
                else:
                    self.continue_btn.disable()

        except Exception as e:
            if status_label:
                try: status_label.delete()
                except Exception: pass
            with self.log_container:
                ui.label(f"SYSTEM FAILURE: {str(e)}").classes('text-rose-500 font-bold')

        self._set_generating_state(False)

    async def send_message(self):
        """Processes user input, streams LLM output with RAG, and saves to history."""
        if not self.text_input or not self.text_input.value:
            return
        text = self.text_input.value.strip()
        if not text or self.thinking:
            return

        is_review_mode = False
        if text == "/clear":
            await self.start_new_chat()
            return
        elif text.startswith("/review"):
            is_review_mode = True
            text = text.replace("/review", "").strip()
            if not text:
                ui.notify("Paste code after /review", type='warning')
                return

        # Dismiss welcome container on first message
        if hasattr(self, 'welcome_container') and self.welcome_container:
            try: self.welcome_container.delete()
            except Exception: pass
            self.welcome_container = None

        self.text_input.value = ''
        self._set_generating_state(True)
        self.abort_trigger = False

        # 1. Render and record User Message
        self.render_user_message(text)
        await mongo_db.add_message_to_session(self.session_id, "user", text)
        self.scroll_to_bottom()

        # 2. Render Assistant Placeholder Card
        card, status, message_content, copy_btn, tts_btn, citations_container = self.render_assistant_message(in_progress=True)

        # 3. Intent Detection & RAG Retrieval
        skip_rag = self._should_skip_rag(text)
        if not skip_rag:
            rag_text, citations = await self._perform_rag_search(text, status)
        else:
            rag_text, citations = "", []
            if status:
                status.text = "Responding..."
            await asyncio.sleep(0.1)

        # 4. Compose Persona & History Context
        history = await mongo_db.get_recent_history(self.session_id, limit=6)
        inventory = await mongo_db.get_library_inventory_summary(limit=10)
        persona = self._build_system_persona(inventory, rag_text, is_review_mode)

        messages = chat_service.build_messages_payload(persona, history)

        # 5. Stream LLM Generation
        if status:
            status.text = "Writing response..."
        response_buffer = ""
        try:
            first = True
            async for token in tars_engine.stream_response(messages):
                if self.abort_trigger:
                    break
                if first:
                    if status: status.delete()
                    first = False
                response_buffer += token
                message_content.content = response_buffer

            # Setup Copy & TTS actions
            setup_message_actions(response_buffer, copy_btn, tts_btn)

            # Render citation chips
            if citations:
                self._render_citation_chips(citations, citations_container)

            self.last_response_text = response_buffer
            await mongo_db.add_message_to_session(self.session_id, "assistant", response_buffer)
            self.scroll_to_bottom()

            # Update conversation title metadata
            title = text[:35] + ("..." if len(text) > 35 else "")
            uid = app.storage.user.get('user_id')
            await mongo_db.save_chat_metadata(
                self.session_id,
                title,
                book_id=self.focus_book_id,
                book_title=self.focus_book_title,
                user_id=uid
            )
            await self.load_and_refresh_history()

            if self.continue_btn:
                has_ended = response_buffer.strip().endswith(('.', '!', '?', ':', ';', '```'))
                if not has_ended:
                    self.continue_btn.enable()
                else:
                    self.continue_btn.disable()

        except Exception as e:
            if status:
                try: status.delete()
                except Exception: pass
            logger.error(f"LLM Generation failure: {e}", exc_info=True)
            with self.log_container:
                ui.label("Generation encountered an issue. Check system logs.").classes('text-rose-500 font-bold')

        self._set_generating_state(False)

    # ==========================================
    # 🏗️ MODULAR UI BUILDERS
    # ==========================================

    def _build_upload_dialog(self):
        """Constructs modal for file uploads and knowledge base ingestion."""
        with ui.dialog() as self.upload_dialog, ui.card().classes('w-[calc(100vw-2rem)] max-w-md p-5 sm:p-6 rounded-3xl bg-white border border-slate-200 shadow-2xl'):
            ui.label("Ingest Document to TARS").classes('text-lg font-black text-slate-900')
            ui.label("Upload PDF, EPUB, DOCX, PPTX, or TXT into your library & knowledge base.").classes('text-xs text-slate-500 mb-4')
            ui.upload(on_upload=self.handle_upload, auto_upload=True).props('accept=".pdf,.epub,.docx,.pptx,.txt" color=indigo flat bordered').classes('w-full border-2 border-dashed border-indigo-200 rounded-2xl')
            ui.button('Close', on_click=self.upload_dialog.close).props('flat rounded-xl color=grey size=md font-bold').classes('w-full mt-3')

    def _build_book_picker_dialog(self):
        """Constructs modal for selecting a scoped book filter."""
        with ui.dialog() as self.book_picker_dialog, ui.card().classes('w-[calc(100vw-2rem)] max-w-xl p-5 sm:p-6 rounded-3xl bg-white border border-slate-200 shadow-2xl'):
            with ui.row().classes('w-full justify-between items-center mb-1'):
                with ui.row().classes('items-center gap-2'):
                    with ui.element('div').classes('p-2 rounded-xl bg-indigo-50 text-indigo-600 border border-indigo-100'):
                        ui.icon('menu_book', size='20px')
                    ui.label("Focus on a Library Document").classes('text-base sm:text-lg font-black text-slate-900')
                ui.button(icon='close', on_click=self.book_picker_dialog.close).props('flat round dense size=sm color=grey')

            ui.label("Constrain TARS AI answers and RAG retrieval exclusively to a single book or paper.").classes('text-xs text-slate-500 mb-3')

            with ui.row().classes('w-full gap-2 items-center mb-3'):
                search_inp = ui.input(placeholder='Search by book title or author...').props('outlined rounded-xl dense clearable').classes('flex-grow text-xs')
                search_inp.on('update:model-value', lambda e: self.populate_book_picker(e.args if hasattr(e, 'args') and e.args else search_inp.value or ""))
                ui.button('Entire Library', icon='public', on_click=lambda: (self.clear_book_focus(), self.book_picker_dialog.close())) \
                    .props('flat dense rounded-xl size=sm color=indigo font-bold').tooltip('Remove focus constraint and search all books')

            with ui.column().classes('w-full max-h-80 overflow-y-auto gap-2 pr-1 no-scrollbar') as self.book_picker_list:
                pass

    def _build_history_drawer(self):
        """Constructs the slide-over conversation history drawer."""
        with ui.right_drawer(value=False).props('bordered width=340').classes('bg-white flex flex-col p-0 z-50 shadow-2xl w-full max-w-[88vw] sm:max-w-[360px]') as self.history_drawer:
            # Header
            with ui.row().classes('w-full h-16 items-center justify-between px-4 border-b border-slate-200 flex-none bg-slate-50'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('history', size='22px').classes('text-indigo-600')
                    ui.label("Conversation History").classes('text-sm font-black text-slate-900 tracking-tight')
                    self.history_drawer_badge = ui.label("0").classes('text-[10px] font-bold text-indigo-700 bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded-full')
                ui.button(icon='close', on_click=self.history_drawer.hide).props('flat round dense size=sm color=grey')

            # "+ New Chat" Action
            with ui.row().classes('p-3 pb-2 flex-none w-full border-b border-slate-100'):
                ui.button('+ New Chat', on_click=self.start_new_chat) \
                    .props('unelevated rounded-xl size=sm color=indigo').classes('w-full font-bold shadow-sm hover:shadow')

            # Search History Filter Box
            with ui.row().classes('px-3 py-2 flex-none w-full border-b border-slate-100'):
                self.history_search_input = ui.input(placeholder='Search by topic, title, or book...').props('outlined rounded-xl dense clearable') \
                    .classes('w-full text-xs bg-slate-50')
                self.history_search_input.on('update:model-value', lambda e: self.render_history_list(e.args if hasattr(e, 'args') and e.args else self.history_search_input.value or ""))

            # Scrollable History List Container
            with ui.column().classes('w-full flex-grow overflow-y-auto px-2.5 pb-6 gap-1 no-scrollbar') as self.history_list_container:
                pass

    def _build_top_control_bar(self, drawer):
        """Constructs unified top header for Chat with hamburger, history badge, focus pill, and options."""
        with ui.header().classes(
            'bg-white/95 backdrop-blur-md border-b border-slate-200 '
            'items-center px-2 sm:px-4 md:px-6 h-14 sm:h-16 pt-[env(safe-area-inset-top,0px)] '
            'fixed top-0 w-full z-40 select-none shadow-sm'
        ).props('elevated=False'):
            with ui.row().classes('w-full max-w-5xl mx-auto items-center justify-between gap-1.5 sm:gap-2 flex-nowrap'):
                # Left: Sidebar toggle, History toggle & Document Scope Badges
                with ui.row().classes('items-center gap-1 sm:gap-2 min-w-0 flex-1'):
                    if drawer:
                        ui.button(icon='menu', on_click=drawer.toggle) \
                            .props('flat round dense color=grey-8 size=md') \
                            .tooltip('Toggle Sidebar').classes('shrink-0')

                    with ui.button(icon='history', on_click=self.toggle_history) \
                            .props('unelevated rounded-xl size=sm color=indigo') \
                            .classes('font-bold text-xs shadow-sm shrink-0 px-2 sm:px-3'):
                        ui.label('History').classes('hidden sm:inline ml-1')
                        self.history_top_badge = ui.badge('0', color='indigo-9').props('floating')

                    # Focused Book Badge
                    self.focus_badge_row = ui.row().classes('items-center gap-1 px-2.5 sm:px-3 py-1 rounded-full bg-indigo-50 border border-indigo-200 shadow-sm cursor-pointer min-w-0').on('click', self.open_book_picker)
                    with self.focus_badge_row:
                        ui.icon('menu_book', size='14px').classes('text-indigo-600 shrink-0')
                        self.focus_title_label = ui.label(f"Focus: {self.focus_book_title or ''}").classes('text-xs font-bold text-indigo-700 truncate max-w-[110px] xs:max-w-[160px] sm:max-w-xs')
                        ui.button(icon='close', on_click=lambda e: (e.stop_propagation(), self.clear_book_focus())) \
                            .props('flat round dense size=xs color=indigo').tooltip('Clear Focus (Search All Library)').classes('shrink-0')
                    self.focus_badge_row.set_visibility(bool(self.focus_book_title))

                    # Entire Library Default Badge
                    self.default_badge_row = ui.row().classes('items-center gap-1 px-2.5 sm:px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200 shadow-sm cursor-pointer shrink-0').on('click', self.open_book_picker)
                    with self.default_badge_row:
                        ui.element('div').classes('w-2 h-2 rounded-full bg-emerald-500 animate-pulse shrink-0')
                        ui.label('Library Wide').classes('text-xs font-bold text-emerald-700')
                        ui.icon('arrow_drop_down', size='16px').classes('text-emerald-600 -ml-1')
                    self.default_badge_row.set_visibility(not bool(self.focus_book_title))

                # Right: Desktop Selectors, New Chat, & Dropdown Menu
                with ui.row().classes('items-center gap-1 sm:gap-2 shrink-0'):
                    with ui.row().classes('hidden md:flex items-center gap-1.5'):
                        self.style_select = ui.select(
                            list(STYLE_PROMPTS.keys()),
                            value=self.chat_style,
                            on_change=self.on_style_change
                        ).props('dense outlined rounded-xl options-dense bg-color=white').classes('text-xs w-28 sm:w-32')
                        self.style_select.tooltip('Select AI Response Persona & Depth')

                        self.teaching_btn = ui.button(
                            f"🎓 Teaching: {'ON' if self.teaching_mode else 'OFF'}",
                            on_click=self.toggle_teaching_mode
                        ).props(f'dense rounded-xl unelevated size=sm color={"indigo" if self.teaching_mode else "grey-7"}') \
                         .classes('font-bold text-xs shadow-sm')
                        self.teaching_btn.tooltip('Socratic mode guides you with thought-provoking questions')

                    ui.button(icon='add', on_click=self.start_new_chat) \
                        .props('dense round unelevated size=sm color=indigo') \
                        .tooltip('Start New Chat Session')

                    self._build_options_menu()

    def _build_options_menu(self):
        """Constructs chat settings and action menu."""
        with ui.button(icon='more_vert').props('flat round dense size=sm color=grey-7').tooltip('Chat Options'):
            with ui.menu().classes('rounded-2xl border border-slate-200 bg-white shadow-xl p-1.5 min-w-[200px]'):
                # Mobile persona selectors
                with ui.element('div').classes('md:hidden px-3 py-2 border-b border-slate-100 mb-1'):
                    ui.label('AI Persona & Style').classes('text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1')
                    ui.select(
                        list(STYLE_PROMPTS.keys()),
                        value=self.chat_style,
                        on_change=lambda e: (self.on_style_change(e), self.style_select.set_value(e.value) if self.style_select else None)
                    ).props('dense outlined rounded-xl options-dense bg-color=white').classes('text-xs w-full mb-2')

                    mob_teach_btn = ui.button(
                        f"🎓 Socratic Tutor: {'ON' if self.teaching_mode else 'OFF'}",
                        on_click=lambda: (
                            self.toggle_teaching_mode(),
                            mob_teach_btn.props(f'color={"indigo" if self.teaching_mode else "grey-7"}'),
                            mob_teach_btn.set_text(f"🎓 Socratic Tutor: {'ON' if self.teaching_mode else 'OFF'}")
                        )
                    ).props(f'dense rounded-xl unelevated size=xs color={"indigo" if self.teaching_mode else "grey-7"}').classes('w-full font-bold text-xs')

                ui.menu_item('🕒 View Chat History', on_click=self.toggle_history).classes('text-xs font-medium')
                ui.menu_item('📥 Export Chat (Markdown)', on_click=self.export_chat).classes('text-xs font-medium')
                ui.menu_item('📚 Change Document Scope', on_click=self.open_book_picker).classes('text-xs font-medium')
                ui.menu_item('🧹 Clear Current Conversation', on_click=self.clear_current_chat).classes('text-xs font-medium text-amber-600')
                ui.separator().classes('my-1')
                ui.menu_item('ℹ️ System Architecture', on_click=self.show_engine_info).classes('text-xs font-medium text-slate-500')

    def _build_chat_log_area(self):
        """Constructs scrollable log viewport and anchor."""
        with ui.column().classes('w-full flex-grow overflow-y-auto p-2.5 sm:p-4 md:p-6 no-scrollbar') as self.scroll_container:
            with ui.column().classes('w-full max-w-4xl mx-auto gap-3 sm:gap-4 pb-4') as self.log_container:
                pass
            self.scroll_anchor = ui.element('div').classes('h-px w-full')

    def _build_floating_input_bar(self):
        """Constructs bottom floating prompt input with attachment and action triggers."""
        with ui.column().classes('w-full p-2 sm:p-4 z-30 shrink-0 max-w-4xl mx-auto'):
            with ui.card().classes(
                'w-full bg-white/95 backdrop-blur-md border border-slate-200 '
                'p-1.5 sm:p-3 rounded-2xl sm:rounded-3xl shadow-xl gap-1'
            ):
                with ui.row().classes('w-full items-end gap-1 sm:gap-2'):
                    # Mobile compact action menu
                    with ui.button(icon='add_circle_outline').props('flat round dense color=indigo size=md').classes('flex sm:hidden shrink-0'):
                        ui.tooltip('Quick Actions')
                        with ui.menu().classes('rounded-2xl border border-slate-200 bg-white shadow-xl p-1 min-w-[180px]'):
                            ui.menu_item('📚 Scope to Document', on_click=self.open_book_picker).classes('text-xs font-medium')
                            ui.menu_item('☁️ Ingest Document', on_click=self.open_upload_dialog).classes('text-xs font-medium')
                            ui.menu_item('⏩ Continue Response', on_click=self.continue_generation).classes('text-xs font-medium')
                            ui.menu_item('🕒 Chat History', on_click=self.toggle_history).classes('text-xs font-medium')

                    # Tablet / Desktop action buttons
                    with ui.row().classes('hidden sm:flex items-center gap-1 shrink-0'):
                        ui.button(icon='history', on_click=self.toggle_history) \
                            .props('flat round dense color=indigo size=md').tooltip('View Chat History')

                        ui.button(icon='cloud_upload', on_click=self.open_upload_dialog) \
                            .props('flat round dense color=indigo size=md').tooltip('Ingest Document to Knowledge Base')

                        ui.button(icon='menu_book', on_click=self.open_book_picker) \
                            .props('flat round dense color=indigo size=md').tooltip('Scope Chat to a Specific Book')

                        self.continue_btn = ui.button(icon='fast_forward', on_click=self.continue_generation) \
                            .props('round dense color=amber size=md').tooltip('Continue Generating')
                        self.continue_btn.disable()

                    self.text_input = ui.textarea(
                        placeholder='Ask TARS anything... (Enter to send)'
                    ).props('rows=1 autogrow outlined rounded bg-color=slate-50') \
                     .classes('flex-grow text-sm max-h-36') \
                     .on('keydown.enter.prevent', self.send_message)

                    with ui.row().classes('shrink-0 items-center'):
                        self.send_btn = ui.button(icon='send', on_click=self.send_message) \
                            .props('round unelevated color=indigo size=md').classes('shadow-md hover:scale-105 transition-transform')
                        self.stop_btn = ui.button(icon='stop', on_click=self.stop_generation) \
                            .props('round color=red size=md shadow-md')
                        self.stop_btn.set_visibility(False)

                with ui.row().classes('w-full justify-center items-center pt-0.5 px-2'):
                    ui.label("🔒 100% Local & Private • Scoped ChromaDB Vector RAG • Multi-Engine AI").classes('text-[9px] sm:text-[10px] text-slate-400 font-medium text-center truncate max-w-full')

    # ==========================================
    # 🏁 MAIN PAGE ENTRY BUILDER
    # ==========================================

    def build_ui(self):
        """Constructs the complete Chat UI in a clean, non-nested composition."""
        # 1. Modals & Drawers
        self._build_upload_dialog()
        self._build_book_picker_dialog()
        self._build_history_drawer()

        # 2. Global Navigation Sidebar
        drawer = sidebar(chat_interface=self)

        # 3. Unified Top Bar (Includes Hamburger, History, Focus Scope, Options - No overlapping bars)
        self._build_top_control_bar(drawer)

        # 4. Chat Layout Shell (Clean fluid layout, zero bottom navigation)
        with ui.column().classes(
            'w-full h-[100dvh] pt-[calc(3.5rem+env(safe-area-inset-top,0px))] sm:pt-[calc(4rem+env(safe-area-inset-top,0px))] '
            'pb-[max(8px,env(safe-area-inset-bottom,0px))] bg-slate-50 overflow-hidden'
        ):
            self._build_chat_log_area()
            self._build_floating_input_bar()


async def chat_page():
    """Route handler for /chat."""
    app.storage.client['page_path'] = '/chat'
    chat = ChatInterface()
    chat.build_ui()
    await chat.initialize()