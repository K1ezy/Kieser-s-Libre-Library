from nicegui import ui
from typing import List, Dict, Any, Callable, Optional
from datetime import datetime
from core.services.chat_service import group_sessions_chronologically


class ChatHistoryDrawer:
    """
    Slide-over conversation history drawer with live search,
    chronological grouping, and session management.
    """

    def __init__(
        self,
        on_new_chat: Callable[[], Any],
        on_select_session: Callable[[str], Any],
        on_delete_session: Callable[[str], Any],
    ):
        self.on_new_chat = on_new_chat
        self.on_select_session = on_select_session
        self.on_delete_session = on_delete_session

        self.drawer = None
        self.drawer_badge = None
        self.search_input = None
        self.list_container = None
        self.current_search_query = ""
        self.cached_sessions: List[Dict[str, Any]] = []
        self.active_session_id: str = ""

    def build(self) -> ui.right_drawer:
        """Builds drawer structure and returns right_drawer instance."""
        with ui.right_drawer(value=False).props('bordered width=340').classes(
            'bg-white flex flex-col p-0 z-50 shadow-2xl w-full max-w-[88vw] sm:max-w-[360px]'
        ) as self.drawer:
            # Header
            with ui.row().classes('w-full h-16 items-center justify-between px-4 border-b border-slate-200 flex-none bg-slate-50'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('history', size='22px').classes('text-indigo-600')
                    ui.label("Conversation History").classes('text-sm font-black text-slate-900 tracking-tight')
                    self.drawer_badge = ui.label("0").classes(
                        'text-[10px] font-bold text-indigo-700 bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded-full'
                    )
                ui.button(icon='close', on_click=self.drawer.hide).props('flat round dense size=sm color=grey')

            # "+ New Chat" Action
            with ui.row().classes('p-3 pb-2 flex-none w-full border-b border-slate-100'):
                ui.button('+ New Chat', on_click=self.on_new_chat) \
                    .props('unelevated rounded-xl size=sm color=indigo').classes('w-full font-bold shadow-sm hover:shadow')

            # Search History Filter Box
            with ui.row().classes('px-3 py-2 flex-none w-full border-b border-slate-100'):
                self.search_input = ui.input(placeholder='Search by topic, title, or book...').props('outlined rounded-xl dense clearable') \
                    .classes('w-full text-xs bg-slate-50')
                self.search_input.on(
                    'update:model-value',
                    lambda e: self.render_list(e.args if hasattr(e, 'args') and e.args else self.search_input.value or "")
                )

            # Scrollable History List Container
            with ui.column().classes('w-full flex-grow overflow-y-auto px-2.5 pb-6 gap-1 no-scrollbar') as self.list_container:
                pass

        return self.drawer

    def toggle(self) -> None:
        if self.drawer:
            self.drawer.toggle()

    def hide(self) -> None:
        if self.drawer:
            self.drawer.hide()

    def update_sessions(self, sessions: List[Dict[str, Any]], active_session_id: str) -> None:
        self.cached_sessions = sessions or []
        self.active_session_id = active_session_id
        count_str = str(len(self.cached_sessions))
        if self.drawer_badge:
            self.drawer_badge.text = count_str
        self.render_list(self.current_search_query)

    def render_list(self, filter_query: str = "") -> None:
        if not self.list_container:
            return
        self.current_search_query = filter_query.strip().lower()
        sessions = self.cached_sessions

        if self.current_search_query:
            sessions = [
                s for s in sessions
                if self.current_search_query in s.get('title', '').lower()
                or self.current_search_query in str(s.get('book_title', '')).lower()
            ]

        self.list_container.clear()
        grouped = group_sessions_chronologically(sessions)

        with self.list_container:
            if not sessions:
                self._render_empty_history()
                return

            for group_name, group_items in grouped.items():
                self._render_group_header(group_name, len(group_items))
                for s in group_items:
                    self._render_item(s)

    def _render_empty_history(self) -> None:
        with ui.column().classes('w-full items-center justify-center py-12 text-center px-4'):
            ui.icon('chat_bubble_outline', size='3em').classes('text-slate-300 mb-2')
            ui.label("No conversations found").classes('text-xs font-bold text-slate-600')
            ui.label("Conversations you create will appear here.").classes('text-[11px] text-slate-400 max-w-[200px]')

    def _render_group_header(self, group_name: str, count: int) -> None:
        with ui.row().classes('w-full items-center justify-between px-2 pt-3 pb-1'):
            ui.label(group_name).classes('text-[10px] font-black text-slate-400 uppercase tracking-widest')
            ui.label(f"{count}").classes('text-[9px] font-bold text-slate-500 bg-slate-100 px-1.5 py-0.2 rounded-full')

    def _render_item(self, session_data: dict) -> None:
        sid = session_data.get('id')
        title = session_data.get('title', 'Conversation')
        ts = session_data.get('timestamp')
        book_t = session_data.get('book_title')
        msg_cnt = session_data.get('message_count')
        is_active = (sid == self.active_session_id)

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
                with ui.row().classes('items-center gap-2.5 flex-grow min-w-0 cursor-pointer').on(
                    'click', lambda s=sid: self.on_select_session(s)
                ):
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

                with ui.row().classes('items-center gap-0.5 shrink-0 opacity-80 group-hover:opacity-100 transition-opacity'):
                    with ui.button(icon='delete_outline', on_click=lambda s=sid: self.on_delete_session(s)) \
                            .props('flat round dense size=xs color=grey-7').classes('hover:text-rose-600'):
                        ui.tooltip('Delete conversation')
