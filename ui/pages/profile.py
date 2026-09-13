from nicegui import ui, app
from core.database.mongo_manager import mongo_db
from components.sidebar import sidebar
from components.header import header
import asyncio

class UserProfile:
    def __init__(self):
        self.profile_data = {}
        self.stats = {}
        self.is_editing = False
        self.name_input = None
        self.role_input = None
        self.bio_input = None
        self.container = None

    async def load_data(self):
        """Loads profile and stats without premature UI refresh."""
        self.profile_data = await mongo_db.get_user_profile()
        self.stats = await mongo_db.get_library_stats()
        self.render_content.refresh()

    async def save_changes(self):
        if self.name_input and self.role_input and self.bio_input:
            await mongo_db.update_user_profile(
                name=self.name_input.value,
                role=self.role_input.value,
                bio=self.bio_input.value
            )
            self.is_editing = False
            ui.notify('Profile Updated', type='positive')
            await self.load_data()

    def toggle_edit(self):
        self.is_editing = not self.is_editing
        self.render_content.refresh()

    @ui.refreshable
    def render_content(self):
        # Header Banner
        with ui.column().classes('w-full h-48 bg-gradient-to-r from-indigo-600 via-purple-600 to-indigo-800 relative rounded-3xl shadow-lg'):
            pass 

        # Profile Card
        with ui.column().classes('w-full max-w-4xl mx-auto -mt-24 px-4 pb-24'):
            with ui.card().classes('w-full p-8 rounded-3xl shadow-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800'):
                with ui.row().classes('w-full items-end gap-6 wrap'):
                    # Avatar
                    with ui.element('div').classes('w-28 h-28 rounded-full border-4 border-white dark:border-slate-800 bg-indigo-50 dark:bg-slate-800 shadow-md flex items-center justify-center overflow-hidden shrink-0'):
                        ui.icon('person', size='3.5em').classes('text-indigo-500 dark:text-indigo-400')
                    
                    # Info
                    with ui.column().classes('mb-2 flex-grow min-w-[200px]'):
                        if not self.is_editing:
                            ui.label(self.profile_data.get('name', 'Library User')).classes('text-3xl font-black text-slate-900 dark:text-slate-100 leading-tight')
                            ui.label(self.profile_data.get('role', 'Student / Researcher')).classes('text-sm font-semibold text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950/40 px-3 py-1 rounded-full w-max mt-1')
                        else:
                            self.name_input = ui.input(value=self.profile_data.get('name', 'Library User'), label='Full Name').props('outlined dense rounded').classes('w-full')
                            self.role_input = ui.input(value=self.profile_data.get('role', 'Student'), label='Role / Title').props('outlined dense rounded').classes('w-full')

                    # Edit Action
                    if not self.is_editing:
                        ui.button('Edit Profile', icon='edit', on_click=self.toggle_edit).props('flat rounded color=indigo font-bold')
                    else:
                        with ui.row().classes('gap-2'):
                            ui.button('Cancel', on_click=self.toggle_edit).props('flat rounded color=red')
                            ui.button('Save', icon='save', on_click=self.save_changes).props('unelevated rounded color=indigo')

                ui.separator().classes('my-6 opacity-50')

                # Bio Section
                ui.label('ABOUT ME').classes('text-xs font-bold text-slate-400 uppercase tracking-widest mb-2')
                if not self.is_editing:
                    ui.label(self.profile_data.get('bio', 'Exploring knowledge with Libre-Library.')).classes('text-slate-600 dark:text-slate-300 leading-relaxed text-base')
                else:
                    self.bio_input = ui.textarea(value=self.profile_data.get('bio', ''), label='Bio').props('outlined rounded').classes('w-full')

                ui.separator().classes('my-6 opacity-50')

                # Stats Grid
                ui.label('ACTIVITY STATS').classes('text-xs font-bold text-slate-400 uppercase tracking-widest mb-4')
                with ui.grid().classes('grid-cols-2 md:grid-cols-4 gap-4 w-full'):
                    def stat_badge(label, value, icon, color):
                        with ui.column().classes(f'p-4 rounded-2xl bg-{color}-50 dark:bg-{color}-950/30 border border-{color}-100 dark:border-{color}-900/40 items-center justify-center hover:scale-105 transition-transform'):
                            ui.icon(icon, size='md').classes(f'text-{color}-500 mb-1')
                            ui.label(str(value)).classes(f'text-2xl font-bold text-{color}-700 dark:text-{color}-300')
                            ui.label(label).classes(f'text-[10px] font-bold text-{color}-600 dark:text-{color}-400 uppercase tracking-wider')

                    stat_badge('Tasks Done', self.stats.get('tasks_done', 0), 'check_circle', 'green')
                    stat_badge('Books Saved', self.stats.get('books', 0), 'library_books', 'indigo')
                    stat_badge('System Status', 'Online', 'wifi', 'emerald')
                    stat_badge('AI Librarian', 'Active', 'smart_toy', 'purple')

    def build_ui(self):
        drawer = sidebar()
        header(drawer_reference=drawer)
        
        with ui.column().classes('w-full min-h-screen pt-20 px-4 md:pt-24 md:px-8 max-w-7xl mx-auto bg-slate-50/50 dark:bg-transparent'):
            self.render_content()

async def profile_page():
    app.storage.client['page_path'] = '/profile'
    page = UserProfile()
    page.build_ui()
    await page.load_data()