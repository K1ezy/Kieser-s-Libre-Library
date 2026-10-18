from nicegui import ui, app
from core.database.mongo_manager import mongo_db
from components.sidebar import sidebar
from components.header import header, refresh_header_avatar
import asyncio
from typing import Optional, Dict, Any

from components.profile import (
    ROLE_CONFIGS,
    get_user_initials,
    render_pvc_id_card,
    open_avatar_modal,
    open_cover_modal,
    render_profile_stats,
    PROGRAM_OPTIONS,
    YEAR_LEVEL_OPTIONS,
)

__all__ = [
    'ROLE_CONFIGS',
    'get_user_initials',
    'PROGRAM_OPTIONS',
    'YEAR_LEVEL_OPTIONS',
    'UserProfile',
    'profile_page',
]


class UserProfile:
    def __init__(self):
        self.profile_data: Dict[str, Any] = {}
        self.stats: Dict[str, Any] = {}
        self.is_editing: bool = False

        # Input handles for editing
        self.name_input = None
        self.headline_input = None
        self.bio_input = None
        self.id_input = None
        self.program_input = None
        self.year_input = None
        self.dept_input = None
        self.branch_input = None

    async def load_data(self):
        """Loads profile and stats strictly isolated to the current user."""
        user_id = app.storage.user.get('user_id')
        self.profile_data, self.stats = await asyncio.gather(
            mongo_db.get_user_profile(user_id=user_id),
            mongo_db.get_library_stats(user_id=user_id)
        )
        if self.profile_data:
            if self.profile_data.get('avatar_url') is not None:
                app.storage.user['avatar_url'] = self.profile_data.get('avatar_url') or ''
            if self.profile_data.get('cover_url') is not None:
                app.storage.user['cover_url'] = self.profile_data.get('cover_url') or ''
            if self.profile_data.get('name'):
                app.storage.user['name'] = self.profile_data.get('name')
        self.render_content.refresh()

    async def save_changes(self):
        """Persists profile and institutional ID metadata changes."""
        user_id = app.storage.user.get('user_id') or self.profile_data.get('id')
        if not user_id:
            ui.notify('Session expired. Please log in again.', type='negative')
            return ui.navigate.to('/login')

        name_val = self.name_input.value if self.name_input else self.profile_data.get('name')
        bio_val = self.bio_input.value if self.bio_input else self.profile_data.get('bio')
        head_val = self.headline_input.value if self.headline_input else self.profile_data.get('headline')
        id_val = self.id_input.value if self.id_input else (
            self.profile_data.get('institutional_id') or self.profile_data.get('student_id')
        )
        prog_val = self.program_input.value if self.program_input else self.profile_data.get('program')
        year_val = self.year_input.value if self.year_input else self.profile_data.get('year_level')
        dept_val = self.dept_input.value if self.dept_input else self.profile_data.get('department')
        branch_val = self.branch_input.value if self.branch_input else self.profile_data.get('branch')

        await mongo_db.update_user_profile(
            user_id=user_id,
            name=name_val,
            bio=bio_val,
            headline=head_val,
            institutional_id=id_val,
            student_id=id_val,
            program=prog_val,
            year_level=year_val,
            department=dept_val,
            branch=branch_val
        )
        self.is_editing = False
        ui.notify('Profile & Institutional Credentials updated successfully!', type='positive')
        await self.load_data()

    def toggle_edit(self):
        self.is_editing = not self.is_editing
        self.render_content.refresh()

    def open_avatar_modal(self):
        user_id = app.storage.user.get('user_id') or self.profile_data.get('id')
        initials = get_user_initials(self.profile_data.get('name'), self.profile_data.get('username'))

        async def on_uploaded(url: str):
            self.profile_data['avatar_url'] = url
            app.storage.user['avatar_url'] = url or ''
            self.render_content.refresh()
            refresh_header_avatar()

        open_avatar_modal(
            user_id=user_id,
            current_avatar=self.profile_data.get('avatar_url'),
            initials=initials,
            on_uploaded=on_uploaded,
        )

    def open_cover_modal(self):
        user_id = app.storage.user.get('user_id') or self.profile_data.get('id')

        async def on_uploaded(url: str):
            self.profile_data['cover_url'] = url
            app.storage.user['cover_url'] = url or ''
            self.render_content.refresh()

        open_cover_modal(
            user_id=user_id,
            current_cover=self.profile_data.get('cover_url'),
            on_uploaded=on_uploaded,
        )

    @ui.refreshable
    def render_content(self):
        raw_role = str(self.profile_data.get('role', 'student')).upper()
        norm_role = 'STUDENT' if raw_role in ('USER', 'STUDENT') else raw_role
        role_cfg = ROLE_CONFIGS.get(norm_role, ROLE_CONFIGS['STUDENT'])

        user_name = self.profile_data.get('name') or self.profile_data.get('username') or 'Library Member'
        username = self.profile_data.get('username') or 'user'
        inst_id = self.profile_data.get('institutional_id') or self.profile_data.get('student_id') or '2024-001'
        program = self.profile_data.get('program') or 'BSCS'
        year_level = self.profile_data.get('year_level') or '1st Year'
        dept = self.profile_data.get('department') or 'College of Computing'
        branch = self.profile_data.get('branch') or 'Main Library Archive'
        admin_code = self.profile_data.get('admin_code') or inst_id
        avatar_url = self.profile_data.get('avatar_url')
        cover_url = self.profile_data.get('cover_url')
        initials = get_user_initials(user_name, username)

        # 1. Single Unified Container Wrapping Cover Banner & Profile Details (Zero Overhang)
        with ui.element('div').classes('w-full max-w-4xl mx-auto bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden'):
            # Cover Banner (100% flush with parent container)
            with ui.element('div').classes('relative w-full h-44 sm:h-56 md:h-60 bg-gradient-to-r from-indigo-950 via-purple-900 to-slate-950 overflow-hidden'):
                if cover_url:
                    ui.image(cover_url).classes('w-full h-full object-cover')
                else:
                    ui.icon('auto_stories').classes('text-white/10 text-8xl absolute right-6 bottom-2 select-none pointer-events-none')

                # Edit Cover Button
                ui.button('EDIT COVER', icon='photo_camera', on_click=self.open_cover_modal).props(
                    'unelevated no-caps'
                ).classes(
                    'absolute top-4 right-4 z-10 px-3.5 py-1.5 rounded-lg text-xs font-semibold '
                    'bg-slate-900/60 hover:bg-slate-900/80 text-white backdrop-blur-md '
                    'border border-white/20 transition-all duration-200 shadow-sm'
                )

            # Profile Body Content
            with ui.element('div').classes('px-5 sm:px-8 pb-8'):
                with ui.element('div').classes('flex flex-col sm:flex-row sm:items-end justify-between gap-4 pb-6 border-b border-slate-100'):
                    with ui.element('div').classes('flex flex-col sm:flex-row sm:items-end gap-5'):
                        # AVATAR: Outer is relative (unclipped), Inner is overflow-hidden
                        with ui.element('div').classes('relative w-28 h-28 sm:w-32 sm:h-32 -mt-14 sm:-mt-16 shrink-0'):
                            with ui.element('div').classes(
                                'w-full h-full rounded-full overflow-hidden ring-4 ring-white shadow-md '
                                'bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center'
                            ):
                                if avatar_url:
                                    ui.image(avatar_url).classes('w-full h-full object-cover')
                                else:
                                    ui.label(initials).classes('text-2xl sm:text-3xl font-black text-white tracking-wider select-none')

                            # Floating Camera Badge outside overflow-hidden circle (NEVER CLIPPED)
                            ui.button(
                                icon='photo_camera',
                                on_click=self.open_avatar_modal,
                            ).props('round unelevated dense').classes(
                                'absolute bottom-0.5 right-0.5 z-10 w-9 h-9 rounded-full '
                                'bg-indigo-600 hover:bg-indigo-700 text-white ring-2 ring-white '
                                'shadow-md transition-transform duration-200 hover:scale-105'
                            ).tooltip('Change Profile Photo')

                        # Profile Core Metadata
                        with ui.column().classes('mb-1 sm:mb-2 flex-grow min-w-0 w-full sm:w-auto items-center sm:items-start'):
                            if not self.is_editing:
                                with ui.row().classes('items-center gap-2 flex-wrap justify-center sm:justify-start'):
                                    ui.label(user_name).classes('text-2xl sm:text-3xl font-black text-slate-900 leading-tight tracking-tight')
                                    with ui.element('div').classes(f'text-[10px] font-black px-2.5 py-0.5 rounded-full uppercase tracking-wider border flex items-center gap-1 {role_cfg["badge_bg"]}'):
                                        ui.icon(role_cfg['icon'], size='14px')
                                        ui.label(norm_role)

                                with ui.row().classes('items-center gap-2 mt-1.5 flex-wrap justify-center sm:justify-start'):
                                    with ui.element('span').classes('text-xs font-mono font-bold text-slate-800 bg-slate-100 border border-slate-200 px-2.5 py-0.5 rounded-lg shadow-2xs'):
                                        ui.label(f"{role_cfg['id_name']}: {inst_id}")
                                    if norm_role == 'STUDENT':
                                        ui.label(f"{program} • {year_level}").classes('text-xs font-black text-emerald-700 bg-emerald-50 border border-emerald-100 px-2.5 py-0.5 rounded-lg')
                                    elif norm_role == 'FACULTY':
                                        ui.label(dept).classes('text-xs font-black text-blue-700 bg-blue-50 border border-blue-100 px-2.5 py-0.5 rounded-lg')
                                    elif norm_role == 'LIBRARIAN':
                                        ui.label(branch).classes('text-xs font-black text-purple-700 bg-purple-50 border border-purple-100 px-2.5 py-0.5 rounded-lg')
                                    elif norm_role == 'ADMIN':
                                        ui.label("System Governance").classes('text-xs font-black text-amber-700 bg-amber-50 border border-amber-100 px-2.5 py-0.5 rounded-lg')

                                    ui.label(self.profile_data.get('headline', 'Academic Scholar & Researcher')).classes('text-xs text-slate-500 font-medium')
                            else:
                                self.name_input = ui.input(value=user_name, label='Full Legal Name').props('outlined dense rounded bg-color=white').classes('w-full text-sm')
                                with ui.row().classes('w-full gap-2.5 flex-wrap sm:flex-nowrap'):
                                    self.id_input = ui.input(value=inst_id, label=role_cfg['id_name']).props('outlined dense rounded bg-color=white').classes('flex-1 text-sm')
                                    if norm_role == 'STUDENT':
                                        self.program_input = ui.select(PROGRAM_OPTIONS, value=program, label='Program').props('outlined dense rounded bg-color=white options-dense').classes('w-32 text-sm')
                                        self.year_input = ui.select(YEAR_LEVEL_OPTIONS, value=year_level, label='Year Level').props('outlined dense rounded bg-color=white options-dense').classes('w-32 text-sm')
                                    elif norm_role == 'FACULTY':
                                        self.dept_input = ui.input(value=dept, label='Department / College').props('outlined dense rounded bg-color=white').classes('flex-1 text-sm')
                                    elif norm_role == 'LIBRARIAN':
                                        self.branch_input = ui.input(value=branch, label='Library Branch / Section').props('outlined dense rounded bg-color=white').classes('flex-1 text-sm')
                                    elif norm_role == 'ADMIN':
                                        self.branch_input = ui.input(value=admin_code, label='Admin Verification Code').props('outlined dense rounded bg-color=white').classes('flex-1 text-sm')

                                self.headline_input = ui.input(
                                    value=self.profile_data.get('headline', 'Academic Scholar & Researcher'),
                                    label='Academic Headline / Discipline'
                                ).props('outlined dense rounded bg-color=white').classes('w-full text-sm')

                    # Action Buttons
                    if not self.is_editing:
                        ui.button('EDIT PROFILE', icon='edit', on_click=self.toggle_edit).props(
                            'outline no-caps color=grey-8 size=sm font-bold'
                        ).classes('self-center sm:self-end border border-slate-300 text-slate-700 hover:bg-slate-50 shadow-2xs rounded-lg px-4 py-1.5 transition-all')
                    else:
                        with ui.row().classes('gap-2 self-center sm:self-end mt-2'):
                            ui.button('Cancel', on_click=self.toggle_edit).props('outline rounded-lg color=grey-7 size=sm font-bold no-caps')
                            ui.button('Save Changes', icon='save', on_click=self.save_changes).props('unelevated rounded-lg color=indigo size=sm font-bold no-caps shadow-xs')

                # 3. Institutional Digital PVC ID Badge
                with ui.element('div').classes('mt-6'):
                    render_pvc_id_card(
                        user_name=user_name,
                        norm_role=norm_role,
                        role_cfg=role_cfg,
                        inst_id=inst_id,
                        program=program,
                        year_level=year_level,
                        dept=dept,
                        branch=branch,
                        admin_code=admin_code,
                        avatar_url=avatar_url,
                        initials=initials,
                    )

                # 4. Biography Section
                ui.separator().classes('my-6 opacity-60')
                ui.label('BIOGRAPHY & RESEARCH INTERESTS').classes('text-xs font-bold uppercase tracking-wider text-slate-400 mb-2')
                if not self.is_editing:
                    ui.label(self.profile_data.get('bio', 'Dedicated learner and researcher utilizing Libre-Library.')).classes('text-slate-700 leading-relaxed text-sm sm:text-base break-words')
                else:
                    self.bio_input = ui.textarea(value=self.profile_data.get('bio', ''), label='Personal Bio / Research Goals').props('outlined rounded bg-color=white').classes('w-full text-sm')

                # 5. Activity & Subsystem Stats
                ui.separator().classes('my-6 opacity-60')
                render_profile_stats(self.stats)

    def build_ui(self):
        drawer = sidebar()
        header(drawer_reference=drawer)
        with ui.column().classes(
            'w-full min-h-fit pt-[calc(4.5rem+env(safe-area-inset-top,0px))] md:pt-24 px-3 sm:px-6 md:px-8 max-w-5xl mx-auto pb-16'
        ):
            self.render_content()


async def profile_page():
    app.storage.client['page_path'] = '/profile'
    page = UserProfile()
    page.build_ui()
    await page.load_data()