from nicegui import ui, run, app
from core.database.mongo_manager import mongo_db
from core.ai_engine.llm_engine import tars_engine 
from core.ai_engine.rag_pipeline import tars_archive 
from core.services.ingestion_service import ingestion_service
from core.config import settings
from pathlib import Path
import asyncio
import time
import uuid
import logging
import string

# IMPORT RESPONSIVE COMPONENTS
from components.sidebar import sidebar 
from components.header import header 
from components.bottom_nav import bottom_nav 

# Setup Interface Logger
logger = logging.getLogger("TARS_UI")

class ChatInterface:
    def __init__(self):
        # Session Logic
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
        
        # UI References
        self.log_container = None
        self.text_input = None
        self.upload_dialog = None
        self.session_input = None 
        self.send_btn = None
        self.stop_btn = None
        self.continue_btn = None 
        self.scroll_anchor = None 
        
        # State
        self.thinking = False
        self.abort_trigger = False
        self.teaching_mode = app.storage.user.get('teaching_mode', False)
        self.last_response_text = "" 
        self.saved_snippets = [] 

    def open_upload_dialog(self):
        if self.upload_dialog:
            self.upload_dialog.open()
        else:
            ui.notify("Upload system not initialized.", type='negative')

    async def initialize(self):
        if not self.log_container: return
        self.log_container.clear()
        
        if self.session_input:
             self.session_input.value = self.session_id

        try:
            history = await mongo_db.get_recent_history(self.session_id, limit=20)
            
            for msg in history:
                with self.log_container:
                    if msg['role'] == 'user':
                        with ui.row().classes('w-full justify-end'):
                            ui.label(msg.get('content', '...')).classes(
                                'px-3.5 py-2.5 sm:px-4 sm:py-3 bg-indigo-600 text-white rounded-2xl rounded-tr-none text-sm shadow-sm max-w-[88%] sm:max-w-[75%] break-words'
                            )
                    else:
                        with ui.row().classes('w-full justify-start'):
                            ui.markdown(msg.get('content', '...')).classes(
                                'p-3.5 sm:p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 '
                                'rounded-2xl rounded-tl-none shadow-sm max-w-[95%] sm:max-w-[85%] text-sm text-slate-800 dark:text-slate-100 break-words overflow-x-auto'
                            )
            
            self.scroll_to_bottom()
                            
        except Exception as e:
            ui.notify(f"History Load Error: {e}", type='warning')
            
        if self.continue_btn: self.continue_btn.disable()

    def scroll_to_bottom(self):
        if self.scroll_anchor:
            self.scroll_anchor.run_method('scrollIntoView', {'behavior': 'smooth', 'block': 'end'})

    def stop_generation(self):
        if self.thinking:
            self.abort_trigger = True
            ui.notify("Stopping...", type='warning')

    async def load_specific_session(self):
        """Called by Sidebar 'Load' button"""
        if not self.session_input: return
        new_id = self.session_input.value.strip()
        if not new_id: 
            ui.notify("Please enter a Session ID to load.", type='warning')
            return
        
        self.session_id = new_id
        app.storage.user['session_id'] = new_id
        self.saved_snippets = [] 
        await self.initialize()
        ui.notify(f"Synced to Session: {new_id}", type='positive')

    async def start_new_chat(self):
        """Called by Sidebar 'New' button"""
        new_id = str(uuid.uuid4())
        app.storage.user['session_id'] = new_id
        self.session_id = new_id
        ui.navigate.to('/chat') 

    def toggle_teaching_mode(self, e):
        """Called by Sidebar Toggle"""
        val = e.value if hasattr(e, 'value') else not self.teaching_mode
        self.teaching_mode = val
        app.storage.user['teaching_mode'] = self.teaching_mode
        status = "ENABLED" if self.teaching_mode else "DISABLED"
        color = "positive" if self.teaching_mode else "info"
        ui.notify(f"Teaching Mode {status}.", type=color)

    def save_last_response(self):
        """Saves current AI answer to snippets"""
        if not self.last_response_text:
            ui.notify("No response to save.", type='warning')
            return
        title = self.last_response_text[:30].replace('\n', ' ') + "..."
        self.saved_snippets.append({"title": title, "content": self.last_response_text})
        ui.notify("Snippet Saved.", type='positive')

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
            else:
                ui.notify(f"Ingestion failed: {result.get('error')}", type='negative')
        except Exception as err:
            logger.error(f"Upload Error: {err}")
            ui.notify(f"Upload Error: {err}", type='negative')

    async def continue_generation(self):
        """Continue generating where TARS left off."""
        if not self.last_response_text or self.thinking: return

        self.thinking = True
        self.abort_trigger = False
        if self.send_btn and self.stop_btn:
            self.send_btn.set_visibility(False)
            self.stop_btn.set_visibility(True)
        if self.continue_btn: self.continue_btn.disable()

        with self.log_container:
            with ui.row().classes('w-full justify-start mb-4'):
                with ui.column().classes('p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl rounded-tl-none shadow-sm max-w-[95%]'):
                    progress_bar = ui.linear_progress(value=0).props('indeterminate color=indigo')
                    message_content = ui.markdown()

        history_context = await mongo_db.get_recent_history(self.session_id, limit=6)
        persona_text = (
            "You are TARS, the Digital Librarian. CONTINUE your last response exactly where it left off. "
            "Maintain tone and formatting. Do not repeat the beginning."
        )

        system_prompt = {"role": "system", "content": persona_text}
        messages_payload = [system_prompt] + [{"role": m['role'], "content": m['content']} for m in history_context]
        
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
                    progress_bar.delete()
                    first_token = False
                response_buffer += token
                message_content.content = response_buffer
            
            self.last_response_text = response_buffer
            await mongo_db.add_message_to_session(self.session_id, "assistant", response_buffer)
            self.scroll_to_bottom() 
            
            if self.continue_btn:
                if not response_buffer.strip().endswith(('.', '!', '?', ':', ';', '```')):
                    self.continue_btn.enable()
                else:
                    self.continue_btn.disable()

        except Exception as e:
            try: progress_bar.delete() 
            except: pass
            with self.log_container: ui.label(f"SYSTEM FAILURE: {str(e)}").classes('text-red-500')
        
        self.thinking = False
        if self.send_btn and self.stop_btn:
            self.stop_btn.set_visibility(False)
            self.send_btn.set_visibility(True)
    
    async def send_message(self):
        if not self.text_input or not self.text_input.value: return
        text = self.text_input.value.strip()
        if not text or self.thinking: return
        
        is_review_mode = False
        
        # Commands
        if text == "/clear":
            await self.start_new_chat()
            return
        elif text.startswith("/review"):
            is_review_mode = True
            text = text.replace("/review", "").strip()
            if not text: 
                ui.notify("Paste code after /review", type='warning')
                return
        
        self.text_input.value = ''
        self.thinking = True
        self.abort_trigger = False
        
        if self.send_btn: self.send_btn.set_visibility(False)
        if self.stop_btn: self.stop_btn.set_visibility(True)
        if self.continue_btn: self.continue_btn.disable()

        # 1. User Message
        with self.log_container:
             with ui.row().classes('w-full justify-end mb-4'):
                ui.label(text).classes(
                    'px-3.5 py-2.5 sm:px-4 sm:py-3 bg-indigo-600 text-white rounded-2xl rounded-tr-none text-sm shadow-sm max-w-[88%] sm:max-w-[75%] break-words'
                )
        await mongo_db.add_message_to_session(self.session_id, "user", text)
        self.scroll_to_bottom()

        # 2. AI Placeholder
        with self.log_container:
            with ui.row().classes('w-full justify-start mb-4'):
                with ui.column().classes('p-3.5 sm:p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl rounded-tl-none shadow-sm max-w-[95%] sm:max-w-[85%] break-words overflow-x-auto'):
                    status = ui.label("Consulting archives...").classes('text-xs text-indigo-500 animate-pulse font-medium')
                    message_content = ui.markdown().classes('break-words overflow-x-auto max-w-full')

        # Intent Detection
        clean_input = text.lower().translate(str.maketrans('', '', string.punctuation)).strip()
        identity_keywords = ["who are you", "what are you", "identify", "your function", "introduce yourself"]
        simple_greeting_keywords = ["hello", "hi", "hey", "tars", "yo", "greetings", "good morning", "good afternoon", "good evening"]
        
        is_identity_query = any(k in clean_input for k in identity_keywords)
        is_simple_greeting = (
            clean_input in simple_greeting_keywords or 
            (len(clean_input.split()) <= 3 and any(g in clean_input for g in simple_greeting_keywords))
        )
        skip_rag = is_identity_query or is_simple_greeting
        rag_text = ""
        
        if not skip_rag:
            try:
                status.text = "Searching knowledge base..."
                hits = await run.io_bound(tars_archive.search, text, 3)
                if hits: rag_text = "\n\n[SEARCH RESULTS]:\n" + "\n---\n".join(hits)
            except Exception as e:
                logger.error(f"RAG Search Error: {e}")
        else:
            status.text = "Responding..."
            await asyncio.sleep(0.1)

        history = await mongo_db.get_recent_history(self.session_id, limit=6)
        
        # Real-time dynamic inventory from MongoDB!
        inventory = await mongo_db.get_library_inventory_summary(limit=10)
        
        persona = (
            "You are TARS, the Digital Librarian. You assist users with their personal digital library, study materials, and questions.\n"
            "Use the provided LIBRARY INVENTORY to tell users what books they have, and the KNOWLEDGE BASE to answer questions with precision.\n\n"
            f"1. **LIBRARY INVENTORY:**\n{inventory}\n"
            f"2. **KNOWLEDGE BASE:**\n{rag_text}\n"
        )
        if self.teaching_mode: 
            persona += "\nTEACHING MODE: Socratic teaching style. Guide the user with questions rather than immediate answers."
        elif is_review_mode: 
            persona += "\nCODE REVIEW MODE: Review provided code for architecture, performance, security, and cleanliness."

        valid_history = []
        for m in history:
            if m and 'role' in m and 'content' in m:
                valid_history.append({"role": m['role'], "content": m['content']})
        
        messages = [{"role": "system", "content": persona}] + valid_history

        # Stream Generation
        status.text = "Writing response..."
        response_buffer = ""
        try:
            first = True
            async for token in tars_engine.stream_response(messages):
                if self.abort_trigger: break
                if first:
                    status.delete() 
                    first = False
                response_buffer += token
                message_content.content = response_buffer
            
            self.last_response_text = response_buffer
            await mongo_db.add_message_to_session(self.session_id, "assistant", response_buffer)
            self.scroll_to_bottom() 
            
            title = text[:30] + "..." 
            await mongo_db.save_chat_metadata(self.session_id, title)

            if self.continue_btn:
                if not response_buffer.strip().endswith(('.', '!', '?', ':', ';', '```')):
                    self.continue_btn.enable()
                else:
                    self.continue_btn.disable()

        except Exception as e:
            try: status.delete() 
            except Exception: pass
            error_msg = "Generation encountered an issue. Check system logs."
            logger.error(f"LLM Generation failure: {e}", exc_info=True)
            with self.log_container: ui.label(error_msg).classes('text-red-500')

        self.thinking = False
        if self.send_btn: self.send_btn.set_visibility(True)
        if self.stop_btn: self.stop_btn.set_visibility(False)

    def build_ui(self):
        # 1. UPLOAD DIALOG
        with ui.dialog() as self.upload_dialog, ui.card().classes('w-[calc(100vw-2rem)] max-w-md p-5 sm:p-6 rounded-2xl sm:rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-2xl'):
            ui.label("Ingest Document to TARS").classes('text-lg font-bold text-slate-800 dark:text-slate-100')
            ui.label("Upload PDF, EPUB, DOCX, PPTX, or TXT into your library & knowledge base.").classes('text-xs text-slate-500 dark:text-slate-400 mb-4')
            ui.upload(on_upload=self.handle_upload, auto_upload=True).props('accept=".pdf,.epub,.docx,.pptx,.txt" color=indigo flat bordered').classes('w-full border-2 border-dashed border-indigo-200 rounded-xl')
            ui.button('Close', on_click=self.upload_dialog.close).props('flat color=grey size=md').classes('w-full mt-3')
        
        # 2. RESPONSIVE NAVIGATION
        drawer = sidebar(chat_interface=self) 
        header(drawer_reference=drawer)
        bottom_nav()
        
        # 3. MAIN LAYOUT
        with ui.column().classes('w-full h-screen pt-16 pb-16 md:pb-0 bg-slate-50 dark:bg-slate-950 overflow-hidden'):
            
            # Scrollable Chat Log
            with ui.column().classes('w-full flex-grow overflow-y-auto p-3 sm:p-4 md:p-6 no-scrollbar') as self.scroll_container:
                with ui.column().classes('w-full max-w-4xl mx-auto gap-3 sm:gap-4 pb-4') as self.log_container:
                    ui.label(f'Session: {self.session_id}').classes('text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest self-center my-1 sm:my-2')
                
                self.scroll_anchor = ui.element('div').classes('h-px w-full')

            # Sticky Input Bar (Redesigned with top tool bar and full-width input for mobile)
            with ui.column().classes(
                'w-full bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border-t border-slate-200 dark:border-slate-800 '
                'p-2.5 sm:p-3 md:p-4 gap-1.5 z-30 shrink-0 max-w-4xl mx-auto rounded-t-2xl sm:rounded-t-3xl shadow-lg'
            ):
                # Action buttons row
                with ui.row().classes('w-full items-center justify-between px-1'):
                    with ui.row().classes('items-center gap-1'):
                        ui.button(icon='cloud_upload', on_click=lambda: self.upload_dialog.open()).props('flat round dense color=indigo size=sm').tooltip('Upload Material')
                        self.continue_btn = ui.button(icon='fast_forward', on_click=self.continue_generation).props('round dense color=amber size=sm').tooltip('Continue Generating')
                        self.continue_btn.disable()
                        ui.button(icon='bookmark', on_click=self.save_last_response).props('flat round dense color=indigo size=sm').tooltip('Save Note')
                    with ui.row().classes('items-center gap-1'):
                        ui.button(icon='delete_sweep', on_click=self.start_new_chat).props('flat round dense color=grey size=sm').tooltip('Clear / New Chat')

                # Input and send button row
                with ui.row().classes('w-full items-end gap-2'):
                    self.text_input = ui.textarea(placeholder='Ask TARS anything...').props('rows=1 autogrow outlined rounded bg-color=slate-50') \
                        .classes('flex-grow text-sm max-h-32') \
                        .on('keydown.enter.prevent', self.send_message)
                    with ui.row().classes('shrink-0'):
                        self.send_btn = ui.button(icon='send', on_click=self.send_message).props('round unelevated color=indigo size=md').classes('shadow-md')
                        self.stop_btn = ui.button(icon='stop', on_click=self.stop_generation).props('round color=red size=md shadow-md')
                        self.stop_btn.set_visibility(False)

async def chat_page():
    app.storage.client['page_path'] = '/chat' 
    chat = ChatInterface()
    chat.build_ui()
    await chat.initialize()