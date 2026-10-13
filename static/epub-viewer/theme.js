/**
 * Libre EPUB Reader - Theme & Typography Manager
 * Handles light, sepia, dark, and OLED black modes, font size, family, and line height.
 */
(function() {
    'use strict';

    const ThemeManager = {
        currentTheme: localStorage.getItem('libre_reader_theme') || 'light',
        currentFontSize: parseInt(localStorage.getItem('libre_reader_font_size') || '16', 10),
        currentFontFamily: localStorage.getItem('libre_reader_font_family') || 'sans',
        currentLineHeight: parseFloat(localStorage.getItem('libre_reader_line_height') || '1.65'),
        rendition: null,

        fontFamilies: {
            sans: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            serif: "'Merriweather', Georgia, 'Times New Roman', serif",
            dyslexic: "'Atkinson Hyperlegible', -apple-system, sans-serif"
        },

        getThemeCss(theme) {
            const themes = {
                sepia: { body: { background: '#f4ecd8 !important', color: '#3d2f1d !important' }, 'p, div, span, li': { color: '#3d2f1d !important' } },
                dark:  { body: { background: '#0f172a !important', color: '#e2e8f0 !important' }, 'p, div, span, li': { color: '#e2e8f0 !important' } },
                black: { body: { background: '#000000 !important', color: '#d1d5db !important' }, 'p, div, span, li': { color: '#d1d5db !important' } }
            };
            return themes[theme] || { body: { background: '#ffffff !important', color: '#0f172a !important' }, 'p, div, span, li': { color: '#0f172a !important' } };
        },

        setRendition(rend) {
            this.rendition = rend;
            if (!rend) return;
            ['light', 'sepia', 'dark', 'black'].forEach(t => rend.themes.register(t, this.getThemeCss(t)));
            this.applyTheme(this.currentTheme, false);
            this.applyFontSize(this.currentFontSize, false);
            this.applyFontFamily(this.currentFontFamily, false);
            this.applyLineHeight(this.currentLineHeight, false);
        },

        applyTheme(theme, save = true) {
            this.currentTheme = theme;
            document.body.setAttribute('data-theme', theme);
            const label = document.getElementById('theme-label');
            if (label) label.innerText = theme.charAt(0).toUpperCase() + theme.slice(1);

            document.querySelectorAll('.theme-swatch').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('data-theme') === theme);
            });

            if (this.rendition) {
                try { this.rendition.themes.select(theme); } catch(e) {}
            }

            if (save) {
                localStorage.setItem('libre_reader_theme', theme);
                this.notifyParent();
            }
        },

        applyFontSize(size, save = true) {
            this.currentFontSize = Math.max(12, Math.min(32, size));
            const fontLabel = document.getElementById('font-size-val');
            if (fontLabel) fontLabel.innerText = `${this.currentFontSize}px`;

            if (this.rendition) {
                try { this.rendition.themes.fontSize(`${this.currentFontSize}px`); } catch(e) {}
            }

            if (save) {
                localStorage.setItem('libre_reader_font_size', this.currentFontSize);
                this.notifyParent();
            }
        },

        applyFontFamily(fontKey, save = true) {
            this.currentFontFamily = fontKey;
            document.querySelectorAll('.font-family-group .pill-btn').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('data-font') === fontKey);
            });

            const fontVal = this.fontFamilies[fontKey] || this.fontFamilies.sans;
            if (this.rendition) {
                try { this.rendition.themes.font(fontVal); } catch(e) {}
            }

            if (save) {
                localStorage.setItem('libre_reader_font_family', fontKey);
                this.notifyParent();
            }
        },

        applyLineHeight(height, save = true) {
            this.currentLineHeight = height;
            document.querySelectorAll('.line-height-group .pill-btn').forEach(btn => {
                btn.classList.toggle('active', parseFloat(btn.getAttribute('data-height')) === height);
            });

            if (this.rendition) {
                try { this.rendition.themes.override('line-height', `${this.currentLineHeight} !important`); } catch(e) {}
            }

            if (save) {
                localStorage.setItem('libre_reader_line_height', this.currentLineHeight);
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
                    theme: this.currentTheme,
                    font_size: this.currentFontSize,
                    font_family: this.currentFontFamily,
                    line_height: this.currentLineHeight
                }, '*');
            } catch(e) {}
        },

        init() {
            this.applyTheme(this.currentTheme, false);
            this.applyFontSize(this.currentFontSize, false);
            this.applyFontFamily(this.currentFontFamily, false);
            this.applyLineHeight(this.currentLineHeight, false);

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

            const fontDec = document.getElementById('font-dec-btn');
            const fontInc = document.getElementById('font-inc-btn');
            if (fontDec) fontDec.addEventListener('click', () => this.applyFontSize(this.currentFontSize - 1, true));
            if (fontInc) fontInc.addEventListener('click', () => this.applyFontSize(this.currentFontSize + 1, true));

            document.querySelectorAll('.font-family-group .pill-btn').forEach(btn => {
                btn.addEventListener('click', () => this.applyFontFamily(btn.getAttribute('data-font'), true));
            });

            document.querySelectorAll('.line-height-group .pill-btn').forEach(btn => {
                btn.addEventListener('click', () => this.applyLineHeight(parseFloat(btn.getAttribute('data-height')), true));
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
