import asyncio
import time
import uuid
from nicegui import ui, app
from core.ai_engine.llm_engine import tars_engine
from core.database.mongo_manager import mongo_db
from core.services.chat_service import chat_service
from components.chat.message_bubble import (
    render_assistant_message,
    render_citation_chips,
    render_user_message,
)


class FloatingChat:
    """Compact floating assistant unified with the main ChatService grounding pipeline."""

    def __init__(self, session_id: str = None):
        self.session_id = session_id or (app.storage.user.get('session_id') if hasattr(app, 'storage') else None) or f"floating_{uuid.uuid4().hex[:8]}"
        self.cancel_event = asyncio.Event()
        self.is_generating = False
        self.thinking = False
        self.visible = False
        self.dialog = None
        self.log_container = None
        self.text_input = None
        self._build_ui()

    def toggle(self):
        self.visible = not self.visible
        if self.visible:
            if not self.dialog:
                self._build_dialog()
            self.dialog.open()
            if self.log_container:
                ui.run_javascript(f'const el = document.getElementById("{self.log_container.id}"); if(el) el.scrollTop = el.scrollHeight;')
        else:
            if self.dialog:
                self.dialog.close()

    async def handle_send(self, text: str, message_container=None) -> None:
        text = (text or "").strip()
        if not text or self.is_generating:
            return

        container = message_container or self.log_container
        if not container:
            return

        self.is_generating = True
        self.thinking = True
        self.cancel_event.clear()

        try:
            render_user_message(container, text)

            skip_rag = chat_service.should_skip_rag(text)
            is_greeting = chat_service.is_greeting_or_identity(text)
            rag_text = ""
            citations = []
            if not skip_rag:
                rag_text, citations = await chat_service.perform_rag_search(
                    text, None, None
                )

            history = await mongo_db.get_recent_history(self.session_id, limit=4)
            asyncio.create_task(
                mongo_db.add_message(
                    session_id=self.session_id,
                    role="user",
                    content=text,
                )
            )

            persona = chat_service.build_system_persona(
                chat_style="Concise",
                is_greeting=is_greeting,
            )
            messages = chat_service.build_messages_payload(
                persona,
                history,
                current_query=text,
                rag_text=rag_text,
                max_turns=4,
            )

            res = render_assistant_message(container, "", in_progress=True)
            if isinstance(res, (tuple, list)):
                if len(res) == 2:
                    bubble_label, bubble_wrapper = res
                    citations_container = bubble_wrapper
                elif len(res) >= 3:
                    card, status_label, bubble_label = res[0], res[1], res[2]
                    citations_container = res[5] if len(res) > 5 else card
                    bubble_wrapper = card
            else:
                bubble_label = res
                bubble_wrapper = container
                citations_container = container

            chunks = []
            last_render_time = time.time()
            async for token in tars_engine.stream_response(
                messages=messages,
                max_tokens=400,
                cancel_event=self.cancel_event,
            ):
                if self.cancel_event.is_set():
                    break
                chunks.append(token)
                now = time.time()
                if now - last_render_time >= 0.06 or token in ('\n', '. ', '? ', '! '):
                    new_text = "".join(chunks)
                    if hasattr(bubble_label, 'set_content'):
                        bubble_label.set_content(new_text)
                    elif hasattr(bubble_label, 'content'):
                        bubble_label.content = new_text
                    last_render_time = now

            final_answer = "".join(chunks).strip()
            if hasattr(bubble_label, 'set_content'):
                bubble_label.set_content(final_answer)
            elif hasattr(bubble_label, 'content'):
                bubble_label.content = final_answer

            if citations and final_answer and citations_container:
                render_citation_chips(citations, citations_container)

            if final_answer:
                await mongo_db.add_message(
                    session_id=self.session_id,
                    role="assistant",
                    content=final_answer,
                    citations=citations,
                )
        finally:
            self.is_generating = False
            self.thinking = False

    async def send_message(self):
        if not self.text_input or not self.text_input.value:
            return
        text = self.text_input.value.strip()
        if not text:
            return
        self.text_input.value = ''
        await self.handle_send(text, self.log_container)

    def _build_ui(self):
        with ui.button(on_click=self.toggle) \
            .props('round color=slate-900 size=md sm:size=lg') \
            .classes('inline-flex fixed bottom-5 right-4 sm:bottom-6 sm:right-6 z-40 shadow-2xl hover:scale-105 active:scale-95 transition-transform p-2 border border-slate-700/60'):
            ui.image('/static/tars_icon.svg').classes('w-6 h-6 sm:w-7 sm:h-7 object-contain').props('no-spinner')
            ui.tooltip('Ask TARS AI Librarian')

    def _build_dialog(self):
        with ui.dialog() as self.dialog, ui.card().classes(
            'w-[calc(100vw-1.5rem)] max-w-sm h-[75dvh] max-h-[520px] p-0 flex flex-col fixed '
            'bottom-4 right-3 sm:bottom-6 sm:right-6 shadow-2xl rounded-3xl '
            'border border-slate-200 overflow-hidden bg-white z-50'
        ):
            with ui.row().classes('w-full bg-slate-900 p-3.5 items-center justify-between text-white shrink-0 border-b border-slate-800'):
                with ui.row().classes('items-center gap-2.5'):
                    ui.image('/static/tars_icon.svg').classes('w-6 h-6 object-contain').props('no-spinner')
                    ui.label('TARS Quick Assistant').classes('font-bold text-sm text-white')
                ui.button(icon='close', on_click=self.toggle).props('flat round dense color=white size=sm')

            self.log_container = ui.column().classes('w-full flex-grow overflow-y-auto p-4 bg-slate-50 gap-2.5 break-words')
            self.log_container.props('id=floating-chat-log')

            with ui.row().classes('w-full p-2.5 bg-white border-t border-slate-200 items-center gap-1.5 shrink-0'):
                self.text_input = ui.input(placeholder='Ask TARS...').props('dense rounded outlined bg-color=slate-50') \
                    .classes('flex-grow text-sm').on('keydown.enter.prevent', self.send_message)
                ui.button(icon='send', on_click=self.send_message).props('flat round dense color=indigo size=md')