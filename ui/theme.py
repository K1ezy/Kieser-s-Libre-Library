from nicegui import ui, app
from core.config import settings

# --- MODERN CLEAN LIGHT DESIGN SYSTEM ---
GLOBAL_THEME_STYLES = '''
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta name="theme-color" content="#4f46e5">
    <meta name="color-scheme" content="light">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        :root {
            color-scheme: light !important;
            --font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            --safe-area-top: env(safe-area-inset-top, 0px);
            --safe-area-bottom: env(safe-area-inset-bottom, 0px);
            --safe-area-left: env(safe-area-inset-left, 0px);
            --safe-area-right: env(safe-area-inset-right, 0px);
        }

        *, *::before, *::after {
            box-sizing: border-box;
            -webkit-tap-highlight-color: transparent;
        }

        /* Permanently enforce clean, coherent light theme across all devices & mobile OS settings */
        html, body, body.body--dark {
            overflow-x: hidden;
            max-width: 100vw;
            width: 100%;
            font-family: var(--font-family) !important;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            touch-action: manipulation;
            overscroll-behavior-y: none;
            -webkit-overflow-scrolling: touch;
            background-color: #f8fafc !important; /* Tailwind slate-50 */
            color: #0f172a !important;            /* Tailwind slate-900 */
        }

        /* Neutralize Quasar dark mode artifacts on body or child elements */
        body.body--dark .bg-white,
        .bg-white {
            background-color: #ffffff !important;
            color: #0f172a !important;
        }

        body.body--dark .bg-slate-50,
        .bg-slate-50 {
            background-color: #f8fafc !important;
        }

        body.body--dark .text-slate-900,
        .text-slate-900 {
            color: #0f172a !important;
        }

        body.body--dark .text-slate-800,
        .text-slate-800 {
            color: #1e293b !important;
        }

        body.body--dark .text-slate-700,
        .text-slate-700 {
            color: #334155 !important;
        }

        body.body--dark .text-slate-500,
        .text-slate-500 {
            color: #64748b !important;
        }

        body.body--dark .text-slate-400,
        .text-slate-400 {
            color: #94a3b8 !important;
        }

        /* Quasar components light mode enforcement */
        .q-header {
            background-color: rgba(255, 255, 255, 0.95) !important;
            color: #0f172a !important;
            border-bottom: 1px solid #e2e8f0 !important;
        }

        .q-drawer {
            background-color: #ffffff !important;
            color: #0f172a !important;
            border-right: 1px solid #e2e8f0 !important;
        }

        .q-dialog .q-card,
        .q-menu {
            background-color: #ffffff !important;
            color: #0f172a !important;
            border: 1px solid #e2e8f0 !important;
        }

        .q-field--outlined .q-field__control {
            background-color: #ffffff !important;
            border-color: #cbd5e1 !important;
        }

        .q-field__native,
        .q-field__input {
            color: #0f172a !important;
        }

        /* Prevent iOS automatic zoom on focus while retaining clear legibility */
        @media (max-width: 768px) {
            input, select, textarea, .q-field__native, .q-field__input {
                font-size: 16px !important;
            }
            .q-btn:active {
                transform: scale(0.97);
            }
        }

        .touch-pan-x {
            touch-action: pan-x;
            -webkit-overflow-scrolling: touch;
        }

        .touch-pan-y {
            touch-action: pan-y;
            -webkit-overflow-scrolling: touch;
        }

        /* Responsive Text and Preformatted Code Blocks */
        pre, code {
            max-width: 100%;
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-word;
        }

        table {
            max-width: 100%;
            overflow-x: auto;
            display: block;
        }

        img {
            max-width: 100%;
            height: auto;
        }

        /* Custom Sleek Light Scrollbars */
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
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
    </style>
'''

def apply_theme():
    """Applies clean, unified light design tokens, Inter typography, and crisp palette."""
    ui.add_head_html(GLOBAL_THEME_STYLES)
    ui.colors(
        primary="#4f46e5",    # Indigo 600
        secondary="#6366f1",  # Indigo 500
        accent="#7c3aed",     # Purple 600
        positive="#10b981",   # Emerald 500
        negative="#f43f5e",   # Rose 500
        info="#0ea5e9",       # Sky 500
        warning="#f59e0b"     # Amber 500
    )
    ui.dark_mode().disable()
    if 'dark_mode' in app.storage.user:
        app.storage.user.pop('dark_mode', None)
    ui.run_javascript("""
        document.documentElement.classList.remove('dark');
        document.body.classList.remove('body--dark');
        if (window.Quasar && window.Quasar.dark) {
            window.Quasar.dark.set(false);
        }
    """)