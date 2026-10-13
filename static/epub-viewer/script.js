/**
 * =========================================================================
 * LIBRE EPUB READER ENGINE (Modular & High-Performance)
 * ePub.js Core, Theme Synchronization, Progress Telemetry & Annotations
 * =========================================================================
 */

(function() {
    'use strict';

    // -------------------------------------------------------------------------
    // 1. CONFIGURATION & STATE INITIALIZATION
    // -------------------------------------------------------------------------
    const urlParams = new URLSearchParams(window.location.search);
    const bookUrl = urlParams.get('file');
    const bookId = urlParams.get('book_id') || '';
    const userId = urlParams.get('user_id') || 'guest';
    const initialCfi = urlParams.get('cfi') ? decodeURIComponent(urlParams.get('cfi')) : null;
    const initialPage = parseInt(urlParams.get('page') || '1', 10);
    const totalPages = Math.max(1, parseInt(urlParams.get('total') || '100', 10));

    const DOM = {
        errorMsg: document.getElementById('error-msg'),
        pageInfo: document.getElementById('page-info'),
        appearanceToggle: document.getElementById('appearance-toggle'),
        appearancePopover: document.getElementById('appearance-popover'),
        themeLabel: document.getElementById('theme-label'),
        fontSizeVal: document.getElementById('font-size-val'),
        fullscreenBtn: document.getElementById('fullscreen-btn'),
        prevBtn: document.getElementById('prev'),
        nextBtn: document.getElementById('next'),
        selectionPopover: document.getElementById('selection-popover'),
        popNoteContainer: document.getElementById('pop-note-container'),
        popNoteText: document.getElementById('pop-note-text'),
        popNoteSave: document.getElementById('pop-note-save'),
        popAddNoteBtn: document.getElementById('pop-add-note-btn'),
        popCopyBtn: document.getElementById('pop-copy-btn'),
        popAskTarsBtn: document.getElementById('pop-ask-tars-btn'),
        aiExplainerCard: document.getElementById('ai-explainer-card'),
        aiCardBody: document.getElementById('ai-card-body'),
        aiCardClose: document.getElementById('ai-card-close'),
        aiAttachNoteBtn: document.getElementById('ai-attach-note-btn'),
        aiOpenChatBtn: document.getElementById('ai-open-chat-btn'),
        highlightPopover: document.getElementById('highlight-popover'),
        hlEditNoteText: document.getElementById('hl-edit-note-text'),
        hlSaveNoteBtn: document.getElementById('hl-save-note-btn'),
        hlDeleteBtn: document.getElementById('hl-delete-btn'),
        annotationsDrawer: document.getElementById('annotations-drawer'),
        drawerToggleBtn: document.getElementById('annotations-drawer-toggle'),
        drawerCloseBtn: document.getElementById('drawer-close-btn'),
        drawerBadge: document.getElementById('annotations-badge'),
        drawerCount: document.getElementById('drawer-count'),
        drawerCards: document.getElementById('drawer-cards'),
        drawerSearch: document.getElementById('drawer-search'),
        drawerExportBtn: document.getElementById('drawer-export-btn'),
        readerToast: document.getElementById('reader-toast')
    };

    if (!bookUrl) {
        if (DOM.errorMsg) {
            DOM.errorMsg.style.display = 'block';
            DOM.errorMsg.innerText = "Error: No book file specified in query parameters.";
        }
        return;
    }

    let book = null;
    let rendition = null;
    let isRestoring = Boolean(initialCfi || (initialPage > 1));
    let lastNotifiedCfi = initialCfi || null;
    let lastNotifiedPage = initialPage;
    let saveDebounceTimer = null;
    let pendingSavePayload = null;
    let toastTimer = null;

    // -------------------------------------------------------------------------
    // 2. THEME & TYPOGRAPHY MANAGER
    // -------------------------------------------------------------------------
    const ThemeManager = {
        currentTheme: localStorage.getItem('libre_reader_theme') || 'light',
        currentFontSize: parseInt(localStorage.getItem('libre_reader_font_size') || '16', 10),
        currentFontFamily: localStorage.getItem('libre_reader_font_family') || 'sans',
        currentLineHeight: parseFloat(localStorage.getItem('libre_reader_line_height') || '1.65'),

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

        applyTheme(theme, save = true) {
            this.currentTheme = theme;
            document.body.setAttribute('data-theme', theme);
            if (DOM.themeLabel) {
                DOM.themeLabel.innerText = theme.charAt(0).toUpperCase() + theme.slice(1);
            }

            document.querySelectorAll('.theme-swatch').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('data-theme') === theme);
            });

            if (rendition) {
                try { rendition.themes.select(theme); } catch(e) {}
            }

            if (save) {
                localStorage.setItem('libre_reader_theme', theme);
                this.notifyParent();
            }
        },

        applyFontSize(size, save = true) {
            this.currentFontSize = Math.max(12, Math.min(32, size));
            if (DOM.fontSizeVal) DOM.fontSizeVal.innerText = `${this.currentFontSize}px`;

            if (rendition) {
                try { rendition.themes.fontSize(`${this.currentFontSize}px`); } catch(e) {}
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
            if (rendition) {
                try { rendition.themes.font(fontVal); } catch(e) {}
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

            if (rendition) {
                try { rendition.themes.override('line-height', `${this.currentLineHeight} !important`); } catch(e) {}
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

        registerRenditionThemes() {
            if (!rendition) return;
            ['light', 'sepia', 'dark', 'black'].forEach(t => {
                rendition.themes.register(t, this.getThemeCss(t));
            });
            this.applyTheme(this.currentTheme, false);
            this.applyFontSize(this.currentFontSize, false);
            this.applyFontFamily(this.currentFontFamily, false);
            this.applyLineHeight(this.currentLineHeight, false);
        }
    };

    // -------------------------------------------------------------------------
    // 3. READING PROGRESS & TELEMETRY SYNCHRONIZATION
    // -------------------------------------------------------------------------
    const ProgressSync = {
        updateHud(page, total, pct, cfi) {
            if (DOM.pageInfo) {
                DOM.pageInfo.innerText = `Page ${page} of ${total} (${pct}%)`;
            }

            try {
                window.parent.postMessage({
                    type: 'LIBRE_READER_PROGRESS',
                    book_id: bookId,
                    current_page: page,
                    total_pages: total,
                    percentage: pct,
                    cfi: cfi,
                    theme: ThemeManager.currentTheme,
                    font_size: ThemeManager.currentFontSize,
                    font_family: ThemeManager.currentFontFamily,
                    line_height: ThemeManager.currentLineHeight
                }, '*');
            } catch (err) {}
        },

        scheduleSave(payload) {
            pendingSavePayload = {
                ...payload,
                theme: ThemeManager.currentTheme,
                font_size: ThemeManager.currentFontSize,
                font_family: ThemeManager.currentFontFamily,
                line_height: ThemeManager.currentLineHeight
            };
            if (saveDebounceTimer) clearTimeout(saveDebounceTimer);
            saveDebounceTimer = setTimeout(() => {
                this.persistReadingProgress(pendingSavePayload);
            }, 500);
        },

        async persistReadingProgress(payload) {
            if (!payload || !payload.book_id) return;
            try {
                await fetch('/api/progress/sync', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
            } catch (err) {
                console.error("[EPUB Engine] Error persisting progress:", err);
            }
        },

        flushPendingSave() {
            if (!pendingSavePayload) return;
            const payloadString = JSON.stringify(pendingSavePayload);
            if (navigator.sendBeacon) {
                navigator.sendBeacon('/api/progress/sync', new Blob([payloadString], { type: 'application/json' }));
            } else {
                fetch('/api/progress/sync', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: payloadString,
                    keepalive: true
                });
            }
            pendingSavePayload = null;
        }
    };

    window.addEventListener('beforeunload', () => ProgressSync.flushPendingSave());
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') ProgressSync.flushPendingSave();
    });

    // -------------------------------------------------------------------------
    // 4. TOAST NOTIFICATION UTILITY
    // -------------------------------------------------------------------------
    function showToast(msg) {
        if (!DOM.readerToast) return;
        DOM.readerToast.innerText = msg;
        DOM.readerToast.classList.add('show');
        if (toastTimer) clearTimeout(toastTimer);
        toastTimer = setTimeout(() => {
            DOM.readerToast.classList.remove('show');
        }, 2400);
    }

    function escapeHtml(text) {
        if (!text) return '';
        return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function dismissAllPopovers() {
        if (DOM.selectionPopover) DOM.selectionPopover.style.display = 'none';
        if (DOM.popNoteContainer) DOM.popNoteContainer.style.display = 'none';
        if (DOM.highlightPopover) DOM.highlightPopover.style.display = 'none';
        if (DOM.aiExplainerCard) DOM.aiExplainerCard.style.display = 'none';
    }

    // -------------------------------------------------------------------------
    // 5. ANNOTATIONS & STUDY HIGHLIGHTS MANAGER
    // -------------------------------------------------------------------------
    const AnnotationManager = {
        annotations: [],
        activeCfiRange: null,
        activeSelectedText: "",
        activePopoverColor: "yellow",
        activeHighlight: null,
        currentFilter: 'all',
        currentSearch: '',

        getColorHex(color) {
            const map = { green: '#bbf7d0', blue: '#bfdbfe', pink: '#fbcfe8' };
            return map[(color || 'yellow').toLowerCase()] || '#fef08a';
        },

        renderSingleHighlight(ann) {
            if (!rendition || !ann.cfi_range) return;
            try {
                rendition.annotations.highlight(
                    ann.cfi_range,
                    { id: ann.id, color: ann.color },
                    (e) => this.onHighlightClicked(e, ann),
                    'hl-' + ann.color,
                    { fill: this.getColorHex(ann.color), 'fill-opacity': '0.38' }
                );
            } catch(e) {}
        },

        async fetchAnnotations() {
            try {
                const res = await fetch(`/api/annotations/${encodeURIComponent(bookId)}?user_id=${encodeURIComponent(userId)}`);
                const data = await res.json();
                if (res.ok && data.annotations) {
                    this.annotations = data.annotations;
                    this.updateDrawerUI();
                    this.annotations.forEach(ann => this.renderSingleHighlight(ann));
                }
            } catch(e) {
                console.error("[EPUB Engine] Error fetching annotations:", e);
            }
        },

        async createAnnotation(color, note = "") {
            if (!this.activeSelectedText || !this.activeCfiRange) return;
            const payload = {
                book_id: bookId,
                user_id: userId,
                selected_text: this.activeSelectedText,
                color: color || "yellow",
                cfi_range: this.activeCfiRange,
                page_number: lastNotifiedPage || 1,
                note: note
            };

            try {
                const res = await fetch('/api/annotations/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (res.ok && data.annotation) {
                    this.annotations.unshift(data.annotation);
                    this.renderSingleHighlight(data.annotation);
                    this.updateDrawerUI();
                    dismissAllPopovers();
                    showToast(note ? "Highlight with note saved!" : "Highlight saved!");
                } else {
                    showToast("Failed to save highlight.");
                }
            } catch(e) {
                showToast("Error saving highlight.");
            }
        },

        onHighlightClicked(e, ann) {
            e.stopPropagation();
            this.activeHighlight = ann;

            const iframe = document.querySelector('#viewer iframe');
            const iframeRect = iframe ? iframe.getBoundingClientRect() : { left: 0, top: 0 };
            const clientX = e.clientX !== undefined ? e.clientX : 150;
            const clientY = e.clientY !== undefined ? e.clientY : 150;

            const x = Math.max(12, Math.min(window.innerWidth - 260, iframeRect.left + clientX - 100));
            const y = Math.max(60, iframeRect.top + clientY - 60);

            dismissAllPopovers();
            if (DOM.highlightPopover) {
                DOM.highlightPopover.style.left = `${x}px`;
                DOM.highlightPopover.style.top = `${y}px`;
                DOM.highlightPopover.style.display = 'flex';
                if (DOM.hlEditNoteText) DOM.hlEditNoteText.value = ann.note || '';
            }
        },

        async updateAnnotation(annId, updates) {
            if (!annId) return;
            try {
                const res = await fetch(`/api/annotations/${encodeURIComponent(annId)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(updates)
                });
                const data = await res.json();
                if (res.ok && data.annotation) {
                    const idx = this.annotations.findIndex(a => a.id === annId);
                    if (idx !== -1) {
                        this.annotations[idx] = data.annotation;
                        if (rendition && data.annotation.cfi_range) {
                            try {
                                rendition.annotations.remove(data.annotation.cfi_range, "highlight");
                                this.renderSingleHighlight(data.annotation);
                            } catch(e) {}
                        }
                    }
                    this.updateDrawerUI();
                    dismissAllPopovers();
                    showToast("Annotation updated!");
                }
            } catch(e) {}
        },

        async deleteAnnotation(annId) {
            if (!annId) return;
            try {
                const res = await fetch(`/api/annotations/${encodeURIComponent(annId)}?user_id=${encodeURIComponent(userId)}`, {
                    method: 'DELETE'
                });
                if (res.ok) {
                    const target = this.annotations.find(a => a.id === annId);
                    if (target && target.cfi_range && rendition) {
                        try { rendition.annotations.remove(target.cfi_range, "highlight"); } catch(e) {}
                    }
                    this.annotations = this.annotations.filter(a => a.id !== annId);
                    this.updateDrawerUI();
                    dismissAllPopovers();
                    showToast("Highlight deleted.");
                }
            } catch(e) {}
        },

        updateDrawerUI() {
            if (DOM.drawerBadge) {
                DOM.drawerBadge.innerText = this.annotations.length;
                DOM.drawerBadge.style.display = this.annotations.length > 0 ? 'inline-block' : 'none';
            }
            if (DOM.drawerCount) DOM.drawerCount.innerText = this.annotations.length;
            if (!DOM.drawerCards) return;

            const filtered = this.annotations.filter(ann => {
                const matchColor = (this.currentFilter === 'all') || (ann.color === this.currentFilter);
                const query = this.currentSearch.toLowerCase();
                const matchSearch = !query ||
                    (ann.selected_text && ann.selected_text.toLowerCase().includes(query)) ||
                    (ann.note && ann.note.toLowerCase().includes(query));
                return matchColor && matchSearch;
            });

            if (filtered.length === 0) {
                DOM.drawerCards.innerHTML = `
                    <div style="text-align: center; color: var(--text-controls); padding: 40px 16px; font-size: 13px;">
                        <span style="font-size: 28px; display: block; margin-bottom: 8px;">📖</span>
                        ${this.annotations.length === 0 ? 'No annotations yet.<br>Select any passage in the book to highlight or add study notes!' : 'No annotations match your filter.'}
                    </div>
                `;
                return;
            }

            DOM.drawerCards.innerHTML = filtered.map(ann => {
                const colorClass = `ann-card-${ann.color || 'yellow'}`;
                const noteHtml = ann.note ? `<div class="ann-student-note">💭 ${escapeHtml(ann.note)}</div>` : '';
                return `
                    <div class="ann-card ${colorClass}" data-ann-id="${ann.id}" data-cfi="${ann.cfi_range || ''}">
                        <div class="ann-card-header">
                            <span style="text-transform: capitalize;">● ${(ann.color || 'yellow')}</span>
                            <span>Page ${ann.page_number || 1}</span>
                        </div>
                        <div class="ann-quote">"${escapeHtml(ann.selected_text || '')}"</div>
                        ${noteHtml}
                        <div class="ann-card-actions">
                            <button class="tool-btn jump-btn" style="padding: 3px 8px; font-size: 11px;">Jump ↗</button>
                            <button class="tool-btn del-btn" style="padding: 3px 8px; font-size: 11px; color: #ef4444;">Delete</button>
                        </div>
                    </div>
                `;
            }).join('');

            // Card Action Listeners
            DOM.drawerCards.querySelectorAll('.ann-card').forEach(card => {
                const annId = card.getAttribute('data-ann-id');
                const cfi = card.getAttribute('data-cfi');

                const jumpBtn = card.querySelector('.jump-btn');
                if (jumpBtn) {
                    jumpBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        if (cfi && rendition) rendition.display(cfi);
                    });
                }

                const delBtn = card.querySelector('.del-btn');
                if (delBtn) {
                    delBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        this.deleteAnnotation(annId);
                    });
                }

                card.addEventListener('click', () => {
                    if (cfi && rendition) rendition.display(cfi);
                });
            });
        },

        toggleDrawer() {
            if (!DOM.annotationsDrawer) return;
            const isOpen = DOM.annotationsDrawer.classList.contains('open');
            DOM.annotationsDrawer.classList.toggle('open', !isOpen);
            if (!isOpen) dismissAllPopovers();
        }
    };

    // -------------------------------------------------------------------------
    // 6. TARS SOCRATIC AI EXPLAINER
    // -------------------------------------------------------------------------
    const TarsExplainer = {
        lastExplainedText: "",
        lastExplanationResult: "",

        async trigger(text) {
            if (!text) return;
            this.lastExplainedText = text;
            const popLeft = DOM.selectionPopover ? DOM.selectionPopover.style.left : "20px";
            const popTop = DOM.selectionPopover ? DOM.selectionPopover.style.top : "80px";
            dismissAllPopovers();

            if (DOM.aiExplainerCard) {
                DOM.aiExplainerCard.style.left = popLeft;
                DOM.aiExplainerCard.style.top = popTop;
                DOM.aiExplainerCard.style.display = 'flex';
                if (DOM.aiCardBody) {
                    DOM.aiCardBody.innerHTML = `
                        <div style="display: flex; align-items: center; gap: 8px; padding: 6px 0; color: var(--text-controls);">
                            <div style="width: 14px; height: 14px; border: 2px solid var(--accent-color); border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
                            <span>TARS is consulting knowledge archive...</span>
                        </div>
                    `;
                }
                if (DOM.aiAttachNoteBtn) DOM.aiAttachNoteBtn.style.display = 'none';
            }

            try {
                const res = await fetch('/api/annotations/explain', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ passage_text: text, book_id: bookId })
                });
                const data = await res.json();
                this.lastExplanationResult = data.explanation || "No explanation provided.";
                if (DOM.aiCardBody) {
                    DOM.aiCardBody.innerHTML = `
                        <div style="font-style: italic; margin-bottom: 6px; color: var(--text-controls); font-size: 11px;">"${escapeHtml(text.length > 80 ? text.substring(0, 80) + '...' : text)}"</div>
                        <div>${escapeHtml(this.lastExplanationResult)}</div>
                    `;
                }
                if (DOM.aiAttachNoteBtn) DOM.aiAttachNoteBtn.style.display = 'inline-block';
            } catch(e) {
                if (DOM.aiCardBody) DOM.aiCardBody.innerText = "TARS explanation unavailable at this time.";
            }
        }
    };

    // -------------------------------------------------------------------------
    // 7. KEYBOARD SHORTCUTS & EVENT LISTENERS
    // -------------------------------------------------------------------------
    function handleKeyDown(e) {
        if (e.target && ['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return;

        if (e.key === "ArrowLeft" || e.key === "PageUp" || e.key === "j") {
            if (rendition) rendition.prev();
            e.preventDefault();
        } else if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === "k") {
            if (rendition) rendition.next();
            e.preventDefault();
        } else if (e.key === "t" || e.key === "T") {
            ThemeManager.cycleTheme();
            e.preventDefault();
        } else if (e.key === "h" || e.key === "H") {
            AnnotationManager.toggleDrawer();
            e.preventDefault();
        } else if (e.key === "+" || e.key === "=") {
            ThemeManager.applyFontSize(ThemeManager.currentFontSize + 1, true);
            e.preventDefault();
        } else if (e.key === "-" || e.key === "_") {
            ThemeManager.applyFontSize(ThemeManager.currentFontSize - 1, true);
            e.preventDefault();
        } else if (e.key === "f" || e.key === "F") {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(() => {});
            } else {
                document.exitFullscreen().catch(() => {});
            }
            e.preventDefault();
        } else if (e.key === "Escape") {
            dismissAllPopovers();
            if (DOM.appearancePopover) DOM.appearancePopover.style.display = 'none';
            if (DOM.annotationsDrawer) DOM.annotationsDrawer.classList.remove('open');
        }
    }

    document.addEventListener("keydown", handleKeyDown);

    // Appearance Popover Listeners
    if (DOM.appearanceToggle && DOM.appearancePopover) {
        DOM.appearanceToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            const isVisible = DOM.appearancePopover.style.display === 'flex';
            DOM.appearancePopover.style.display = isVisible ? 'none' : 'flex';
        });

        document.addEventListener('click', (e) => {
            if (DOM.appearancePopover && !DOM.appearancePopover.contains(e.target) && e.target !== DOM.appearanceToggle) {
                DOM.appearancePopover.style.display = 'none';
            }
        });
    }

    document.querySelectorAll('.theme-swatch').forEach(btn => {
        btn.addEventListener('click', () => {
            ThemeManager.applyTheme(btn.getAttribute('data-theme'), true);
        });
    });

    const fontDecBtn = document.getElementById('font-dec-btn');
    const fontIncBtn = document.getElementById('font-inc-btn');
    if (fontDecBtn) fontDecBtn.addEventListener('click', () => ThemeManager.applyFontSize(ThemeManager.currentFontSize - 1, true));
    if (fontIncBtn) fontIncBtn.addEventListener('click', () => ThemeManager.applyFontSize(ThemeManager.currentFontSize + 1, true));

    document.querySelectorAll('.font-family-group .pill-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            ThemeManager.applyFontFamily(btn.getAttribute('data-font'), true);
        });
    });

    document.querySelectorAll('.line-height-group .pill-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            ThemeManager.applyLineHeight(parseFloat(btn.getAttribute('data-height')), true);
        });
    });

    if (DOM.fullscreenBtn) {
        DOM.fullscreenBtn.addEventListener('click', () => {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(() => {});
            } else {
                document.exitFullscreen().catch(() => {});
            }
        });
    }

    // Annotation Selection Popover Listeners
    document.querySelectorAll('#selection-popover .hl-swatch').forEach(swatch => {
        swatch.addEventListener('click', (e) => {
            e.stopPropagation();
            const color = swatch.getAttribute('data-color') || 'yellow';
            AnnotationManager.activePopoverColor = color;
            AnnotationManager.createAnnotation(color, "");
        });
    });

    if (DOM.popAddNoteBtn) {
        DOM.popAddNoteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!DOM.popNoteContainer) return;
            const isOpen = DOM.popNoteContainer.style.display === 'flex';
            DOM.popNoteContainer.style.display = isOpen ? 'none' : 'flex';
            if (!isOpen && DOM.popNoteText) DOM.popNoteText.focus();
        });
    }

    if (DOM.popNoteSave) {
        DOM.popNoteSave.addEventListener('click', (e) => {
            e.stopPropagation();
            const note = DOM.popNoteText ? DOM.popNoteText.value.trim() : "";
            AnnotationManager.createAnnotation(AnnotationManager.activePopoverColor || "yellow", note);
        });
    }

    if (DOM.popCopyBtn) {
        DOM.popCopyBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (AnnotationManager.activeSelectedText) {
                navigator.clipboard.writeText(`"${AnnotationManager.activeSelectedText}" (Libre-Library)`).then(() => {
                    showToast("Quote copied to clipboard!");
                    dismissAllPopovers();
                }).catch(() => {
                    showToast("Clipboard access denied.");
                });
            }
        });
    }

    if (DOM.popAskTarsBtn) {
        DOM.popAskTarsBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            TarsExplainer.trigger(AnnotationManager.activeSelectedText);
        });
    }

    if (DOM.aiCardClose) {
        DOM.aiCardClose.addEventListener('click', (e) => {
            e.stopPropagation();
            if (DOM.aiExplainerCard) DOM.aiExplainerCard.style.display = 'none';
        });
    }

    if (DOM.aiAttachNoteBtn) {
        DOM.aiAttachNoteBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (TarsExplainer.lastExplainedText && TarsExplainer.lastExplanationResult) {
                await AnnotationManager.createAnnotation("blue", "TARS AI: " + TarsExplainer.lastExplanationResult);
                dismissAllPopovers();
            }
        });
    }

    if (DOM.aiOpenChatBtn) {
        DOM.aiOpenChatBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const prompt = `Can you explain this excerpt in detail: "${TarsExplainer.lastExplainedText}"`;
            try {
                window.parent.postMessage({ type: 'OPEN_TARS_CHAT', message: prompt }, '*');
            } catch(e) {}
            window.open(`/chat?prompt=${encodeURIComponent(prompt)}`, '_blank');
        });
    }

    document.querySelectorAll('#highlight-popover .hl-swatch').forEach(swatch => {
        swatch.addEventListener('click', (e) => {
            e.stopPropagation();
            const newColor = swatch.getAttribute('data-update-color');
            if (AnnotationManager.activeHighlight && newColor) {
                AnnotationManager.updateAnnotation(AnnotationManager.activeHighlight.id, { color: newColor });
            }
        });
    });

    if (DOM.hlSaveNoteBtn) {
        DOM.hlSaveNoteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const note = DOM.hlEditNoteText ? DOM.hlEditNoteText.value.trim() : "";
            if (AnnotationManager.activeHighlight) {
                AnnotationManager.updateAnnotation(AnnotationManager.activeHighlight.id, { note: note });
            }
        });
    }

    if (DOM.hlDeleteBtn) {
        DOM.hlDeleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (AnnotationManager.activeHighlight) {
                AnnotationManager.deleteAnnotation(AnnotationManager.activeHighlight.id);
            }
        });
    }

    if (DOM.drawerToggleBtn) {
        DOM.drawerToggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            AnnotationManager.toggleDrawer();
        });
    }

    if (DOM.drawerCloseBtn) {
        DOM.drawerCloseBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (DOM.annotationsDrawer) DOM.annotationsDrawer.classList.remove('open');
        });
    }

    document.querySelectorAll('.drawer-filter-bar .filter-pill').forEach(pill => {
        pill.addEventListener('click', () => {
            document.querySelectorAll('.drawer-filter-bar .filter-pill').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            AnnotationManager.currentFilter = pill.getAttribute('data-filter') || 'all';
            AnnotationManager.updateDrawerUI();
        });
    });

    if (DOM.drawerSearch) {
        DOM.drawerSearch.addEventListener('input', (e) => {
            AnnotationManager.currentSearch = e.target.value.trim();
            AnnotationManager.updateDrawerUI();
        });
    }

    if (DOM.drawerExportBtn) {
        DOM.drawerExportBtn.addEventListener('click', () => {
            window.location.href = `/api/annotations/${encodeURIComponent(bookId)}/export?user_id=${encodeURIComponent(userId)}`;
            showToast("Study guide download initiated!");
        });
    }

    document.addEventListener('click', (e) => {
        if (DOM.selectionPopover && !DOM.selectionPopover.contains(e.target) && e.target !== DOM.selectionPopover) {
            DOM.selectionPopover.style.display = 'none';
        }
        if (DOM.highlightPopover && !DOM.highlightPopover.contains(e.target) && e.target !== DOM.highlightPopover) {
            DOM.highlightPopover.style.display = 'none';
        }
        if (DOM.aiExplainerCard && !DOM.aiExplainerCard.contains(e.target) && e.target !== DOM.aiExplainerCard) {
            DOM.aiExplainerCard.style.display = 'none';
        }
    });

    // Parent Window Commands
    window.addEventListener('message', function(event) {
        if (!event.data || !rendition) return;
        if (event.data.type === 'READER_NAVIGATE') {
            if (event.data.action === 'next') rendition.next();
            else if (event.data.action === 'prev') rendition.prev();
        } else if (event.data.type === 'SET_THEME' && event.data.theme) {
            ThemeManager.applyTheme(event.data.theme, true);
        }
    });

    // -------------------------------------------------------------------------
    // 8. EPUB.JS LIFECYCLE INITIALIZATION
    // -------------------------------------------------------------------------
    ThemeManager.applyTheme(ThemeManager.currentTheme, false);

    try {
        book = ePub(bookUrl);
        rendition = book.renderTo("viewer", {
            width: "100%",
            height: "100%",
            flow: "paginated",
            manager: "default"
        });

        ThemeManager.registerRenditionThemes();

        if (initialCfi) {
            rendition.display(initialCfi).catch(() => rendition.display());
        } else {
            rendition.display();
        }

        AnnotationManager.fetchAnnotations();

        // Selection Listener
        rendition.on('selected', function(cfiRange, contents) {
            AnnotationManager.activeCfiRange = cfiRange;
            try {
                const iframe = document.querySelector('#viewer iframe');
                const iframeRect = iframe ? iframe.getBoundingClientRect() : { left: 0, top: 0 };
                const sel = contents.window.getSelection();
                AnnotationManager.activeSelectedText = sel ? sel.toString().trim() : '';
                if (!AnnotationManager.activeSelectedText) return;

                let rangeRect = null;
                if (sel && sel.rangeCount > 0) rangeRect = sel.getRangeAt(0).getBoundingClientRect();

                const popWidth = 240;
                const x = Math.max(12, Math.min(window.innerWidth - popWidth - 12, iframeRect.left + (rangeRect ? rangeRect.left + rangeRect.width / 2 - popWidth / 2 : 100)));
                const y = Math.max(60, iframeRect.top + (rangeRect ? rangeRect.top - 48 : 100));

                dismissAllPopovers();
                if (DOM.selectionPopover) {
                    DOM.selectionPopover.style.left = `${x}px`;
                    DOM.selectionPopover.style.top = `${y}px`;
                    DOM.selectionPopover.style.display = 'flex';
                    if (DOM.popNoteContainer) DOM.popNoteContainer.style.display = 'none';
                    if (DOM.popNoteText) DOM.popNoteText.value = '';
                }
            } catch (err) {}
        });

        // Location coordinates generation
        book.ready.then(() => book.locations.generate(1000)).then(() => {
            if (isRestoring && !initialCfi && initialPage > 1 && totalPages > 1) {
                const fraction = Math.max(0, Math.min(1, (initialPage - 1) / (totalPages - 1)));
                const cfi = book.locations.cfiFromPercentage(fraction);
                if (cfi) rendition.display(cfi);
            }
        }).catch(() => {});

        // Relocation Listener
        rendition.on('relocated', function(location) {
            if (!location || !location.start) return;
            const curCfi = location.start.cfi;

            let pct = 0;
            if (book.locations && book.locations.length()) {
                pct = book.locations.percentageFromCfi(curCfi);
            } else if (book.spine && book.spine.length) {
                pct = (location.start.index || 0) / Math.max(1, book.spine.length);
            }
            pct = Math.max(0, Math.min(1, pct));

            const curPage = Math.max(1, Math.min(totalPages, Math.round(pct * (totalPages - 1)) + 1));
            const pctInt = Math.round(pct * 100);

            ProgressSync.updateHud(curPage, totalPages, pctInt, curCfi);

            if (isRestoring) {
                isRestoring = false;
                lastNotifiedCfi = curCfi;
                lastNotifiedPage = curPage;
                return;
            }

            if (curCfi === lastNotifiedCfi && curPage === lastNotifiedPage) return;

            lastNotifiedCfi = curCfi;
            lastNotifiedPage = curPage;

            ProgressSync.scheduleSave({
                book_id: bookId,
                user_id: userId,
                current_page: curPage,
                total_pages: totalPages,
                progress_percent: Math.round(pct * 1000) / 10,
                cfi: curCfi,
                status: (curPage >= totalPages && totalPages > 1) ? 'completed' : 'reading',
                client_timestamp: Date.now() / 1000
            });
        });

        // Button Listeners
        if (DOM.nextBtn) DOM.nextBtn.addEventListener("click", () => rendition.next());
        if (DOM.prevBtn) DOM.prevBtn.addEventListener("click", () => rendition.prev());

        // Rendition hooks
        rendition.hooks.content.register(function(contents) {
            contents.document.addEventListener("keydown", handleKeyDown);
            contents.document.addEventListener("click", () => dismissAllPopovers());
        });

    } catch (e) {
        console.error("[EPUB Engine] Initialization error:", e);
        if (DOM.errorMsg) {
            DOM.errorMsg.style.display = 'block';
            DOM.errorMsg.innerText = "Fatal Reader Error: " + e.message;
        }
    }
})();