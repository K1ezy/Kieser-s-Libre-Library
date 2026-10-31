"""
Mobile pull-to-refresh gesture.

Self-contained touch handler that, when the user pulls down from the very top of
the page, shows a spinner and reloads the route for fresh data — the native list
refresh pattern on phones. Desktop (mouse) never triggers it since only touch
events are bound. It suppresses the browser's own overscroll refresh while active
and ignores drawers, dialogs, inputs, and horizontal scrollers.
"""
from nicegui import ui


def pull_to_refresh() -> None:
    """Injects the pull-to-refresh indicator and gesture handler once per page."""
    ui.add_body_html('''
    <div id="libre-ptr-indicator" aria-hidden="true">
        <span class="libre-ptr-icon">&#8595;</span>
        <span class="libre-ptr-spin"></span>
        <span class="libre-ptr-text">Pull to refresh</span>
    </div>
    <style>
        /* Suppress the browser's native pull-to-refresh so ours is the only one. */
        html, body { overscroll-behavior-y: contain; }
        #libre-ptr-indicator {
            position: fixed;
            left: 50%;
            top: calc(env(safe-area-inset-top, 0px) + 56px);
            transform: translateX(-50%) translateY(-80px);
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            border-radius: 9999px;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.18);
            color: #4f46e5;
            font-size: 12px;
            font-weight: 700;
            z-index: 55;
            opacity: 0;
            pointer-events: none;
            will-change: transform, opacity;
        }
        #libre-ptr-indicator .libre-ptr-icon {
            font-size: 15px;
            line-height: 1;
            transition: transform 0.2s ease;
        }
        #libre-ptr-indicator.ready .libre-ptr-icon { transform: rotate(180deg); }
        #libre-ptr-indicator .libre-ptr-spin {
            display: none;
            width: 15px;
            height: 15px;
            border: 2px solid rgba(79, 70, 229, 0.25);
            border-top-color: #4f46e5;
            border-radius: 50%;
            animation: libre-ptr-rotate 0.7s linear infinite;
        }
        #libre-ptr-indicator.loading .libre-ptr-icon { display: none; }
        #libre-ptr-indicator.loading .libre-ptr-spin { display: inline-block; }
        @keyframes libre-ptr-rotate { to { transform: rotate(360deg); } }
    </style>
    <script>
    (function() {
        if (window.__librePtrInit) return;
        window.__librePtrInit = true;

        const THRESH = 72;
        const MAX = 110;
        let startY = 0, startX = 0, pulling = false, engaged = false, dist = 0;

        function ind() { return document.getElementById('libre-ptr-indicator'); }
        function txt() { const i = ind(); return i ? i.querySelector('.libre-ptr-text') : null; }

        function atTop() {
            const se = document.scrollingElement || document.documentElement;
            return (se.scrollTop || window.pageYOffset || 0) <= 0;
        }
        function blocked(t) {
            return !!(t && t.closest && t.closest(
                '.q-drawer, .q-dialog, .mobile-scroll-row, input, textarea, select, ' +
                '[contenteditable="true"], .q-menu, [id^="reader"]'
            ));
        }
        function modalOpen() {
            return !!document.querySelector('.q-dialog__inner, .q-drawer--on-top');
        }
        function reset() {
            const i = ind();
            if (!i) return;
            i.style.transition = 'transform .25s cubic-bezier(.16,1,.3,1), opacity .2s ease';
            i.style.transform = 'translateX(-50%) translateY(-80px)';
            i.style.opacity = '0';
            i.classList.remove('ready', 'loading');
            const x = txt(); if (x) x.innerText = 'Pull to refresh';
        }

        window.addEventListener('touchstart', function(e) {
            if (e.touches.length !== 1 || !atTop() || modalOpen() || blocked(e.target)) {
                pulling = false; return;
            }
            const t = e.touches[0];
            startY = t.clientY; startX = t.clientX;
            pulling = true; engaged = false; dist = 0;
            const i = ind(); if (i) i.style.transition = 'none';
        }, { passive: true });

        window.addEventListener('touchmove', function(e) {
            if (!pulling) return;
            const t = e.touches[0];
            const dy = t.clientY - startY, dx = t.clientX - startX;
            if (dy <= 0 || Math.abs(dx) > Math.abs(dy)) {
                if (!engaged) pulling = false;
                return;
            }
            if (!atTop()) { pulling = false; reset(); return; }
            engaged = true;
            e.preventDefault(); // stop native rubber-band / browser refresh
            dist = Math.min(MAX, dy * 0.5);
            const i = ind();
            if (i) {
                i.style.transform = 'translateX(-50%) translateY(' + (dist - 80) + 'px)';
                i.style.opacity = String(Math.min(1, dist / THRESH));
                i.classList.toggle('ready', dist >= THRESH);
                const x = txt();
                if (x) x.innerText = dist >= THRESH ? 'Release to refresh' : 'Pull to refresh';
            }
        }, { passive: false });

        function end() {
            if (!pulling) return;
            pulling = false;
            if (engaged && dist >= THRESH) {
                const i = ind();
                if (i) {
                    i.style.transition = 'transform .2s ease, opacity .2s ease';
                    i.style.transform = 'translateX(-50%) translateY(10px)';
                    i.style.opacity = '1';
                    i.classList.remove('ready');
                    i.classList.add('loading');
                    const x = txt(); if (x) x.innerText = 'Refreshing\\u2026';
                }
                try { if (navigator.vibrate) navigator.vibrate(20); } catch (err) {}
                setTimeout(function() { try { location.reload(); } catch (err) {} }, 200);
            } else {
                reset();
            }
        }

        window.addEventListener('touchend', end, { passive: true });
        window.addEventListener('touchcancel', function() { pulling = false; reset(); }, { passive: true });
    })();
    </script>
    ''')
