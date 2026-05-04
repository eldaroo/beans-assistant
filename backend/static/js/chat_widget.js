/*
 * Timonel chat: Alpine factory.
 *
 * The chat shell lives inline in `tenant_detail.html` (tenant mode) and in
 * `onboarding.html` (onboarding mode). This file exports a single Alpine
 * factory, `beansChat(...)`, that owns: messages, dock mode, suggested
 * prompts, focus trap, and the structured-handoff event emitter.
 *
 * Factory signature (back-compat):
 *   beansChat('+5491100000001')                       // legacy: tenant mode, phone string
 *   beansChat({ phone: '+5491100000001' })            // tenant mode, object form
 *   beansChat({ mode: 'onboarding',
 *               endpoint: '/api/onboarding/web' })    // onboarding mode
 *
 * Mode semantics:
 *   tenant      (default) — pin toggle visible, localStorage persists dock,
 *                            emits beans:navigate + beans:refresh, endpoint
 *                            defaults to /api/tenants/{phone}/chat.
 *   onboarding             — pin toggle hidden (always pinned), localStorage
 *                            untouched (pending session is ephemeral), no
 *                            beans:navigate, no beans:refresh, endpoint comes
 *                            from config (e.g. /api/onboarding/web).
 *
 * Both modes share: state machine, suggested-prompts chips (different copy
 * per mode), focus trap, bubble shapes, streaming-cursor, agent-pulse on
 * the avatar.
 *
 * Contract with the dashboard (per ADR-001, tenant mode only):
 *   - Outgoing: `beans:navigate` on window with detail { tab, filter?, sort? }.
 *   - Incoming: `beans:open`     on window with detail { prompt? }.
 *
 * State machine (beans-ai-thinking-states):
 *   idle | thinking | tool_running | streaming | error
 *
 * Identity rules (beans-agent-identity-and-trust):
 *   - Avatar: header-only, never per message.
 *   - Passive voice for completed user actions ("Stock actualizado").
 *   - Active voice with "el timonel" only when accountability matters.
 */

(function () {
    'use strict';

    var DOCK_KEY_PREFIX = 'beans:dock:';
    // Pinned-by-default: the agent is the operating surface, not a help bubble.
    // Users who want it out of the way unpin once and the choice persists.
    var DEFAULT_DOCK = 'pinned';

    // ADR-002: grace period before window.location.href on completion redirect
    // and on session_expired. 1500ms lets the user read the final assistant
    // bubble before the page swaps under them.
    var REDIRECT_GRACE_MS = 1500;

    // Recovery copy table (beans-agent-identity-and-trust rule 3).
    // Infrastructure failures (llm/db/network/rate) speak in passive system
    // voice — no agent name. session_expired is also system-voice. The
    // server's `response` field is the source of truth when present; this
    // table is the fallback when the dispatcher could not produce text.
    var ERROR_FALLBACK_COPY = {
        llm_unavailable: 'Se cortó la conexión. Probá de nuevo en un momento.',
        session_expired: 'La sesión venció. Te llevo al login.',
        rate_limited:    'Esperá un momento y probá de nuevo.',
        db_error:        'Algo se rompió de mi lado. Probá en un minuto.'
    };

    // Tenant-mode chips (3 first-open / 2 post-reply). beans-suggested-prompts.
    var INITIAL_SUGGESTIONS = [
        '¿Qué productos están por agotarse?',
        'Mostrá las ventas de hoy',
        'Resumen del mes'
    ];
    var POST_REPLY_SUGGESTIONS = [
        'Detalle por producto',
        'Comparar con la semana pasada'
    ];

    // Onboarding-mode chips. M2 hardcodes both lists; M3 may swap them with
    // a /api/onboarding/first-action call. Voseo, sentence case, no period.
    var ONBOARDING_INITIAL_SUGGESTIONS = [
        'Configurar mi negocio',
        '¿Qué información necesitás de mí?',
        'Probar primero con datos de ejemplo'
    ];
    var ONBOARDING_POST_REPLY_SUGGESTIONS = [
        'Listo, seguimos',
        'Cambiar mi respuesta anterior'
    ];

    /**
     * Naive keyword router for v1. Returns a `beans:navigate` detail or null.
     * Replace with structured tool-call output once the agent emits typed
     * function calls (beans-tool-call-cards: future `metadata.tool_calls`).
     * Tenant mode only — onboarding does not navigate the dashboard.
     */
    function inferNavigation(replyText) {
        if (!replyText) return null;
        var t = replyText.toLowerCase();

        var hasStock = t.indexOf('stock') !== -1;
        var hasAgotar = t.indexOf('agotar') !== -1 || t.indexOf('agotá') !== -1;
        var hasMenos = t.indexOf('menos') !== -1 || t.indexOf('bajo') !== -1;
        if (hasStock && (hasAgotar || hasMenos)) {
            return { tab: 'stock', filter: { lowStock: true }, sort: 'stock:asc' };
        }

        var hasVentas = t.indexOf('venta') !== -1;
        var hasHoy = t.indexOf('hoy') !== -1 || t.indexOf('esta semana') !== -1;
        if (hasVentas && hasHoy) {
            return { tab: 'sales', filter: { range: 'today' } };
        }

        if (t.indexOf('gasto') !== -1) {
            return { tab: 'expenses' };
        }

        var hasProducto = t.indexOf('producto') !== -1;
        var hasNuevo = t.indexOf('nuevo') !== -1 || t.indexOf('agregar') !== -1 || t.indexOf('cargar') !== -1;
        if (hasProducto && hasNuevo) {
            return { tab: 'products' };
        }

        return null;
    }

    /**
     * Post-navigate system message. Passive voice: the user did it (asked),
     * the timonel was the conduit. beans-agent-identity-and-trust rule 3.
     */
    function navigationCopy(detail) {
        if (!detail) return null;
        switch (detail.tab) {
            case 'stock':
                return 'Stock abierto con los productos por debajo del umbral. Volvé al chat con el botón de arriba.';
            case 'sales':
                return 'Ventas abierto con el rango de hoy. Volvé al chat con el botón de arriba.';
            case 'expenses':
                return 'Gastos abierto. Volvé al chat con el botón de arriba.';
            case 'products':
                return 'Productos abierto. Volvé al chat con el botón de arriba.';
        }
        return null;
    }

    /**
     * Minimal markdown -> HTML for assistant bubbles. Bold, inline code, links
     * and line breaks. beans-streaming-ui rule 2 calls for an append-only
     * re-parse; for the sync v1 a single full parse is fine.
     */
    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function renderInline(text) {
        var s = escapeHtml(text);
        s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
        s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        s = s.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
        return s;
    }

    function renderMarkdown(text) {
        if (!text) return '';
        var paragraphs = String(text).split(/\n{2,}/);
        return paragraphs.map(function (p) {
            var lines = p.split(/\n/).map(renderInline).join('<br>');
            return '<p>' + lines + '</p>';
        }).join('');
    }

    function nextId() {
        return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
    }

    /**
     * Header subtitle copy table per beans-ai-thinking-states rule 2.
     * Returns the live trust signal that sits below the avatar's name.
     */
    function statusFor(state, activeTool) {
        if (state === 'tool_running') return (activeTool && activeTool.verb) ? activeTool.verb : 'Trabajando.';
        if (state === 'thinking')     return 'Pensando...';
        if (state === 'streaming')    return 'Respondiendo.';
        if (state === 'error')        return 'Algo salió mal. Probá de nuevo.';
        return 'Cuidando tu negocio.';
    }

    /**
     * Normalize the factory argument into an internal config object.
     * Accepts a string (legacy) or an object. Defaults preserve tenant
     * behavior so existing call sites keep working unchanged.
     */
    function buildConfig(arg) {
        var cfg = { mode: 'tenant', phone: '', endpoint: '', dockKey: '' };
        if (typeof arg === 'string') {
            cfg.phone = arg;
        } else if (arg && typeof arg === 'object') {
            if (typeof arg.mode === 'string')     cfg.mode = arg.mode;
            if (typeof arg.phone === 'string')    cfg.phone = arg.phone;
            if (typeof arg.endpoint === 'string') cfg.endpoint = arg.endpoint;
            if (typeof arg.dockKey === 'string')  cfg.dockKey = arg.dockKey;
        }
        if (!cfg.endpoint) {
            if (cfg.mode === 'onboarding') {
                cfg.endpoint = '/api/onboarding/web';
            } else {
                cfg.endpoint = '/api/tenants/' + encodeURIComponent(cfg.phone) + '/chat';
            }
        }
        if (!cfg.dockKey) {
            cfg.dockKey = DOCK_KEY_PREFIX + (cfg.phone || cfg.mode);
        }
        return cfg;
    }

    /**
     * The Alpine factory. Returns a fresh state object per `<div x-data>`.
     */
    window.beansChat = function (arg) {
        var cfg = buildConfig(arg);
        var isOnboarding = cfg.mode === 'onboarding';
        var initialSuggestions = isOnboarding
            ? ONBOARDING_INITIAL_SUGGESTIONS.slice()
            : INITIAL_SUGGESTIONS.slice();

        return {
            // --- public state ---
            isOpen: false,
            // Onboarding is structurally pinned (no toggle); tenant defaults to
            // pinned and persists user's choice.
            docked: isOnboarding ? 'pinned' : DEFAULT_DOCK,
            messages: [],                // { id, role, html, streaming?, toolCall?, cards? }
            input: '',

            // State machine. idle | thinking | tool_running | streaming | error
            state: 'idle',
            activeTool: null,

            // Header subtitle, derived. Updated whenever state/activeTool changes.
            status: statusFor('idle', null),

            // Chip rail. Initial = 3 (tenant) or 3 (onboarding); post-reply = 2;
            // cleared mid-flight. Different copy lists per mode.
            suggestions: initialSuggestions,

            // Mode flags exposed to the template so it can hide the pin button
            // and the floating launcher in onboarding mode.
            mode: cfg.mode,
            isOnboarding: isOnboarding,

            // Legacy shim: some templates still observe isThinking.
            get isThinking() { return this.state === 'thinking'; },

            // --- private ---
            _mode: cfg.mode,
            _endpoint: cfg.endpoint,
            _tenantPhone: cfg.phone,
            _dockKey: cfg.dockKey,
            _focusReturn: null,
            _trapHandler: null,
            _seedMessage: '',

            // --- lifecycle ---
            init: function () {
                if (!isOnboarding) {
                    // Tenant mode: read the persisted dock preference.
                    var saved = null;
                    try { saved = localStorage.getItem(this._dockKey); } catch (_) { /* no-op */ }
                    this.docked = (saved === 'pinned' || saved === 'floating') ? saved : DEFAULT_DOCK;

                    // Pinned = "I want the chat visible". Auto-open on every
                    // page load when the persisted (or default) preference is
                    // pinned. Floating opens only on launcher click.
                    if (this.docked === 'pinned') {
                        this.isOpen = true;
                    }
                } else {
                    // Onboarding mode: chat shell is structurally visible the
                    // moment it mounts (the spectacle controls when that is).
                    // No localStorage read — pending session is ephemeral.
                    this.isOpen = true;
                }

                if (this.$root && typeof this.$root === 'object') {
                    this.$root.beansDock = this.docked;
                    this.$root.beansOpen = this.isOpen;
                }

                var self = this;
                if (!isOnboarding) {
                    window.addEventListener('beans:open', function (e) {
                        self.open();
                        if (e && e.detail && e.detail.prompt) {
                            self.input = e.detail.prompt;
                        }
                        self.$nextTick(function () {
                            if (self.$refs.input) self.$refs.input.focus();
                        });
                    });
                }

                // Focus input on mount in onboarding mode (the spectacle hands
                // off into a focused thread).
                if (isOnboarding) {
                    this.$nextTick(function () {
                        if (self.$refs.input) self.$refs.input.focus();
                        self._installFocusTrap();
                    });
                }
            },

            // --- dock control ---
            open: function () {
                if (this.isOpen) return;
                this.isOpen = true;
                this._focusReturn = document.activeElement;
                this._syncRoot();
                var self = this;
                this.$nextTick(function () {
                    if (self.$refs.input) self.$refs.input.focus();
                    self._installFocusTrap();
                });
            },

            close: function () {
                // Onboarding never closes — the chat shell is the only surface.
                if (this.isOnboarding) return;
                if (!this.isOpen) return;
                this.isOpen = false;
                this._syncRoot();
                this._removeFocusTrap();
                if (this._focusReturn && typeof this._focusReturn.focus === 'function') {
                    try { this._focusReturn.focus(); } catch (_) { /* no-op */ }
                }
            },

            // Esc closes only the floating widget; pin is opinionated.
            // Onboarding has no close path; Esc is a no-op there.
            onEscape: function () {
                if (this.isOnboarding) return;
                if (this.docked === 'floating') this.close();
            },

            togglePin: function () {
                // Onboarding has no pin toggle (the button is hidden in
                // onboarding.html); this guard is belt-and-suspenders.
                if (this.isOnboarding) return;
                this.docked = (this.docked === 'pinned') ? 'floating' : 'pinned';
                try { localStorage.setItem(this._dockKey, this.docked); } catch (_) { /* no-op */ }
                this._syncRoot();
            },

            _syncRoot: function () {
                if (this.$root && typeof this.$root === 'object') {
                    this.$root.beansDock = this.docked;
                    this.$root.beansOpen = this.isOpen;
                }
            },

            _setState: function (next, activeTool) {
                this.state = next;
                this.activeTool = activeTool || null;
                this.status = statusFor(this.state, this.activeTool);
            },

            // --- focus trap (a11y) ---
            _focusables: function () {
                if (!this.$refs.shell) return [];
                var sel = 'a[href], area[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
                return Array.prototype.slice.call(this.$refs.shell.querySelectorAll(sel));
            },

            _installFocusTrap: function () {
                var self = this;
                this._trapHandler = function (e) {
                    if (e.key !== 'Tab' || !self.isOpen) return;
                    var nodes = self._focusables();
                    if (nodes.length === 0) return;
                    var first = nodes[0];
                    var last = nodes[nodes.length - 1];
                    if (e.shiftKey && document.activeElement === first) {
                        e.preventDefault();
                        last.focus();
                    } else if (!e.shiftKey && document.activeElement === last) {
                        e.preventDefault();
                        first.focus();
                    }
                };
                document.addEventListener('keydown', this._trapHandler, true);
            },

            _removeFocusTrap: function () {
                if (this._trapHandler) {
                    document.removeEventListener('keydown', this._trapHandler, true);
                    this._trapHandler = null;
                }
            },

            // --- bubble class helpers ---
            bubbleClass: function (m) {
                if (m.role === 'user') {
                    return 'self-end max-w-[85%] rounded-2xl rounded-br-md px-4 py-2.5 text-sm bg-[color:var(--color-brand)] text-[color:var(--color-brand-fg)]';
                }
                if (m.role === 'system') {
                    return 'self-center max-w-[90%] text-center text-xs text-[color:var(--color-text-muted)] py-1';
                }
                return 'self-start max-w-[85%] rounded-2xl rounded-bl-md px-4 py-2.5 text-sm bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text)] beans-md';
            },

            /**
             * Spectacle hand-off seam. The onboarding page captures the chip
             * text (or first input) and calls this *after* the chat factory
             * mounts. The text is rendered as a user bubble and POSTed in
             * the same call — the user does not click send a second time.
             *
             * Idempotent within a session: a second call after the thread
             * already has a user message is ignored.
             */
            seedFirstMessage: function (text) {
                var clean = (text || '').trim();
                if (!clean) return;
                if (this.messages.length > 0) return;
                this.send(clean);
            },

            // --- send + receive ---
            send: function (raw) {
                var text = (raw || '').trim();
                if (!text) return;
                if (this.state === 'thinking' || this.state === 'tool_running') return;

                this.messages.push({ id: nextId(), role: 'user', kind: 'text', html: escapeHtml(text) });
                this.input = '';
                this.suggestions = [];
                this._setState('thinking', null);
                this._scrollSoon();

                var self = this;
                fetch(this._endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text })
                }).then(function (res) {
                    if (!res.ok) throw new Error('http_' + res.status);
                    return res.json();
                }).then(function (data) {
                    var reply = (data && data.response) ? data.response : '';
                    var metadata = (data && data.metadata) || {};

                    // ADR-002 metadata shape:
                    //   tool_calls: [{ tool, status, label_es, payload }]
                    //   captured: { ... }
                    //   complete: bool
                    //   redirect_to: str | null
                    //   error: str | null
                    var toolCalls = metadata.tool_calls || [];
                    var errorCode = metadata.error || null;

                    // Inline-card scaffold (beans-structured-output rule 3) —
                    // separate from tool-call cards; backend may emit either.
                    var cards = metadata.cards || null;

                    // M3.4: each tool-call entry becomes its own card-shape
                    // message in the thread. Cards are receipts of what just
                    // happened; the assistant text is the LLM's commentary.
                    // Buffer cards first, then push the text bubble so cards
                    // render *before* the bubble in chronological order.
                    var bufferedToolCards = [];
                    if (toolCalls && toolCalls.length) {
                        for (var i = 0; i < toolCalls.length; i++) {
                            var entry = toolCalls[i] || {};
                            bufferedToolCards.push({
                                id: nextId(),
                                role: 'assistant',
                                kind: 'tool-card',
                                toolCall: {
                                    name: entry.tool || '',
                                    state: entry.status || 'success',
                                    label: entry.label_es || entry.tool || ''
                                }
                            });
                        }
                    }

                    // On infra/auth errors, prefer the server's `response`
                    // text when present (it's already user-facing per ADR-002),
                    // else fall back to the table.
                    var displayReply = reply;
                    if (errorCode && !displayReply) {
                        displayReply = ERROR_FALLBACK_COPY[errorCode] || '';
                    }

                    // Push tool cards first so they appear above the text bubble.
                    for (var j = 0; j < bufferedToolCards.length; j++) {
                        self.messages.push(bufferedToolCards[j]);
                    }

                    var assistantId = nextId();
                    var msg = {
                        id: assistantId,
                        role: 'assistant',
                        kind: 'text',
                        html: renderMarkdown(displayReply),
                        // Start true so the cursor is visible from the first
                        // render after push. The clear-after-600ms must mutate
                        // via the reactive array index, not via this raw
                        // reference — Alpine wraps the object once it lands in
                        // self.messages and direct mutations on the closure
                        // ref bypass the proxy, leaving the cursor visually
                        // stuck on past bubbles when later re-renders expose
                        // the stale state.
                        streaming: true
                    };
                    if (cards && cards.length) {
                        msg.cards = cards;
                    }
                    if (displayReply) {
                        self.messages.push(msg);
                    }

                    self._setState('streaming', null);
                    setTimeout(function () {
                        for (var k = 0; k < self.messages.length; k++) {
                            if (self.messages[k] && self.messages[k].id === assistantId) {
                                self.messages[k].streaming = false;
                                break;
                            }
                        }
                        if (self.state === 'streaming') self._setState('idle', null);
                        // On llm_unavailable / rate_limited / db_error the input
                        // stays enabled and the state machine resets to idle so
                        // the user can retry. session_expired is handled below
                        // (no further input — the redirect takes over).
                        if (errorCode && errorCode !== 'session_expired') {
                            self._setState('idle', null);
                        }
                        // Post-reply chip rail (different copy per mode). Only
                        // re-show chips on a clean turn (no error, not redirecting).
                        if (!errorCode && !metadata.complete && !self.input.trim()) {
                            self.suggestions = self.isOnboarding
                                ? ONBOARDING_POST_REPLY_SUGGESTIONS.slice()
                                : POST_REPLY_SUGGESTIONS.slice();
                        }
                    }, 600);

                    // Completion redirect (ADR-002). 1500ms grace lets the user
                    // read the final assistant message before the page swaps.
                    if (metadata.complete && metadata.redirect_to) {
                        setTimeout(function () {
                            window.location.href = metadata.redirect_to;
                        }, REDIRECT_GRACE_MS);
                    }

                    // session_expired: redirect to /login after the same grace.
                    // No further user input is accepted — disable the state
                    // machine path that re-enables idle.
                    if (errorCode === 'session_expired') {
                        setTimeout(function () {
                            window.location.href = '/login';
                        }, REDIRECT_GRACE_MS);
                    }

                    // Tenant-mode only: structured handoff and dashboard refresh.
                    // Onboarding mode never navigates or refreshes — there is
                    // no dashboard to drive yet. Skip on errors so we do not
                    // refresh a panel after a failed turn.
                    if (!self.isOnboarding && !errorCode) {
                        var nav = inferNavigation(reply);
                        if (nav) {
                            window.dispatchEvent(new CustomEvent('beans:navigate', { detail: nav }));
                            var copy = navigationCopy(nav);
                            if (copy) {
                                self.messages.push({ id: nextId(), role: 'system', kind: 'text', html: escapeHtml(copy) });
                            }
                        }
                        window.dispatchEvent(new CustomEvent('beans:refresh', {
                            detail: { tenantPhone: self._tenantPhone }
                        }));
                    }
                }).catch(function (err) {
                    console.error('[beansChat] send failed', err);
                    self._setState('error', null);
                    self.messages.push({
                        id: nextId(),
                        role: 'assistant',
                        kind: 'text',
                        html: escapeHtml('No pude procesar tu mensaje ahora. Probá de nuevo en un momento.')
                    });
                    setTimeout(function () { self._setState('idle', null); }, 1200);
                }).then(function () {
                    self._scrollSoon();
                });
            },

            _scrollSoon: function () {
                var self = this;
                this.$nextTick(function () {
                    if (self.$refs.thread) {
                        self.$refs.thread.scrollTop = self.$refs.thread.scrollHeight;
                    }
                });
            }
        };
    };
})();
