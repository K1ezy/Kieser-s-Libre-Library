/**
 * Libre Library - Universal Keyboard Accessibility & Navigation Engine
 * 
 * Provides 100% keyboard control across the application:
 * - Fluid smooth scrolling (j/k, d/u, Space/Shift+Space, gg/G, Arrows, PageUp/PageDown, Home/End)
 * - Intelligent scroll container targeting (scrolls active scrollarea, dialog, or window)
 * - Vim-style chord navigation (g h -> Home, g b -> Books, g c -> Chat, etc.)
 * - Instant search focus (/ or Ctrl+K / Cmd+K)
 * - Quick drawer toggle (m) and AI chat toggle (t)
 * - Keyboard Shortcuts Cheat Sheet modal (? or Shift+/)
 * - Escape to blur inputs or dismiss open dialogs
 */

(function () {
    'use strict';

    // Prevent duplicate initialization across NiceGUI re-renders
    if (window.__LIBRE_KEYBOARD_NAV_INITIALIZED__) return;
    window.__LIBRE_KEYBOARD_NAV_INITIALIZED__ = true;

    let lastGPressTime = 0;
    let chordTimer = null;
    let hoveredElement = null;

    // Track hovered element for context-aware scrolling
    document.addEventListener('mouseover', function (e) {
        hoveredElement = e.target;
    }, { passive: true });

    /**
     * Determines whether an element is an editable input or form control.
     */
    function isEditableElement(el) {
        if (!el) return false;
        const tag = (el.tagName || '').toUpperCase();
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
        if (el.isContentEditable) return true;
        if (el.getAttribute && el.getAttribute('role') === 'textbox') return true;
        if (el.closest && (el.closest('.q-field__native') || el.closest('.q-field__input') || el.closest('.q-field'))) return true;
        return false;
    }

    /**
     * Detects the best scrollable container (modal dialog, scroll area, or window).
     */
    function getActiveScrollContainer() {
        // 1. If an active open dialog exists, scroll within the dialog
        const activeDialog = document.querySelector('.q-dialog:not([style*="display: none"]):not(.q-dialog--hidden)');
        if (activeDialog) {
            const card = activeDialog.querySelector('.q-card, .q-dialog__inner, [class*="overflow-y-auto"]');
            if (card && card.scrollHeight > card.clientHeight) return card;
        }

        // 2. If hovering over or focused inside a scrollable container
        let target = hoveredElement || document.activeElement;
        while (target && target !== document.body && target !== document.documentElement) {
            if (target.scrollHeight > target.clientHeight + 5) {
                const style = window.getComputedStyle(target);
                const overflowY = style.overflowY || '';
                if (overflowY === 'auto' || overflowY === 'scroll') {
                    return target;
                }
            }
            target = target.parentElement;
        }

        // 3. Reader interface or scroll area
        const readerScroll = document.querySelector('.q-scrollarea__container, main [class*="overflow-y"]');
        if (readerScroll && readerScroll.scrollHeight > readerScroll.clientHeight) {
            return readerScroll;
        }

        // 4. Default to standard window/document scrolling
        return window;
    }

    /**
     * Smoothly scrolls the active container by delta pixels.
     */
    function scrollContainerBy(delta) {
        const container = getActiveScrollContainer();
        if (container === window || !container || container === document.documentElement || container === document.body) {
            window.scrollBy({ top: delta, left: 0, behavior: 'smooth' });
        } else {
            container.scrollBy({ top: delta, left: 0, behavior: 'smooth' });
        }
    }

    /**
     * Smoothly scrolls to the top or bottom.
     */
    function scrollToPosition(toTop) {
        const container = getActiveScrollContainer();
        if (container === window || !container || container === document.documentElement || container === document.body) {
            const top = toTop ? 0 : Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
            window.scrollTo({ top: top, left: 0, behavior: 'smooth' });
        } else {
            const top = toTop ? 0 : container.scrollHeight;
            container.scrollTo({ top: top, left: 0, behavior: 'smooth' });
        }
    }

    /**
     * Renders or toggles the Visual Chord Feedback Pill.
     */
    function showChordIndicator() {
        let pill = document.getElementById('libre-chord-indicator');
        if (!pill) {
            pill = document.createElement('div');
            pill.id = 'libre-chord-indicator';
            pill.className = 'libre-chord-indicator';
            pill.innerHTML = `
                <div class="chord-badge">g</div>
                <div class="chord-text">Press <b>h</b> (Home) · <b>b</b> (Books) · <b>c</b> (Chat) · <b>p</b> (Planner) · <b>s</b> (Summarize) · <b>u</b> (Upload) · <b>g</b> (Top)</div>
            `;
            document.body.appendChild(pill);
        }
        pill.classList.add('visible');
        clearTimeout(chordTimer);
        chordTimer = setTimeout(() => {
            hideChordIndicator();
            lastGPressTime = 0;
        }, 1200);
    }

    function hideChordIndicator() {
        const pill = document.getElementById('libre-chord-indicator');
        if (pill) pill.classList.remove('visible');
    }

    /**
     * Focuses the primary search input on the current page or header.
     */
    function focusSearchInput() {
        const selectors = [
            '#global-header-search input',
            '#global-search-input input',
            'input[placeholder*="Search" i]',
            '.q-field input[type="search"]',
            '.q-field input[type="text"]'
        ];
        for (const selector of selectors) {
            const input = document.querySelector(selector);
            if (input && input.offsetParent !== null) { // visible
                input.focus();
                input.select();
                return true;
            }
        }
        // If no search input is found on the current page, navigate to /books
        window.location.href = '/books';
        return true;
    }

    /**
     * Creates and toggles the Keyboard Shortcuts Modal Dialog.
     */
    function toggleHelpModal() {
        let modal = document.getElementById('libre-shortcuts-modal');
        if (modal) {
            if (modal.classList.contains('visible')) {
                modal.classList.remove('visible');
            } else {
                modal.classList.add('visible');
            }
            return;
        }

        modal = document.createElement('div');
        modal.id = 'libre-shortcuts-modal';
        modal.className = 'libre-shortcuts-modal';
        modal.innerHTML = `
            <div class="modal-backdrop" onclick="document.getElementById('libre-shortcuts-modal').classList.remove('visible')"></div>
            <div class="modal-card">
                <div class="modal-header">
                    <div class="modal-title-group">
                        <div class="modal-icon">⌨️</div>
                        <div>
                            <h3 class="modal-title">Keyboard Shortcuts & Accessibility</h3>
                            <p class="modal-subtitle">Full hands-on keyboard control for Libre Library</p>
                        </div>
                    </div>
                    <button class="modal-close-btn" onclick="document.getElementById('libre-shortcuts-modal').classList.remove('visible')" aria-label="Close">✕</button>
                </div>
                
                <div class="modal-body">
                    <!-- Column 1: Scrolling & Reading -->
                    <div class="shortcut-group">
                        <div class="group-title">📜 Scrolling & View Control</div>
                        <div class="shortcut-row">
                            <span class="shortcut-desc">Scroll Down</span>
                            <div class="key-combo"><kbd>j</kbd> <span>or</span> <kbd>↓</kbd></div>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-desc">Scroll Up</span>
                            <div class="key-combo"><kbd>k</kbd> <span>or</span> <kbd>↑</kbd></div>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-desc">Half Page Down</span>
                            <div class="key-combo"><kbd>d</kbd> <span>or</span> <kbd>PgDn</kbd></div>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-desc">Half Page Up</span>
                            <div class="key-combo"><kbd>u</kbd> <span>or</span> <kbd>PgUp</kbd></div>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-desc">Page Down / Up</span>
                            <div class="key-combo"><kbd>Space</kbd> / <kbd>Shift</kbd>+<kbd>Space</kbd></div>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-desc">Jump to Top</span>
                            <div class="key-combo"><kbd>g</kbd> <kbd>g</kbd> <span>or</span> <kbd>Home</kbd></div>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-desc">Jump to Bottom</span>
                            <div class="key-combo"><kbd>G</kbd> <span>or</span> <kbd>End</kbd></div>
                        </div>
                    </div>

                    <!-- Column 2: Navigation & Quick Actions -->
                    <div class="shortcut-group">
                        <div class="group-title">🧭 Quick Navigation (Go-to)</div>
                        <div class="shortcut-row">
                            <span class="shortcut-desc">Go to Home</span>
                            <div class="key-combo"><kbd>g</kbd> <kbd>h</kbd></div>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-desc">Go to Library Books</span>
                            <div class="key-combo"><kbd>g</kbd> <kbd>b</kbd></div>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-desc">Go to TARS AI Chat</span>
                            <div class="key-combo"><kbd>g</kbd> <kbd>c</kbd></div>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-desc">Go to Study Planner</span>
                            <div class="key-combo"><kbd>g</kbd> <kbd>p</kbd></div>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-desc">Go to AI Summarizer</span>
                            <div class="key-combo"><kbd>g</kbd> <kbd>s</kbd></div>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-desc">Go to Upload Material</span>
                            <div class="key-combo"><kbd>g</kbd> <kbd>u</kbd></div>
                        </div>
                        <div class="shortcut-row">
                            <span class="shortcut-desc">Go to Admin Console</span>
                            <div class="key-combo"><kbd>g</kbd> <kbd>a</kbd></div>
                        </div>
                    </div>

                    <!-- Column 3: Global Actions -->
                    <div class="shortcut-group full-width">
                        <div class="group-title">⚡ Global Commands & Modals</div>
                        <div class="grid-shortcuts">
                            <div class="shortcut-row">
                                <span class="shortcut-desc">Focus Search Bar</span>
                                <div class="key-combo"><kbd>/</kbd> <span>or</span> <kbd>Ctrl</kbd>+<kbd>K</kbd></div>
                            </div>
                            <div class="shortcut-row">
                                <span class="shortcut-desc">Close / Unfocus Input</span>
                                <div class="key-combo"><kbd>Esc</kbd></div>
                            </div>
                            <div class="shortcut-row">
                                <span class="shortcut-desc">Toggle AI Quick Chat</span>
                                <div class="key-combo"><kbd>t</kbd></div>
                            </div>
                            <div class="shortcut-row">
                                <span class="shortcut-desc">Toggle Left Drawer</span>
                                <div class="key-combo"><kbd>m</kbd></div>
                            </div>
                            <div class="shortcut-row">
                                <span class="shortcut-desc">Toggle Fullscreen (Reader)</span>
                                <div class="key-combo"><kbd>f</kbd></div>
                            </div>
                            <div class="shortcut-row">
                                <span class="shortcut-desc">Shortcuts Cheat Sheet</span>
                                <div class="key-combo"><kbd>?</kbd></div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="modal-footer">
                    <span class="footer-hint">💡 Press <b>Esc</b> to close this guide or resume reading.</span>
                    <button class="footer-btn" onclick="document.getElementById('libre-shortcuts-modal').classList.remove('visible')">Got it</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        requestAnimationFrame(() => modal.classList.add('visible'));
    }

    /**
     * Master Keyboard Event Listener.
     */
    window.addEventListener('keydown', function (e) {
        const target = e.target;
        const inInput = isEditableElement(target);

        // 1. ESCAPE: Always handled, regardless of active element
        if (e.key === 'Escape') {
            // Dismiss Shortcuts Modal if open
            const helpModal = document.getElementById('libre-shortcuts-modal');
            if (helpModal && helpModal.classList.contains('visible')) {
                helpModal.classList.remove('visible');
                e.preventDefault();
                return;
            }
            // Dismiss Chord Pill if open
            hideChordIndicator();
            lastGPressTime = 0;

            // If active element is an input, blur it so keyboard scrolling immediately resumes
            if (inInput) {
                target.blur();
                e.preventDefault();
                return;
            }

            // Close any open Quasar dialogs
            const closeBtn = document.querySelector('.q-dialog button[aria-label="Close"], .q-dialog .q-btn:has(i)');
            if (closeBtn) {
                closeBtn.click();
                e.preventDefault();
                return;
            }
            return;
        }

        // 2. SEARCH SHORTCUT (/ or Ctrl+K / Cmd+K)
        if ((e.key === '/' && !inInput) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k')) {
            e.preventDefault();
            focusSearchInput();
            return;
        }

        // 3. HELP MODAL SHORTCUT (? or Shift+/)
        if (e.key === '?' && !inInput) {
            e.preventDefault();
            toggleHelpModal();
            return;
        }

        // IF USER IS TYPING IN ANY INPUT OR TEXTAREA, DO NOT INTERCEPT ANY OTHER KEYS
        if (inInput) {
            return;
        }

        // Check if modifiers are pressed (Ctrl, Alt, Meta) - don't intercept standard browser shortcuts
        if (e.ctrlKey || e.metaKey) {
            return;
        }

        const now = Date.now();
        const key = e.key;

        // 4. CHORDED NAVIGATION (g + [key])
        if (lastGPressTime && (now - lastGPressTime < 1100)) {
            hideChordIndicator();
            lastGPressTime = 0;

            if (key === 'g') {
                e.preventDefault();
                scrollToPosition(true);
                return;
            } else if (key === 'h') {
                e.preventDefault();
                window.location.href = '/';
                return;
            } else if (key === 'b') {
                e.preventDefault();
                window.location.href = '/books';
                return;
            } else if (key === 'c') {
                e.preventDefault();
                window.location.href = '/chat';
                return;
            } else if (key === 'p') {
                e.preventDefault();
                window.location.href = '/planner';
                return;
            } else if (key === 's') {
                e.preventDefault();
                window.location.href = '/summarizer';
                return;
            } else if (key === 'u') {
                e.preventDefault();
                window.location.href = '/upload';
                return;
            } else if (key === 'a') {
                e.preventDefault();
                window.location.href = '/admin';
                return;
            } else if (key === 'r') {
                e.preventDefault();
                window.location.href = '/profile';
                return;
            }
        }

        // If 'g' is pressed, activate chord mode
        if (key === 'g') {
            lastGPressTime = now;
            showChordIndicator();
            return;
        }

        // 5. FLUID KEYBOARD SCROLLING
        const scrollStep = 120;
        const pageStep = Math.round(window.innerHeight * 0.65);
        const fullPageStep = Math.round(window.innerHeight * 0.85);

        // Step down
        if (key === 'j' || key === 'ArrowDown') {
            e.preventDefault();
            scrollContainerBy(scrollStep);
            return;
        }

        // Step up
        if (key === 'k' || key === 'ArrowUp') {
            e.preventDefault();
            scrollContainerBy(-scrollStep);
            return;
        }

        // Half page down
        if (key === 'd' || key === 'PageDown') {
            e.preventDefault();
            scrollContainerBy(pageStep);
            return;
        }

        // Half page up
        if (key === 'u' || key === 'PageUp') {
            e.preventDefault();
            scrollContainerBy(-pageStep);
            return;
        }

        // Full page scroll (Space / Shift+Space)
        if (key === ' ' || key === 'Spacebar') {
            e.preventDefault();
            scrollContainerBy(e.shiftKey ? -fullPageStep : fullPageStep);
            return;
        }

        // Jump to Bottom (G or End)
        if (key === 'G' || key === 'End') {
            e.preventDefault();
            scrollToPosition(false);
            return;
        }

        // Jump to Top (Home)
        if (key === 'Home') {
            e.preventDefault();
            scrollToPosition(true);
            return;
        }

        // 6. QUICK TOGGLES
        // 't': Toggle TARS Floating Chat
        if (key === 't') {
            const chatFab = document.querySelector('.q-fab, button[aria-label*="chat" i], button:has(i:contains("smart_toy")), [data-chat-toggle]');
            if (chatFab) {
                e.preventDefault();
                chatFab.click();
                return;
            }
        }

        // 'm': Toggle Sidebar Drawer
        if (key === 'm') {
            const menuBtn = document.querySelector('header button:has(i:contains("menu")), button[aria-label*="menu" i]');
            if (menuBtn) {
                e.preventDefault();
                menuBtn.click();
                return;
            }
        }

        // 'f': Toggle Fullscreen (useful in Reader)
        if (key === 'f') {
            if (window.location.pathname.startsWith('/read/')) {
                e.preventDefault();
                if (document.fullscreenElement) {
                    document.exitFullscreen();
                } else {
                    document.documentElement.requestFullscreen();
                }
                return;
            }
        }
    }, { capture: true });

    // Expose global API for manual triggers or inspection
    window.LibreAccessibility = {
        showHelp: toggleHelpModal,
        focusSearch: focusSearchInput,
        scrollBy: scrollContainerBy,
        scrollTo: scrollToPosition
    };

    console.log("⚡ Libre Library Keyboard Accessibility Engine active. Press '?' for shortcuts.");
})();
