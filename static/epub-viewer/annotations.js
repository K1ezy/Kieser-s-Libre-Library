/**
 * Libre EPUB Reader - Annotations & Highlights Manager
 * Manages 4-color highlights, sticky notes, study drawer, search, and Markdown export.
 */
(function() {
    'use strict';

    function escapeHtml(text) {
        if (!text) return '';
        return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    const AnnotationManager = {
        annotations: [],
        activeCfiRange: null,
        activeSelectedText: '',
        activePopoverColor: 'yellow',
        activeHighlight: null,
        currentFilter: 'all',
        currentSearch: '',
        context: null, // { bookId, userId, getRendition, getPageNum, showToast, dismissAllPopovers }

        getColorHex(color) {
            const map = { green: '#bbf7d0', blue: '#bfdbfe', pink: '#fbcfe8' };
            return map[(color || 'yellow').toLowerCase()] || '#fef08a';
        },

        renderSingleHighlight(ann) {
            const rendition = this.context.getRendition();
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
            const { bookId, userId } = this.context;
            if (!bookId) return;
            try {
                const res = await fetch(`/api/annotations/${encodeURIComponent(bookId)}?user_id=${encodeURIComponent(userId)}`);
                const data = await res.json();
                if (res.ok && data.annotations) {
                    this.annotations = data.annotations;
                    this.updateDrawerUI();
                    this.annotations.forEach(ann => this.renderSingleHighlight(ann));
                }
            } catch(e) {
                console.error("[EPUB Annotations] Fetch error:", e);
            }
        },

        async createAnnotation(color, note = "") {
            const { bookId, userId, getPageNum, showToast, dismissAllPopovers } = this.context;
            if (!this.activeSelectedText || !this.activeCfiRange) return;

            const payload = {
                book_id: bookId,
                user_id: userId,
                selected_text: this.activeSelectedText,
                color: color || "yellow",
                cfi_range: this.activeCfiRange,
                page_number: getPageNum() || 1,
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
            const { dismissAllPopovers } = this.context;

            const iframe = document.querySelector('#viewer iframe');
            const iframeRect = iframe ? iframe.getBoundingClientRect() : { left: 0, top: 0 };
            const clientX = e.clientX !== undefined ? e.clientX : 150;
            const clientY = e.clientY !== undefined ? e.clientY : 150;

            const x = Math.max(12, Math.min(window.innerWidth - 260, iframeRect.left + clientX - 100));
            const y = Math.max(60, iframeRect.top + clientY - 60);

            dismissAllPopovers();
            const popover = document.getElementById('highlight-popover');
            const noteText = document.getElementById('hl-edit-note-text');
            if (popover) {
                popover.style.left = `${x}px`;
                popover.style.top = `${y}px`;
                popover.style.display = 'flex';
                if (noteText) noteText.value = ann.note || '';
            }
        },

        async updateAnnotation(annId, updates) {
            const { showToast, dismissAllPopovers, getRendition } = this.context;
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
                        const rendition = getRendition();
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
            const { userId, showToast, dismissAllPopovers, getRendition } = this.context;
            if (!annId) return;
            try {
                const res = await fetch(`/api/annotations/${encodeURIComponent(annId)}?user_id=${encodeURIComponent(userId)}`, {
                    method: 'DELETE'
                });
                if (res.ok) {
                    const target = this.annotations.find(a => a.id === annId);
                    const rendition = getRendition();
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
            const badge = document.getElementById('annotations-badge');
            const count = document.getElementById('drawer-count');
            const cardsContainer = document.getElementById('drawer-cards');

            if (badge) {
                badge.innerText = this.annotations.length;
                badge.style.display = this.annotations.length > 0 ? 'inline-block' : 'none';
            }
            if (count) count.innerText = this.annotations.length;
            if (!cardsContainer) return;

            const filtered = this.annotations.filter(ann => {
                const matchColor = (this.currentFilter === 'all') || (ann.color === this.currentFilter);
                const query = this.currentSearch.toLowerCase();
                const matchSearch = !query ||
                    (ann.selected_text && ann.selected_text.toLowerCase().includes(query)) ||
                    (ann.note && ann.note.toLowerCase().includes(query));
                return matchColor && matchSearch;
            });

            if (filtered.length === 0) {
                cardsContainer.innerHTML = `
                    <div style="text-align: center; color: var(--text-controls); padding: 40px 16px; font-size: 13px;">
                        <span style="font-size: 28px; display: block; margin-bottom: 8px;">📖</span>
                        ${this.annotations.length === 0 ? 'No annotations yet.<br>Select any passage in the book to highlight or add study notes!' : 'No annotations match your filter.'}
                    </div>
                `;
                return;
            }

            cardsContainer.innerHTML = filtered.map(ann => {
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

            const rendition = this.context.getRendition();
            cardsContainer.querySelectorAll('.ann-card').forEach(card => {
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
            const drawer = document.getElementById('annotations-drawer');
            if (!drawer) return;
            const isOpen = drawer.classList.contains('open');
            drawer.classList.toggle('open', !isOpen);
            if (!isOpen) this.context.dismissAllPopovers();
        },

        init(ctx) {
            this.context = ctx;

            // Highlight Swatches
            document.querySelectorAll('#selection-popover .hl-swatch').forEach(swatch => {
                swatch.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const color = swatch.getAttribute('data-color') || 'yellow';
                    this.activePopoverColor = color;
                    this.createAnnotation(color, "");
                });
            });

            // Note Container Toggle & Save
            const popAddNote = document.getElementById('pop-add-note-btn');
            const noteContainer = document.getElementById('pop-note-container');
            const noteText = document.getElementById('pop-note-text');
            if (popAddNote && noteContainer) {
                popAddNote.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const isOpen = noteContainer.style.display === 'flex';
                    noteContainer.style.display = isOpen ? 'none' : 'flex';
                    if (!isOpen && noteText) noteText.focus();
                });
            }

            const popNoteSave = document.getElementById('pop-note-save');
            if (popNoteSave) {
                popNoteSave.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const note = noteText ? noteText.value.trim() : "";
                    this.createAnnotation(this.activePopoverColor || "yellow", note);
                });
            }

            // Copy Quote
            const popCopy = document.getElementById('pop-copy-btn');
            if (popCopy) {
                popCopy.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (this.activeSelectedText) {
                        navigator.clipboard.writeText(`"${this.activeSelectedText}" (Libre-Library)`).then(() => {
                            ctx.showToast("Quote copied to clipboard!");
                            ctx.dismissAllPopovers();
                        }).catch(() => {
                            ctx.showToast("Clipboard access denied.");
                        });
                    }
                });
            }

            // Update Highlight Note & Color
            document.querySelectorAll('#highlight-popover .hl-swatch').forEach(swatch => {
                swatch.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const newColor = swatch.getAttribute('data-update-color');
                    if (this.activeHighlight && newColor) {
                        this.updateAnnotation(this.activeHighlight.id, { color: newColor });
                    }
                });
            });

            const hlSaveNote = document.getElementById('hl-save-note-btn');
            const hlEditNoteText = document.getElementById('hl-edit-note-text');
            if (hlSaveNote) {
                hlSaveNote.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const note = hlEditNoteText ? hlEditNoteText.value.trim() : "";
                    if (this.activeHighlight) this.updateAnnotation(this.activeHighlight.id, { note });
                });
            }

            const hlDeleteBtn = document.getElementById('hl-delete-btn');
            if (hlDeleteBtn) {
                hlDeleteBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (this.activeHighlight) this.deleteAnnotation(this.activeHighlight.id);
                });
            }

            // Drawer Toggles & Search
            const drawerToggle = document.getElementById('annotations-drawer-toggle');
            if (drawerToggle) drawerToggle.addEventListener('click', (e) => { e.stopPropagation(); this.toggleDrawer(); });

            const drawerClose = document.getElementById('drawer-close-btn');
            const drawer = document.getElementById('annotations-drawer');
            if (drawerClose && drawer) drawerClose.addEventListener('click', (e) => { e.stopPropagation(); drawer.classList.remove('open'); });

            document.querySelectorAll('.drawer-filter-bar .filter-pill').forEach(pill => {
                pill.addEventListener('click', () => {
                    document.querySelectorAll('.drawer-filter-bar .filter-pill').forEach(p => p.classList.remove('active'));
                    pill.classList.add('active');
                    this.currentFilter = pill.getAttribute('data-filter') || 'all';
                    this.updateDrawerUI();
                });
            });

            const searchInput = document.getElementById('drawer-search');
            if (searchInput) {
                searchInput.addEventListener('input', (e) => {
                    this.currentSearch = e.target.value.trim();
                    this.updateDrawerUI();
                });
            }

            const exportBtn = document.getElementById('drawer-export-btn');
            if (exportBtn) {
                exportBtn.addEventListener('click', () => {
                    window.location.href = `/api/annotations/${encodeURIComponent(ctx.bookId)}/export?user_id=${encodeURIComponent(ctx.userId)}`;
                    ctx.showToast("Study guide download initiated!");
                });
            }
        }
    };

    window.AnnotationManager = AnnotationManager;
})();
