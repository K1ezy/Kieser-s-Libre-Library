from nicegui import ui, app
from core.database.mongo_manager import mongo_db
from core.auth.jwt_handler import (
    create_access_token,
    is_user_authenticated,
    set_user_session,
    clear_user_session
)
import bcrypt
import re

# Premium Button & Input Styles
BTN_STYLE = 'w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-base shadow-lg shadow-indigo-500/20 active:scale-[0.99] transition-all'
INPUT_CLASSES = 'w-full mb-3 sm:mb-4 text-base'

def create_password_toggle(input_field):
    """Adds a modern eye icon toggle to show/hide password."""
    with input_field.add_slot('append'):
        toggle_icon = ui.icon('visibility_off').classes('cursor-pointer text-slate-400 hover:text-indigo-600 transition-colors')
        def toggle():
            current_type = input_field._props.get('type', 'password')
            if current_type == 'password':
                input_field._props['type'] = 'text'
                toggle_icon._props['name'] = 'visibility'
            else:
                input_field._props['type'] = 'password'
                toggle_icon._props['name'] = 'visibility_off'
            input_field.update()
            toggle_icon.update()
        toggle_icon.on('click', toggle)

async def login_page():
    # If already logged in, redirect directly to dashboard
    if is_user_authenticated():
        ui.navigate.to('/')
        return

    dark = ui.dark_mode()
    ui.button(icon='dark_mode', on_click=dark.toggle) \
        .classes('absolute top-4 right-4 z-50 text-gray-500 dark:text-gray-300 hover:text-gray-700 dark:hover:white transition-colors') \
        .props('flat round size=md')

    with ui.row().classes('w-full h-screen m-0 p-0 overflow-hidden'):
        # Brand Side
        with ui.column().classes('hidden md:flex w-1/2 h-full bg-gradient-to-br from-indigo-900 via-indigo-800 to-purple-900 items-center justify-center text-white p-12 relative overflow-hidden'):
            # Ambient background glow
            ui.element('div').classes('absolute w-96 h-96 bg-indigo-500/20 rounded-full blur-3xl -top-20 -left-20')
            ui.element('div').classes('absolute w-80 h-80 bg-purple-500/20 rounded-full blur-3xl -bottom-20 -right-20')
            
            ui.icon('auto_stories', size='5rem').classes('mb-6 opacity-95 drop-shadow-md')
            ui.label('Libre Library').classes('text-5xl font-black tracking-tight mb-3 text-center')
            ui.label('Your Intelligent Digital Archive').classes('text-lg font-normal opacity-85 text-center max-w-sm')
            
            with ui.row().classes('mt-8 gap-4 opacity-75 text-sm'):
                with ui.row().classes('items-center gap-1.5'):
                    ui.icon('bolt', size='sm')
                    ui.label('Fast Search')
                with ui.row().classes('items-center gap-1.5'):
                    ui.icon('psychology', size='sm')
                    ui.label('AI Librarian')
                with ui.row().classes('items-center gap-1.5'):
                    ui.icon('auto_stories', size='sm')
                    ui.label('Reader')

        # Form Side
        with ui.column().classes('w-full md:w-1/2 h-full items-center justify-center bg-slate-50 dark:bg-slate-900 p-4 sm:p-8 transition-colors duration-300 overflow-y-auto'):
            with ui.card().classes('w-full max-w-md p-5 sm:p-8 shadow-xl md:shadow-none border border-slate-200/80 dark:border-slate-800/80 md:border-none bg-white md:bg-transparent dark:bg-slate-900 rounded-2xl sm:rounded-3xl'):
                with ui.column().classes('w-full mb-4 sm:mb-6'):
                    ui.label('Welcome Back').classes('text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight mb-1')
                    ui.label('Sign in with your email or username').classes('text-xs sm:text-sm text-slate-500 dark:text-slate-400')

                # Identifier Field (Email or Username)
                identifier = ui.input(placeholder='Email or Username') \
                    .classes(INPUT_CLASSES) \
                    .props('rounded outlined dense autocomplete="username" autocapitalize="none" spellcheck="false"')
                with identifier.add_slot('prepend'):
                    ui.icon('person').classes('text-indigo-500 opacity-70')

                # Password Field
                pwd = ui.input(placeholder='Password', password=True) \
                    .classes('w-full mb-6') \
                    .props('rounded outlined dense autocomplete="current-password"')
                with pwd.add_slot('prepend'):
                    ui.icon('lock').classes('text-indigo-500 opacity-70')
                create_password_toggle(pwd)

                async def try_login():
                    clean_id = (identifier.value or '').strip()
                    clean_pwd = (pwd.value or '').strip()

                    if not clean_id or not clean_pwd:
                        ui.notify('Please fill in both email/username and password.', type='warning')
                        return

                    users = await mongo_db.get_users_by_identifier(clean_id)
                    if not users:
                        ui.notify('No account found with this email or username.', type='negative')
                        return

                    matched_user = None
                    for user in users:
                        hp = user.get('hashed_password')
                        if not hp:
                            continue
                        hp_bytes = hp.encode('utf-8') if isinstance(hp, str) else hp
                        try:
                            if bcrypt.checkpw(clean_pwd.encode('utf-8'), hp_bytes):
                                matched_user = user
                                break
                        except Exception:
                            continue

                    if matched_user:
                        token = create_access_token({"sub": matched_user['id'], "role": matched_user.get('role', 'user')})
                        set_user_session(matched_user, token)
                        await mongo_db.update_user_last_login(matched_user['id'])
                        ui.notify(f"Welcome back, {matched_user.get('username', 'User')}!", type='positive')
                        ui.navigate.to('/')
                    else:
                        ui.notify('Invalid credentials. Please verify your password.', type='negative')

                # Bind Enter Key to Submit
                identifier.on('keydown.enter', try_login)
                pwd.on('keydown.enter', try_login)

                ui.button('Sign In', on_click=try_login).classes(BTN_STYLE)

                with ui.row().classes('w-full justify-center items-center mt-6 gap-1 text-sm'):
                    ui.label("Don't have an account?").classes('text-slate-500 dark:text-slate-400')
                    ui.link('Create Account', '/signup').classes('text-indigo-600 dark:text-indigo-400 font-bold hover:underline')


async def signup_page():
    # If already logged in, redirect directly to dashboard
    if is_user_authenticated():
        ui.navigate.to('/')
        return

    dark = ui.dark_mode()
    ui.button(icon='dark_mode', on_click=dark.toggle) \
        .classes('absolute top-4 right-4 z-50 text-gray-500 dark:text-gray-300 hover:text-gray-700 dark:hover:white transition-colors') \
        .props('flat round size=md')

    with ui.row().classes('w-full h-screen m-0 p-0 overflow-hidden'):
        # Brand Side
        with ui.column().classes('hidden md:flex w-1/2 h-full bg-gradient-to-br from-purple-900 via-indigo-900 to-indigo-800 items-center justify-center text-white p-12 relative overflow-hidden'):
            ui.element('div').classes('absolute w-96 h-96 bg-purple-500/20 rounded-full blur-3xl -top-20 -right-20')
            ui.element('div').classes('absolute w-80 h-80 bg-indigo-500/20 rounded-full blur-3xl -bottom-20 -left-20')

            ui.icon('account_circle', size='5rem').classes('mb-6 opacity-95 drop-shadow-md')
            ui.label('Join Libre Library').classes('text-5xl font-black tracking-tight mb-3 text-center')
            ui.label('Unlock intelligent search, AI study companions, and flashcards.').classes('text-lg font-normal opacity-85 text-center max-w-sm')

        # Form Side
        with ui.column().classes('w-full md:w-1/2 h-full items-center justify-center bg-slate-50 dark:bg-slate-900 p-4 sm:p-8 transition-colors duration-300 overflow-y-auto'):
            with ui.card().classes('w-full max-w-md p-5 sm:p-8 shadow-xl md:shadow-none border border-slate-200/80 dark:border-slate-800/80 md:border-none bg-white md:bg-transparent dark:bg-slate-900 rounded-2xl sm:rounded-3xl'):
                with ui.column().classes('w-full mb-4 sm:mb-6'):
                    ui.label('Create Account').classes('text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight mb-1')
                    ui.label('Get started with your free digital library').classes('text-xs sm:text-sm text-slate-500 dark:text-slate-400')

                # Username Field
                username = ui.input(placeholder='Username') \
                    .classes(INPUT_CLASSES) \
                    .props('rounded outlined dense autocomplete="username" autocapitalize="none" spellcheck="false"')
                with username.add_slot('prepend'):
                    ui.icon('person_outline').classes('text-indigo-500 opacity-70')

                # Email Field
                email = ui.input(placeholder='Email Address') \
                    .classes(INPUT_CLASSES) \
                    .props('rounded outlined dense autocomplete="email" autocapitalize="none" spellcheck="false"')
                with email.add_slot('prepend'):
                    ui.icon('alternate_email').classes('text-indigo-500 opacity-70')

                # Password Field
                pwd = ui.input(placeholder='Password (min 6 characters)', password=True) \
                    .classes(INPUT_CLASSES) \
                    .props('rounded outlined dense autocomplete="new-password"')
                with pwd.add_slot('prepend'):
                    ui.icon('lock_outline').classes('text-indigo-500 opacity-70')
                create_password_toggle(pwd)

                # Confirm Password Field
                confirm_pwd = ui.input(placeholder='Confirm Password', password=True) \
                    .classes('w-full mb-6') \
                    .props('rounded outlined dense autocomplete="new-password"')
                with confirm_pwd.add_slot('prepend'):
                    ui.icon('lock_reset').classes('text-indigo-500 opacity-70')
                create_password_toggle(confirm_pwd)

                async def try_signup():
                    clean_username = (username.value or '').strip()
                    clean_email = (email.value or '').strip().lower()
                    clean_pwd = (pwd.value or '').strip()
                    clean_confirm = (confirm_pwd.value or '').strip()

                    # Validations
                    if not clean_username or not clean_email or not clean_pwd or not clean_confirm:
                        ui.notify("All fields are required.", type='warning')
                        return

                    if len(clean_username) < 3:
                        ui.notify("Username must be at least 3 characters long.", type='warning')
                        return

                    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", clean_email):
                        ui.notify("Please enter a valid email address.", type='warning')
                        return

                    if len(clean_pwd) < 6:
                        ui.notify("Password must be at least 6 characters long.", type='warning')
                        return

                    if clean_pwd != clean_confirm:
                        ui.notify("Passwords do not match.", type='warning')
                        return

                    # Case-insensitive collision checks
                    if await mongo_db.get_user_by_email(clean_email):
                        ui.notify("An account with this email already exists.", type='negative')
                        return

                    if await mongo_db.get_user_by_identifier(clean_username):
                        ui.notify("This username is already taken. Please choose another.", type='negative')
                        return

                    hashed = bcrypt.hashpw(clean_pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    users = await mongo_db.get_all_users()
                    role = "admin" if not users else "user"

                    created = await mongo_db.create_user(clean_username, clean_email, hashed, role)
                    if not created:
                        ui.notify("Registration failed. Please try again.", type='negative')
                        return

                    # Auto-login newly registered user directly
                    token = create_access_token({"sub": created['id'], "role": created['role']})
                    set_user_session(created, token)
                    await mongo_db.update_user_last_login(created['id'])
                    ui.notify(f"Welcome to Libre Library, {created['username']}!", type='positive')
                    ui.navigate.to('/')

                # Bind Enter Key
                username.on('keydown.enter', try_signup)
                email.on('keydown.enter', try_signup)
                pwd.on('keydown.enter', try_signup)
                confirm_pwd.on('keydown.enter', try_signup)

                ui.button('Create Account', on_click=try_signup).classes(BTN_STYLE)

                with ui.row().classes('w-full justify-center items-center mt-6 gap-1 text-sm'):
                    ui.label('Already have an account?').classes('text-slate-500 dark:text-slate-400')
                    ui.link('Sign In', '/login').classes('text-indigo-600 dark:text-indigo-400 font-bold hover:underline')