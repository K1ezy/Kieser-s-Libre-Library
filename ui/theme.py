from nicegui import ui, app
from core.config import settings
from datetime import datetime

# --- MODERN DESIGN SYSTEM & DARK MODE CSS ---
GLOBAL_THEME_STYLES = '''
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        :root {
            --font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }

        body {
            font-family: var(--font-family) !important;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            transition: background-color 0.25s ease, color 0.25s ease;
        }

        /* --- Custom Sleek Scrollbars --- */
        ::-webkit-scrollbar {
            width: 7px;
            height: 7px;
        }
        ::-webkit-scrollbar-track {
            background: transparent;
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(148, 163, 184, 0.4);
            border-radius: 9999px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(99, 102, 241, 0.7);
        }

        /* --- Dark Mode System Adaptation --- */
        body.body--dark {
            background-color: #0b0f19 !important; /* Premium Midnight Slate */
            color: #f1f5f9 !important;
        }

        body.body--dark .q-header {
            background-color: rgba(15, 23, 42, 0.9) !important;
            border-bottom-color: #1e293b !important;
        }

        body.body--dark .q-drawer {
            background-color: #0f172a !important;
            border-right-color: #1e293b !important;
        }

        body.body--dark .bg-white {
            background-color: #131d31 !important;
            color: #f8fafc !important;
            border-color: #1e293b !important;
        }

        body.body--dark .bg-slate-50,
        body.body--dark .bg-gray-50 {
            background-color: #0b0f19 !important;
        }

        body.body--dark .bg-gray-100 {
            background-color: #1a253c !important;
        }

        body.body--dark .bg-indigo-50 {
            background-color: rgba(99, 102, 241, 0.15) !important;
            color: #a5b4fc !important;
        }

        body.body--dark .text-slate-800,
        body.body--dark .text-gray-900,
        body.body--dark .text-gray-800 {
            color: #f8fafc !important;
        }

        body.body--dark .text-slate-700,
        body.body--dark .text-gray-700 {
            color: #cbd5e1 !important;
        }

        body.body--dark .text-slate-500,
        body.body--dark .text-slate-400,
        body.body--dark .text-gray-500 {
            color: #94a3b8 !important;
        }

        body.body--dark .border-gray-100,
        body.body--dark .border-gray-200,
        body.body--dark .border-slate-100,
        body.body--dark .border-slate-200,
        body.body--dark .border-b,
        body.body--dark .border-t {
            border-color: #1e293b !important;
        }

        /* Form Inputs & Quasar Controls in Dark Mode */
        body.body--dark .q-field--outlined .q-field__control {
            border-color: #334155 !important;
            background-color: #131d31 !important;
        }

        body.body--dark .q-field__native,
        body.body--dark .q-field__prefix,
        body.body--dark .q-field__suffix,
        body.body--dark .q-field__input {
            color: #f1f5f9 !important;
        }

        body.body--dark .q-menu,
        body.body--dark .q-dialog .q-card {
            background-color: #131d31 !important;
            color: #f1f5f9 !important;
            border: 1px solid #1e293b !important;
        }

        body.body--dark ::-webkit-scrollbar-thumb {
            background: rgba(100, 116, 139, 0.5);
        }
    </style>
'''

def is_night_time() -> bool:
    """Returns True if it's between 7 PM and 6 AM."""
    hour = datetime.now().hour
    return hour < 6 or hour >= 19

def get_current_mode_value() -> bool:
    """Returns True if Dark Mode is active."""
    user_pref = app.storage.user.get('dark_mode')
    if user_pref is None:
        return is_night_time()
    return bool(user_pref)

def toggle_dark_mode(e):
    """Callback for dark mode toggles."""
    is_dark = e.value if hasattr(e, 'value') else not get_current_mode_value()
    app.storage.user['dark_mode'] = is_dark
    
    if is_dark:
        ui.dark_mode().enable()
    else:
        ui.dark_mode().disable()

def apply_theme():
    """Applies global CSS design tokens, custom font, and initial color theme."""
    ui.add_head_html(GLOBAL_THEME_STYLES)
    ui.colors(
        primary=settings.UI_THEME_COLOR,
        secondary="#818cf8",
        accent="#a855f7",
        positive="#10b981",
        negative="#ef4444",
        info="#0ea5e9",
        warning="#f59e0b"
    )
    
    should_be_dark = get_current_mode_value()
    if should_be_dark:
        ui.dark_mode().enable()
    else:
        ui.dark_mode().disable()