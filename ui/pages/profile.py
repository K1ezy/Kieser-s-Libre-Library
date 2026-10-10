from nicegui import ui, app
from core.database.mongo_manager import mongo_db
from components.sidebar import sidebar
from components.header import header
from components.bottom_nav import bottom_nav
from ui.pages.attendance import generate_qr_base64
import asyncio

PROGRAM_OPTIONS = ["BSCS", "BSIT", "BSED", "BEED", "BSBA", "BSHM", "Crim", "Nursing", "GENERAL"]

ROLE_COLORS = {
    "ADMIN": ("bg-purple-100 text-purple-800 border-purple-200", "security"),
    "LIBRARIAN": ("bg-blue-100 text-blue-800 border-blue-200", "local_library"),
    "FACULTY": ("bg-emerald-100 text-emerald-800 border-emerald-200", "school"),
    "STUDENT": ("bg-indigo-100 text-indigo-800 border-indigo-200", "badge"),
    "USER": ("bg-indigo-100 text-indigo-800 border-indigo-200", "badge"),
}

class UserProfile:
    def __init__(self):
        self.profile_data = {}
        self.stats = {}
        self.is_editing = False
        self.name_input = None
        self.headline_input = None
        self.bio_input = None
        self.student_id_input = None
        self.program_select = None
        self.container = None

    async def load_data(self):
        """Loads profile and stats strictly isolated to current user."""
        user_id = app.storage.user.get('user_id')
        self.profile_data = await mongo_db.get_user_profile(user_id=user_id)
        self.stats = await mongo_db.get_library_stats(user_id=user_id)
        self.render_content.refresh()

    async def save_changes(self):
        user_id = app.storage.user.get('user_id')
        if not user_id:
            ui.notify('Session expired. Please log in again.', type='negative')
            return ui.navigate.to('/login')

        if self.name_input and self.headline_input and self.bio_input:
            sid_val = self.student_id_input.value if self.student_id_input else self.profile_data.get('student_id')
            prog_val = self.program_select.value if self.program_select else self.profile_data.get('program')
            await mongo_db.update_user_profile(
                user_id=user_id,
                name=self.name_input.value,
                bio=self.bio_input.value,
                headline=self.headline_input.value,
                student_id=sid_val,
                program=prog_val
            )
            self.is_editing = False
            ui.notify('Profile & Student ID updated successfully!', type='positive')
            await self.load_data()

    def toggle_edit(self):
        self.is_editing = not self.is_editing
        self.render_content.refresh()

    @ui.refreshable
    def render_content(self):
        # Header Banner
        with ui.column().classes('w-full h-36 sm:h-48 bg-gradient-to-r from-indigo-600 via-purple-600 to-indigo-800 relative rounded-2xl sm:rounded-3xl shadow-lg'):
            pass 

        # Profile Card
        with ui.column().classes('w-full max-w-4xl mx-auto -mt-16 sm:-mt-24 px-2 sm:px-4'):
            with ui.card().classes('w-full p-4 sm:p-6 md:p-8 rounded-2xl sm:rounded-3xl shadow-xl bg-white border border-slate-200'):
                with ui.row().classes('w-full items-center sm:items-end gap-4 sm:gap-6 flex-col sm:flex-row text-center sm:text-left'):
                    # Avatar
                    with ui.element('div').classes('w-20 h-20 sm:w-28 sm:h-28 rounded-full border-4 border-white bg-indigo-50 shadow-md flex items-center justify-center overflow-hidden shrink-0 border-indigo-100'):
                        ui.icon('person', size='2.5em').classes('text-indigo-600')
                    
                    # Info
                    with ui.column().classes('mb-1 sm:mb-2 flex-grow min-w-0 w-full sm:w-auto items-center sm:items-start'):
                        raw_role = self.profile_data.get('role', 'student').upper()
                        account_role = 'STUDENT' if raw_role == 'USER' else raw_role
                        badge_style, badge_icon = ROLE_COLORS.get(account_role, ("bg-indigo-100 text-indigo-800 border-indigo-200", "badge"))
                        user_sid = self.profile_data.get('student_id', '2024-001')
                        user_prog = self.profile_data.get('program', 'BSCS')

                        if not self.is_editing:
                            with ui.row().classes('items-center gap-2 flex-wrap justify-center sm:justify-start'):
                                ui.label(self.profile_data.get('name', 'Library User')).classes('text-2xl sm:text-3xl font-black text-slate-900 leading-tight')
                                with ui.element('div').classes(f'text-[10px] font-black px-2.5 py-0.5 rounded-full uppercase tracking-wider border flex items-center gap-1 {badge_style}'):
                                    ui.icon(badge_icon, size='14px')
                                    ui.label(account_role)

                            with ui.row().classes('items-center gap-2 mt-1 flex-wrap justify-center sm:justify-start'):
                                ui.label(f"ID: {user_sid}").classes('text-xs font-mono font-bold text-slate-700 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded')
                                ui.label(user_prog).classes('text-xs font-black text-indigo-700 bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded')
                                ui.label(self.profile_data.get('headline', 'Student / Researcher')).classes('text-xs text-slate-500 font-medium')
                        else:
                            self.name_input = ui.input(value=self.profile_data.get('name', 'Library User'), label='Full Name').props('outlined dense rounded bg-color=white').classes('w-full text-sm')
                            with ui.row().classes('w-full gap-2'):
                                self.student_id_input = ui.input(value=user_sid, label='Student / Faculty ID Number').props('outlined dense rounded bg-color=white').classes('flex-1 text-sm')
                                self.program_select = ui.select(PROGRAM_OPTIONS, value=user_prog, label='Program').props('outlined dense rounded bg-color=white options-dense').classes('w-36 text-sm')
                            self.headline_input = ui.input(value=self.profile_data.get('headline', 'Student / Researcher'), label='Title / Field of Study').props('outlined dense rounded bg-color=white').classes('w-full text-sm')

                    # Edit Action
                    if not self.is_editing:
                        ui.button('Edit Profile', icon='edit', on_click=self.toggle_edit).props('flat rounded color=indigo font-bold size=md').classes('self-center sm:self-end')
                    else:
                        with ui.row().classes('gap-2 self-center sm:self-end'):
                            ui.button('Cancel', on_click=self.toggle_edit).props('flat rounded color=red size=md')
                            ui.button('Save', icon='save', on_click=self.save_changes).props('unelevated rounded color=indigo size=md font-bold')

                ui.separator().classes('my-4 sm:my-6 opacity-50')

                # Digital Library Student Pass (Mini Card)
                user_sid_clean = self.profile_data.get('student_id', '2024-001')
                qr_code_b64 = generate_qr_base64(user_sid_clean)

                with ui.row().classes('w-full p-4 sm:p-5 rounded-2xl bg-gradient-to-r from-slate-50 to-indigo-50/40 border border-indigo-100 items-center justify-between gap-4 flex-wrap mb-4'):
                    with ui.row().classes('items-center gap-4'):
                        with ui.element('div').classes('p-2 bg-white rounded-xl border border-slate-200 shadow-sm shrink-0'):
                            ui.image(qr_code_b64).classes('w-16 h-16 rounded-lg')
                        with ui.column().classes('gap-0'):
                            ui.label('OFFICIAL LIBRARY QR PASS').classes('text-[10px] font-black text-indigo-600 uppercase tracking-widest')
                            ui.label(f"{self.profile_data.get('name', 'User')} • {user_sid_clean}").classes('text-sm font-bold text-slate-900')
                            ui.label('Ready for contactless library door check-in').classes('text-xs text-slate-500')
                    
                    ui.button('Open Attendance Terminal', icon='qr_code_scanner', on_click=lambda: ui.navigate.to('/attendance')) \
                        .props('unelevated rounded-xl color=indigo size=sm font-bold')

                # Bio Section
                ui.label('ABOUT ME').classes('text-[11px] sm:text-xs font-bold text-slate-400 uppercase tracking-widest mb-1.5')
                if not self.is_editing:
                    ui.label(self.profile_data.get('bio', 'Exploring knowledge with Libre-Library.')).classes('text-slate-700 leading-relaxed text-sm sm:text-base break-words')
                else:
                    self.bio_input = ui.textarea(value=self.profile_data.get('bio', ''), label='Bio').props('outlined rounded bg-color=white').classes('w-full text-sm')

                ui.separator().classes('my-4 sm:my-6 opacity-50')

                # Stats Grid
                ui.label('ACTIVITY STATS').classes('text-[11px] sm:text-xs font-bold text-slate-400 uppercase tracking-widest mb-3 sm:mb-4')
                with ui.grid().classes('grid-cols-2 md:grid-cols-4 gap-2.5 sm:gap-4 w-full'):
                    def stat_badge(label, value, icon, color):
                        with ui.column().classes(f'p-3 sm:p-4 rounded-xl sm:rounded-2xl bg-{color}-50 border border-{color}-200 items-center justify-center hover:scale-105 transition-transform text-center'):
                            ui.icon(icon, size='sm').classes(f'text-{color}-600 mb-1')
                            ui.label(str(value)).classes(f'text-xl sm:text-2xl font-bold text-{color}-700 leading-none')
                            ui.label(label).classes(f'text-[9px] sm:text-[10px] font-bold text-{color}-600 uppercase tracking-wider mt-1')

                    stat_badge('Tasks Done', self.stats.get('tasks_done', 0), 'check_circle', 'green')
                    stat_badge('Books Saved', self.stats.get('books', 0), 'library_books', 'indigo')
                    stat_badge('System Status', 'Online', 'wifi', 'emerald')
                    stat_badge('AI Librarian', 'Active', 'smart_toy', 'purple')

    def build_ui(self):
        drawer = sidebar()
        header(drawer_reference=drawer)
        bottom_nav()
        
        with ui.column().classes('w-full min-h-[100dvh] pt-[calc(4.5rem+env(safe-area-inset-top,0px))] px-3 sm:px-4 md:pt-24 md:px-8 max-w-7xl mx-auto pb-[calc(5rem+env(safe-area-inset-bottom,0px))] md:pb-16'):
            self.render_content()

async def profile_page():
    app.storage.client['page_path'] = '/profile'
    page = UserProfile()
    page.build_ui()
    await page.load_data()