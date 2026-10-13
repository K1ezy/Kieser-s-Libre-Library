from nicegui import ui
from typing import Callable, Any, Optional


class ChatInputBar:
    """
    Bottom floating prompt input bar with responsive quick-action menus,
    streaming controls, and model generation triggers.
    """

    def __init__(
        self,
        on_send: Callable[[], Any],
        on_stop: Callable[[], Any],
        on_continue: Callable[[], Any],
        on_open_history: Callable[[], Any],
        on_open_upload: Callable[[], Any],
        on_open_book_picker: Callable[[], Any],
    ):
        self.on_send = on_send
        self.on_stop = on_stop
        self.on_continue = on_continue
        self.on_open_history = on_open_history
        self.on_open_upload = on_open_upload
        self.on_open_book_picker = on_open_book_picker

        self.text_input = None
        self.send_btn = None
        self.stop_btn = None
        self.continue_btn = None

    def build(self) -> ui.column:
        with ui.column().classes('w-full p-2 sm:p-4 z-30 shrink-0 max-w-4xl mx-auto') as container:
            with ui.card().classes(
                'w-full bg-white/95 backdrop-blur-md border border-slate-200 '
                'p-1.5 sm:p-3 rounded-2xl sm:rounded-3xl shadow-xl gap-1'
            ):
                with ui.row().classes('w-full items-end gap-1 sm:gap-2'):
                    # Mobile compact action menu
                    with ui.button(icon='add_circle_outline').props('flat round dense color=indigo size=md').classes('flex sm:hidden shrink-0'):
                        ui.tooltip('Quick Actions')
                        with ui.menu().classes('rounded-2xl border border-slate-200 bg-white shadow-xl p-1 min-w-[180px]'):
                            ui.menu_item('📚 Scope to Document', on_click=self.on_open_book_picker).classes('text-xs font-medium')
                            ui.menu_item('☁️ Ingest Document', on_click=self.on_open_upload).classes('text-xs font-medium')
                            ui.menu_item('⏩ Continue Response', on_click=self.on_continue).classes('text-xs font-medium')
                            ui.menu_item('🕒 Chat History', on_click=self.on_open_history).classes('text-xs font-medium')

                    # Tablet / Desktop action buttons
                    with ui.row().classes('hidden sm:flex items-center gap-1 shrink-0'):
                        ui.button(icon='history', on_click=self.on_open_history) \
                            .props('flat round dense color=indigo size=md').tooltip('View Chat History')

                        ui.button(icon='cloud_upload', on_click=self.on_open_upload) \
                            .props('flat round dense color=indigo size=md').tooltip('Ingest Document to Knowledge Base')

                        ui.button(icon='menu_book', on_click=self.on_open_book_picker) \
                            .props('flat round dense color=indigo size=md').tooltip('Scope Chat to a Specific Book')

                        self.continue_btn = ui.button(icon='fast_forward', on_click=self.on_continue) \
                            .props('round dense color=amber size=md').tooltip('Continue Generating')
                        self.continue_btn.disable()

                    self.text_input = ui.textarea(
                        placeholder='Ask TARS anything... (Enter to send)'
                    ).props('rows=1 autogrow outlined rounded bg-color=slate-50') \
                     .classes('flex-grow text-sm max-h-36') \
                     .on('keydown.enter.prevent', self.on_send)

                    with ui.row().classes('shrink-0 items-center'):
                        self.send_btn = ui.button(icon='send', on_click=self.on_send) \
                            .props('round unelevated color=indigo size=md').classes('shadow-md hover:scale-105 transition-transform')
                        self.stop_btn = ui.button(icon='stop', on_click=self.on_stop) \
                            .props('round color=red size=md shadow-md')
                        self.stop_btn.set_visibility(False)

                with ui.row().classes('w-full justify-center items-center pt-0.5 px-2'):
                    ui.label("🔒 100% Local & Private • Scoped ChromaDB Vector RAG • Multi-Engine AI").classes(
                        'text-[9px] sm:text-[10px] text-slate-400 font-medium text-center truncate max-w-full'
                    )

        return container

    def set_generating_state(self, is_generating: bool):
        if self.send_btn:
            self.send_btn.set_visibility(not is_generating)
        if self.stop_btn:
            self.stop_btn.set_visibility(is_generating)
        if self.continue_btn and is_generating:
            self.continue_btn.disable()

    @property
    def value(self) -> str:
        return self.text_input.value if self.text_input else ""

    @value.setter
    def value(self, val: str):
        if self.text_input:
            self.text_input.value = val
