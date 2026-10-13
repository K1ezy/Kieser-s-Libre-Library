/**
 * Libre PDF Reader - Theme & Appearance Manager
 * Controls CSS canvas filters (Light, Warm Sepia, Slate Dark, OLED Black),
 * theme swatches, and parent window theme notifications.
 */
(function() {
    'use strict';

    const ThemeManager = {
        currentTheme: localStorage.getItem('libre_reader_theme') || 'light',

        applyTheme(theme, save = true) {
            this.currentTheme = theme;
            document.body.setAttribute('data-theme', theme);
            const label = document.getElementById('theme-label');
            if (label) label.innerText = theme.charAt(0).toUpperCase() + theme.slice(1);

            document.querySelectorAll('.theme-swatch').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('data-theme') === theme);
            });

            if (save) {
                localStorage.setItem('libre_reader_theme', theme);
                this.notifyParent();
            }
        },

        cycleTheme() {
            const themes = ['light', 'sepia', 'dark', 'black'];
            const nextIdx = (themes.indexOf(this.currentTheme) + 1) % themes.length;
            this.applyTheme(themes[nextIdx], true);
        },

        notifyParent() {
            try {
                window.parent.postMessage({
                    type: 'LIBRE_READER_THEME_CHANGE',
                    theme: this.currentTheme
                }, '*');
            } catch(e) {}
        },

        init() {
            this.applyTheme(this.currentTheme, false);

            const toggle = document.getElementById('appearance-toggle');
            const popover = document.getElementById('appearance-popover');
            if (toggle && popover) {
                toggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const isVisible = popover.style.display === 'flex';
                    popover.style.display = isVisible ? 'none' : 'flex';
                });

                document.addEventListener('click', (e) => {
                    if (popover && !popover.contains(e.target) && e.target !== toggle) {
                        popover.style.display = 'none';
                    }
                });
            }

            document.querySelectorAll('.theme-swatch').forEach(btn => {
                btn.addEventListener('click', () => this.applyTheme(btn.getAttribute('data-theme'), true));
            });

            const fsBtn = document.getElementById('fullscreen-btn');
            if (fsBtn) {
                fsBtn.addEventListener('click', () => {
                    if (!document.fullscreenElement) document.documentElement.requestFullscreen().catch(() => {});
                    else document.exitFullscreen().catch(() => {});
                });
            }
        }
    };

    window.ThemeManager = ThemeManager;
})();
