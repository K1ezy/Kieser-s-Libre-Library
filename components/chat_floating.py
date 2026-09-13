from nicegui import ui, app, run
from core.database.mongo_manager import mongo_db
from core.ai_engine.llm_engine import tars_engine
from core.ai_engine.rag_pipeline import tars_archive
import asyncio
import uuid

class FloatingChat:
    def __init__(self):
        self.visible = False
        self.dialog = None
        self.log_container = None
        self.text_input = None
        self.thinking = False
        if 'session_id' not in app.storage.user: app.storage.user['session_id'] = str(uuid.uuid4())
        self.session_id = app.storage.user['session_id']
        self._build_ui()

    def toggle(self):
        self.visible = not self.visible
        if self.visible:
            self.dialog.open()
            if self.log_container: 
                ui.run_javascript(f'const el = document.getElementById("{self.log_container.id}"); if(el) el.scrollTop = el.scrollHeight;')
        else:
            self.dialog.close()

    async def send_message(self):
        if not self.text_input or not self.text_input.value: return
        text = self.text_input.value.strip()
        if not text: return
        self.text_input.value = ''
        if self.thinking: return
        self.thinking = True
        
        with self.log_container:
            ui.chat_message(text=text, name='You', sent=True).classes('text-white bg-indigo-600')
        await mongo_db.add_message_to_session(self.session_id, "user", text)
        
        with self.log_container:
            response_msg = ui.chat_message(name='TARS', sent=False).classes('bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-100')
            with response_msg:
                spinner = ui.spinner('dots', size='sm')
                content_label = ui.markdown()

        try:
            rag_text = ""
            try:
                hits = await run.io_bound(tars_archive.search, text, 1)
                if hits: rag_text = "\n[CONTEXT]: " + hits[0]
            except Exception: pass

            history = await mongo_db.get_recent_history(self.session_id, limit=4)
            persona = "You are TARS, the intelligent AI librarian. Be concise and helpful. " + rag_text
            valid_history = [{"role": m['role'], "content": m['content']} for m in history if 'role' in m]
            messages = [{"role": "system", "content": persona}] + valid_history
            
            response_buffer = ""
            first = True
            async for token in tars_engine.stream_response(messages):
                if first: 
                    spinner.delete()
                    first = False
                response_buffer += token
                content_label.content = response_buffer
            
            await mongo_db.add_message_to_session(self.session_id, "assistant", response_buffer)

        except Exception as e:
            try: spinner.delete() 
            except Exception: pass
            with response_msg: ui.label("Response unavailable.").classes('text-red-500 text-xs')

        self.thinking = False

    def _build_ui(self):
        ui.button(icon='smart_toy', on_click=self.toggle) \
            .props('fab color=indigo') \
            .classes('fixed bottom-6 right-6 z-50 shadow-2xl hover:scale-105 transition-transform')
            
        with ui.dialog() as self.dialog, ui.card().classes(
            'w-[360px] h-[520px] p-0 flex flex-col fixed bottom-20 right-6 shadow-2xl rounded-3xl '
            'border border-slate-200 dark:border-slate-800 overflow-hidden bg-white dark:bg-slate-900'
        ):
            with ui.row().classes('w-full bg-gradient-to-r from-indigo-600 to-indigo-700 p-3.5 items-center justify-between text-white shrink-0'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('smart_toy', size='sm')
                    ui.label('TARS Quick Assistant').classes('font-bold text-sm')
                ui.button(icon='close', on_click=self.toggle).props('flat round dense color=white')
                
            self.log_container = ui.column().classes('w-full flex-grow overflow-y-auto p-4 bg-slate-50 dark:bg-slate-950 gap-2.5')
            self.log_container.props('id=floating-chat-log')
            
            with ui.row().classes('w-full p-2.5 bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800 items-center gap-1.5 shrink-0'):
                self.text_input = ui.input(placeholder='Ask TARS...').props('dense rounded outlined bg-color=slate-50') \
                    .classes('flex-grow text-xs').on('keydown.enter.prevent', self.send_message)
                ui.button(icon='send', on_click=self.send_message).props('flat round dense color=indigo')