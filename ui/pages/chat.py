from nicegui import ui, run, app
from core.database.mongo_manager import mongo_db
from core.ai_engine.llm_engine import tars_engine
from core.services.ingestion_service import ingestion_service
from core.config import settings
from pathlib import Path
from datetime import datetime
import asyncio
import time
import uuid
import logging
from typing import Optional, Dict, Any, List, Tuple

from components.sidebar import sidebar
from core.services.chat_service import (
    chat_service,
    STYLE_PROMPTS,
    STARTER_PROMPTS_BOOK,
    STARTER_PROMPTS_LIBRARY,
    group_sessions_chronologically,
)
from components.chat import (
    setup_message_actions,
    render_citation_chips,
    render_user_message,
    render_assistant_message,
    render_welcome_state,
    linkify_tars_citations,
    ChatHistoryDrawer,
    BookPickerDialog,
    open_upload_dialog,
    show_architecture_dialog,
    ChatInputBar,
)

logger = logging.getLogger("TARS_UI")


class ChatInterface:
    """
    Modular, high-performance controller for TARS AI Librarian Chat.
    Orchestrates session state, scoped vector RAG, and streaming responses
    through dedicated components in `components/chat/`.
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
        self.course_code_scope = app.storage.user.get('chat_course_code_scope')
        self.course_options = {"": "All Library Catalog"}
        self.course_select = None
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

        # Component References
        self.history_drawer_comp = ChatHistoryDrawer(
            on_new_chat=self.start_new_chat,
            on_select_session=self.switch_session,
            on_delete_session=self.delete_session_ui,
        )
        self.book_picker_comp = BookPickerDialog(
            on_select_book=self.set_book_focus,
            on_clear_focus=self.clear_book_focus,
        )
        self.input_bar_comp = ChatInputBar(
            on_send=self.send_message,
            on_stop=self.stop_generation,
            on_continue=self.continue_generation,
            on_open_history=self.toggle_history,
            on_open_upload=self.open_upload_dialog,
            on_open_book_picker=self.open_book_picker,
        )

        self.history_top_badge = None

        # 4. State & Caches
        self.cached_sessions = []
        self.cached_books = []
        self.thinking = False
        self.is_generating = False
        self.cancel_event = asyncio.Event()
        self.focus_book_meta: Optional[Dict[str, Any]] = None
        self.abort_trigger = False
        self.teaching_mode = app.storage.user.get('teaching_mode', False)
        self.chat_style = app.storage.user.get('chat_style', 'Balanced')
        self.last_response_text = ""

    # Compatibility properties for external references
    @property
    def history_drawer(self):
        return self.history_drawer_comp.drawer

    @property
    def book_picker_dialog(self):
        return self.book_picker_comp.dialog

    @property
    def text_input(self):
        return self.input_bar_comp.text_input

    @property
    def send_btn(self):
        return self.input_bar_comp.send_btn

    @property
    def stop_btn(self):
        return self.input_bar_comp.stop_btn

    @property
    def continue_btn(self):
        return self.input_bar_comp.continue_btn

    def _set_generating_state(self, is_generating: bool):
        self.thinking = is_generating
        self.is_generating = is_generating
        self.input_bar_comp.set_generating_state(is_generating)

    def scroll_to_bottom(self):
        if self.scroll_anchor:
            self.scroll_anchor.run_method('scrollIntoView', {'behavior': 'smooth', 'block': 'end'})

    def update_focus_badges(self):
        has_focus = bool(self.focus_book_title)
        if self.focus_title_label and self.focus_book_title:
            self.focus_title_label.text = f"Focus: {self.focus_book_title}"
        if self.focus_badge_row:
            self.focus_badge_row.set_visibility(has_focus)
        if self.default_badge_row:
            self.default_badge_row.set_visibility(not has_focus)

    def clear_book_focus(self):
        self.focus_book_id = None
        self.focus_book_title = None
        self.focus_book_meta = None
        app.storage.user.pop('chat_focus_book_id', None)
        app.storage.user.pop('chat_focus_book_title', None)
        self.update_focus_badges()
        ui.notify("Chat focus reset to entire library.", type='info')
        if hasattr(self, 'welcome_container') and self.welcome_container:
            self.render_welcome_state()

    def set_book_focus(self, book: dict):
        self.focus_book_id = book.get('id')
        self.focus_book_title = book.get('title', 'Selected Document')
        self.focus_book_meta = book
        app.storage.user['chat_focus_book_id'] = self.focus_book_id
        app.storage.user['chat_focus_book_title'] = self.focus_book_title
        self.update_focus_badges()
        self.book_picker_comp.close()
        ui.notify(f"Chat focused on: '{self.focus_book_title}'", type='positive')
        if hasattr(self, 'welcome_container') and self.welcome_container:
            self.render_welcome_state()

    async def load_course_scopes(self):
        try:
            user_prog = app.storage.user.get('program') or app.storage.user.get('department')
            courses = await mongo_db.syllabus.get_available_course_scopes(user_prog)
            opts = {"": "All Library Catalog"}
            for c in courses:
                opts[c["course_code"]] = c["display_name"]
            self.course_options = opts
            if self.course_select:
                self.course_select.options = self.course_options
                if self.course_code_scope and self.course_code_scope in self.course_options:
                    self.course_select.value = self.course_code_scope
                else:
                    self.course_select.value = ""
                self.course_select.update()
        except Exception as e:
            logger.debug("Failed loading course scopes: %s", e)

    def on_course_scope_change(self, e):
        val = (e.value or "").strip()
        if val:
            self.course_code_scope = val
            app.storage.user['chat_course_code_scope'] = val
            label = self.course_options.get(val, val)
            ui.notify(f"Vector search scoped to: {label}", type='positive')
        else:
            self.course_code_scope = None
            app.storage.user.pop('chat_course_code_scope', None)
            ui.notify("Vector search scoped to entire library catalog.", type='info')

    async def open_book_picker(self):
        if not self.cached_books:
            try:
                self.cached_books = await mongo_db.get_recent_books(limit=100)
            except Exception as e:
                logger.error(f"Book Picker Load Error: {e}")
        self.book_picker_comp.open(self.cached_books, self.focus_book_id)

    def toggle_history(self):
        self.history_drawer_comp.toggle()

    async def load_and_refresh_history(self):
        try:
            uid = app.storage.user.get('user_id')
            self.cached_sessions = await mongo_db.get_chat_sessions(limit=60, user_id=uid) or []
            if self.history_top_badge:
                self.history_top_badge.text = str(len(self.cached_sessions))
            self.history_drawer_comp.update_sessions(self.cached_sessions, self.session_id)
        except Exception as e:
            logger.error(f"History refresh error: {e}")

    async def switch_session(self, session_id: str):
        if self.session_id == session_id and self.log_container and len(self.log_container.default_slot.children) > 0:
            self.history_drawer_comp.hide()
            return

        self.session_id = session_id
        app.storage.user['session_id'] = session_id
        self.history_drawer_comp.hide()

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
        try:
            ui.notify("Loaded conversation history.", type='info')
        except Exception:
            pass
        await self.initialize()
        self.history_drawer_comp.update_sessions(self.cached_sessions, self.session_id)

    async def delete_session_ui(self, sid: str):
        try:
            ui.notify("Chat session deleted.", type='info')
        except Exception:
            pass

        try:
            await mongo_db.delete_chat_session(sid)
            self.cached_sessions = [s for s in self.cached_sessions if s.get('id') != sid]
            if self.history_top_badge:
                self.history_top_badge.text = str(len(self.cached_sessions))

            if sid == self.session_id:
                await self.start_new_chat(show_notify=False)
            else:
                self.history_drawer_comp.update_sessions(self.cached_sessions, self.session_id)
        except Exception as e:
            logger.error(f"Session deletion error: {e}")

    async def start_new_chat(self, show_notify: bool = True):
        if show_notify:
            try:
                ui.notify("New chat started.", type='positive')
            except Exception:
                pass

        new_id = str(uuid.uuid4())
        app.storage.user['session_id'] = new_id
        self.session_id = new_id
        self.last_response_text = ""

        if self.log_container:
            self.log_container.clear()

        self.render_welcome_state()
        self.history_drawer_comp.update_sessions(self.cached_sessions, self.session_id)
        self.history_drawer_comp.hide()

    async def export_chat(self):
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
        try:
            ui.notify("Conversation cleared.", type='info')
        except Exception:
            pass
        try:
            await mongo_db.delete_chat_session(self.session_id)
            if self.log_container:
                self.log_container.clear()
            self.render_welcome_state()
            await self.load_and_refresh_history()
        except Exception as e:
            logger.error(f"Clear failed: {e}")
            try:
                ui.notify(f"Clear failed: {e}", type='negative')
            except Exception:
                pass

    def open_upload_dialog(self):
        open_upload_dialog(on_upload=self.handle_upload)

    def on_style_change(self, e):
        self.chat_style = e.value
        app.storage.user['chat_style'] = self.chat_style
        ui.notify(f"Response style set to: {self.chat_style}", type='info')

    def toggle_teaching_mode(self, e=None):
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
        show_architecture_dialog()

    async def handle_upload(self, e):
        try:
            from ui.pages.upload import SmartFileAdapter
            adapter = SmartFileAdapter(e)
            fname = adapter.name

            ui.notify(f"Ingesting '{fname}'...", type='info')
            result = await ingestion_service.process_upload(adapter, fname)

            if result.get('success'):
                ui.notify(result.get('message', 'File ingested successfully.'), type='positive')
                self.cached_books = []
            else:
                ui.notify(f"Ingestion failed: {result.get('error')}", type='negative')
        except Exception as err:
            logger.error(f"Upload Error: {err}")
            ui.notify(f"Upload Error: {err}", type='negative')

    def render_welcome_state(self):
        self.welcome_container = render_welcome_state(
            container=self.log_container,
            focus_book_title=self.focus_book_title,
            on_preset_click=self.submit_preset_prompt,
        )

    async def submit_preset_prompt(self, prompt_text: str):
        if self.thinking:
            return
        self.input_bar_comp.value = prompt_text
        await self.send_message()

    def render_user_message(self, text: str):
        render_user_message(self.log_container, text)

    def render_assistant_message(self, content: str = "", citations: list = None, in_progress: bool = False):
        return render_assistant_message(
            container=self.log_container,
            content=content,
            citations=citations,
            in_progress=in_progress,
            teaching_mode=self.teaching_mode,
        )

    def _is_client_connected(self) -> bool:
        """Returns True if the current NiceGUI client is alive and connected."""
        try:
            if not hasattr(self, 'log_container') or not self.log_container:
                return False
            client_ref = getattr(self.log_container, '_client', None)
            if client_ref is None:
                return False
            c = client_ref()
            if c is None or getattr(c, '_deleted', False) or getattr(c, 'has_been_deleted', False):
                return False
            return True
        except Exception:
            return False

    async def initialize(self):
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
        await self.load_course_scopes()

    def stop_generation(self):
        if self.thinking or self.is_generating:
            self.abort_trigger = True
            self.cancel_event.set()
            ui.notify("Stopping...", type='warning')

    async def continue_generation(self):
        if not self.last_response_text or self.thinking:
            return

        self._set_generating_state(True)
        self.abort_trigger = False

        card, status_label, message_content, copy_btn, tts_btn, citations_container = self.render_assistant_message(in_progress=True)
        if status_label:
            status_label.text = "Continuing with next document sections..."

        history_context = await mongo_db.get_recent_history(self.session_id, limit=6)
        rag_text = ""
        citations = []
        if self.focus_book_id or self.course_code_scope:
            rag_text, citations = await chat_service.perform_rag_search(
                "continue",
                self.focus_book_id,
                self.focus_book_title,
                history=history_context,
                course_code_scope=self.course_code_scope,
            )

        persona_text = (
            "You are TARS, the Digital Librarian. CONTINUE your response by advancing to the next sections or principles of the document. "
            "Do NOT repeat points already stated. Maintain academic depth and formatting."
        )

        messages_payload = chat_service.build_messages_payload(
            system_persona=persona_text,
            history=history_context,
            current_query="Please continue with the next sections or details of the document.",
            rag_text=rag_text,
            max_turns=6
        )
        await asyncio.sleep(0.05)
        response_buffer = ""
        try:
            first_token = True
            last_render_time = time.time()
            async for token in tars_engine.stream_response(messages_payload, max_tokens=1500):
                if self.abort_trigger or not self._is_client_connected():
                    response_buffer += " ... [STOPPED]"
                    try:
                        message_content.content = response_buffer
                    except Exception:
                        pass
                    break
                if first_token:
                    if status_label:
                        try: status_label.delete()
                        except Exception: pass
                    first_token = False
                response_buffer += token
                now = time.time()
                if now - last_render_time >= 0.065 or token in ('\n', '. ', '? ', '! '):
                    try:
                        message_content.content = response_buffer
                    except Exception:
                        if not self._is_client_connected():
                            break
                    last_render_time = now

            if not self._is_client_connected():
                if response_buffer:
                    await mongo_db.add_message_to_session(self.session_id, "assistant", response_buffer)
                return

            try:
                linkified = linkify_tars_citations(response_buffer, citations) if citations else response_buffer
                message_content.content = linkified
                self.last_response_text = response_buffer
                await mongo_db.add_message_to_session(self.session_id, "assistant", response_buffer)
                if citations and citations_container:
                    render_citation_chips(citations, citations_container)
                self.scroll_to_bottom()
                setup_message_actions(response_buffer, copy_btn, tts_btn)

                if self.continue_btn:
                    has_ended = response_buffer.strip().endswith(('.', '!', '?', ':', ';', '```'))
                    if not has_ended:
                        self.continue_btn.enable()
                    else:
                        self.continue_btn.disable()
            except RuntimeError as re:
                if 'deleted' in str(re).lower():
                    return
                raise
        except Exception as e:
            if status_label:
                try: status_label.delete()
                except Exception: pass
            err_msg = str(e).lower()
            if 'deleted' in err_msg or 'client' in err_msg:
                logger.info("Continue generation ended cleanly after client disconnected.")
                return
            logger.error(f"Continue generation failure: {e}", exc_info=True)
            if self._is_client_connected() and self.log_container:
                try:
                    with self.log_container:
                        ui.label(f"SYSTEM FAILURE: {str(e)}").classes('text-rose-500 font-bold')
                except Exception:
                    pass
        finally:
            if self._is_client_connected():
                self._set_generating_state(False)

    async def send_message(self):
        text = self.input_bar_comp.value.strip()
        if not text or self.thinking or self.is_generating:
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

        if hasattr(self, 'welcome_container') and self.welcome_container:
            try: self.welcome_container.delete()
            except Exception: pass
            self.welcome_container = None

        self.input_bar_comp.value = ''
        self._set_generating_state(True)
        self.abort_trigger = False
        self.cancel_event.clear()

        # 1. Render user bubble in UI immediately
        self.render_user_message(text)
        self.scroll_to_bottom()

        # 2. Fetch prior history BEFORE queueing the new user message write
        history = await mongo_db.get_recent_history(self.session_id, limit=12)

        # Persist user message asynchronously
        asyncio.create_task(
            mongo_db.add_message(
                session_id=self.session_id,
                role="user",
                content=text,
                book_id=self.focus_book_id,
            )
        )

        # 3. Assistant Placeholder Card
        card, status, message_content, copy_btn, tts_btn, citations_container = self.render_assistant_message(in_progress=True)

        # 4. Classify intent & perform strict-threshold RAG retrieval
        is_greeting = chat_service.is_greeting_or_identity(text)
        skip_rag = chat_service.should_skip_rag(text)

        rag_text = ""
        citations = []
        if not skip_rag:
            if status:
                status.text = "Searching knowledge base..."
            focus_title = (
                self.focus_book_meta.get("title")
                if self.focus_book_meta
                else self.focus_book_title
            )
            rag_text, citations = await chat_service.perform_rag_search(
                query=text,
                focus_book_id=self.focus_book_id,
                focus_book_title=focus_title,
                course_code_scope=self.course_code_scope,
            )
        else:
            if status:
                status.text = "Responding..."
            await asyncio.sleep(0.05)

        # 5. Build system persona & user-turn grounded payload
        persona = chat_service.build_system_persona(
            chat_style=self.chat_style,
            focus_book=self.focus_book_meta,
            focus_book_title=self.focus_book_title,
            is_greeting=is_greeting,
            teaching_mode=self.teaching_mode,
            is_review_mode=is_review_mode,
        )
        messages = chat_service.build_messages_payload(
            system_persona=persona,
            history=history,
            current_query=text,
            rag_text=rag_text,
            max_turns=6,
        )

        # 6. Stream assistant tokens into UI bubble
        if status:
            status.text = "Synthesizing answer..."
        response_buffer = ""
        is_summary = any(k in text.lower() for k in (
            "summarize", "summary", "overview", "everything", "all topics", "lecture", "study guide", "explain all", "all slides", "continue"
        ))
        if is_summary or self.chat_style == 'Exam Prep':
            effective_tokens = 1500
        elif self.chat_style in ('Academic', 'Socratic') or self.teaching_mode:
            effective_tokens = 750
        else:
            effective_tokens = 400

        try:
            first = True
            last_render_time = time.time()
            async for token in tars_engine.stream_response(
                messages=messages,
                max_tokens=effective_tokens,
                cancel_event=self.cancel_event,
            ):
                if self.abort_trigger or self.cancel_event.is_set() or not self._is_client_connected():
                    break
                if first:
                    if status:
                        try: status.delete()
                        except Exception: pass
                    first = False
                response_buffer += token
                now = time.time()
                if now - last_render_time >= 0.065 or token in ('\n', '. ', '? ', '! '):
                    try:
                        message_content.content = response_buffer
                    except Exception:
                        if not self._is_client_connected():
                            break
                    last_render_time = now

            if not self._is_client_connected():
                if response_buffer:
                    await mongo_db.add_message(
                        session_id=self.session_id,
                        role="assistant",
                        content=response_buffer,
                        citations=citations,
                        book_id=self.focus_book_id,
                    )
                return

            try:
                full_response = response_buffer.strip()
                linkified = linkify_tars_citations(full_response, citations) if citations else full_response
                message_content.content = linkified
                setup_message_actions(full_response, copy_btn, tts_btn)

                # 7. Render verified citation chips only when grounded chunks were used
                if citations and citations_container and full_response:
                    render_citation_chips(citations, citations_container)

                self.last_response_text = full_response

                # 8. Persist assistant response
                if full_response:
                    await mongo_db.add_message(
                        session_id=self.session_id,
                        role="assistant",
                        content=full_response,
                        citations=citations,
                        book_id=self.focus_book_id,
                    )

                self.scroll_to_bottom()

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
                    has_ended = full_response.endswith(('.', '!', '?', ':', ';', '```'))
                    if not has_ended:
                        self.continue_btn.enable()
                    else:
                        self.continue_btn.disable()
            except RuntimeError as re:
                if 'deleted' in str(re).lower():
                    if response_buffer:
                        await mongo_db.add_message(
                            session_id=self.session_id,
                            role="assistant",
                            content=response_buffer,
                            citations=citations,
                            book_id=self.focus_book_id,
                        )
                    return
                raise
        except Exception as e:
            if status:
                try: status.delete()
                except Exception: pass

            err_msg = str(e).lower()
            if 'deleted' in err_msg or 'client' in err_msg:
                logger.info("Chat stream completed or cancelled after client disconnected.")
                return

            logger.error(f"LLM Generation failure: {e}", exc_info=True)
            if self._is_client_connected() and self.log_container:
                try:
                    with self.log_container:
                        ui.label("Generation encountered an issue. Check system logs.").classes('text-rose-500 font-bold')
                except Exception:
                    pass
        finally:
            if self._is_client_connected():
                self._set_generating_state(False)

    def _build_top_control_bar(self, drawer):
        with ui.header().classes(
            'bg-white/95 backdrop-blur-md border-b border-slate-200 '
            'items-center px-2 sm:px-4 md:px-6 h-14 sm:h-16 pt-[env(safe-area-inset-top,0px)] '
            'fixed top-0 w-full z-40 select-none shadow-sm'
        ).props('elevated=False'):
            with ui.row().classes('w-full max-w-5xl mx-auto items-center justify-between gap-1.5 sm:gap-2 flex-nowrap'):
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

                    self.focus_badge_row = ui.row().classes(
                        'items-center gap-1 px-2.5 sm:px-3 py-1 rounded-full bg-indigo-50 border border-indigo-200 shadow-sm cursor-pointer min-w-0'
                    ).on('click', self.open_book_picker)
                    with self.focus_badge_row:
                        ui.icon('menu_book', size='14px').classes('text-indigo-600 shrink-0')
                        self.focus_title_label = ui.label(f"Focus: {self.focus_book_title or ''}").classes(
                            'text-xs font-bold text-indigo-700 truncate max-w-[110px] xs:max-w-[160px] sm:max-w-xs'
                        )
                        ui.button(icon='close', on_click=lambda e: (e.stop_propagation(), self.clear_book_focus())) \
                            .props('flat round dense size=xs color=indigo').tooltip('Clear Focus (Search All Library)').classes('shrink-0')
                    self.focus_badge_row.set_visibility(bool(self.focus_book_title))

                    self.default_badge_row = ui.row().classes(
                        'items-center gap-1 px-2.5 sm:px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200 shadow-sm cursor-pointer shrink-0'
                    ).on('click', self.open_book_picker)
                    with self.default_badge_row:
                        ui.element('div').classes('w-2 h-2 rounded-full bg-emerald-500 animate-pulse shrink-0')
                        ui.label('Library Wide').classes('text-xs font-bold text-emerald-700')
                        ui.icon('arrow_drop_down', size='16px').classes('text-emerald-600 -ml-1')
                    self.default_badge_row.set_visibility(not bool(self.focus_book_title))

                    # Course Syllabus Scope Dropdown
                    self.course_select = ui.select(
                        self.course_options,
                        value=self.course_code_scope or "",
                        on_change=self.on_course_scope_change,
                    ).props('dense outlined rounded-xl options-dense bg-color=white').classes(
                        'text-xs min-w-[125px] max-w-[175px] shrink-0'
                    )
                    self.course_select.tooltip('Scope RAG vector search to approved course curriculum textbooks')

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

                    with ui.button(icon='more_vert').props('flat round dense size=sm color=grey-7').tooltip('Chat Options'):
                        with ui.menu().classes('rounded-2xl border border-slate-200 bg-white shadow-xl p-1.5 min-w-[200px]'):
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

    def build_ui(self):
        # 1. Dialogs & Drawer
        self.book_picker_comp.build()
        self.history_drawer_comp.build()

        # 2. Sidebar & Top Bar
        drawer = sidebar(chat_interface=self)
        self._build_top_control_bar(drawer)

        # 3. Main Chat Viewport
        with ui.column().classes(
            'w-full fixed top-14 sm:top-16 inset-x-0 bottom-0 flex flex-col bg-slate-50 overflow-hidden p-0 m-0'
        ):
            with ui.column().classes('w-full flex-1 min-h-0 overflow-y-auto p-2.5 sm:p-4 md:p-6 no-scrollbar touch-pan-y overscroll-contain') as self.scroll_container:
                with ui.column().classes('w-full max-w-4xl mx-auto gap-3 sm:gap-4 pb-4') as self.log_container:
                    pass
                self.scroll_anchor = ui.element('div').classes('h-px w-full')

            self.input_bar_comp.build()


async def chat_page():
    app.storage.client['page_path'] = '/chat'
    chat = ChatInterface()
    chat.build_ui()
    await chat.initialize()