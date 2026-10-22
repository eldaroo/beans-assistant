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
    // Infrastructure failures speak in passive system voice. The server's
    // `response` field is the source of truth when present; this table is
    // the safety net when the dispatcher could not produce text.
    //
    // Spec 001 (Timonel M1) extends the table with five Timonel error
    // classes that the safe_node wrapper emits on the backend:
    //   unknown_product, missing_field, ambiguous_input, network,
    //   llm_unavailable.
    // The legacy infra/auth codes (session_expired, rate_limited, db_error)
    // are preserved because the redirect logic and existing chat endpoints
    // still use them.
    var ERROR_FALLBACK_COPY = {
        // Timonel M1 error envelope codes (spec 001).
        unknown_product: 'No reconocí el producto que mencionaste. Repetímelo si querés, o decime el nombre exacto.',
        missing_field:   'Me falta un dato para procesar esto.',
        ambiguous_input: 'Eso no me salió. Volvamos a lo de los productos.',
        network:         'Tuve un problema técnico. Probá de nuevo en un momento.',
        llm_unavailable: 'El asistente no pudo responder ahora. Probá de nuevo en un momento.',
        // Legacy infra/auth codes preserved from PR #36.
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

    // Onboarding-mode chips: intentionally empty (per Dario's UX feedback,
    // 2026-05-04). The dispatcher now drives the conversation deterministically
    // — every reply ends with a concrete next question, so chips would only
    // distract or, worse, send a message Timonel doesn't know how to handle.
    var ONBOARDING_INITIAL_SUGGESTIONS = [];
    var ONBOARDING_POST_REPLY_SUGGESTIONS = [];

    /**
     * Navigation source of truth.
     *
     * Until spec 001 (Timonel M1) the widget keyword-scanned the assistant
     * reply for words like "gasto" and "stock" via inferNavigation(), and
     * dispatched beans:navigate based on the scan. That path was the actual
     * cause of the Gastos UI flip on turn 2 of Dario's screenshot
     * (2026-05-15): the agent asked "¿qué querés agregar: una venta, un
     * gasto, ..." and the widget read "gasto" and opened the Gastos tab
     * before the agent had even picked an intent.
     *
     * The keyword scanner has been removed. Navigation now flows only from
     * the agent's structured `metadata.navigation` field, set when (and
     * only when) a tool actually executed. Mary's review names this as the
     * fix that holds; see specs/001-timonel-conversational-memory.
     *
     * Returns the validated navigation detail when the backend supplied
     * one, or null otherwise. Validation is shape-only (a tab string) —
     * it does not interpret reply text.
     */
    // The backend navigation cue names tabs in Spanish (Productos, Ventas,
    // Gastos, Stock — see write_agent._OPERATION_NAVIGATION), but the dashboard
    // tabs and navigationCopy() are keyed in lowercase English. Map between the
    // two here, at the single chokepoint, so the auto tab-switch and the
    // "Productos abierto" copy fire after a chat-created product. English keys
    // pass through unchanged, so this is idempotent.
    var TAB_ALIASES = {
        'productos': 'products',
        'ventas': 'sales',
        'gastos': 'expenses',
        'stock': 'stock',
    };

    function readNavigation(metadata) {
        if (!metadata || typeof metadata !== 'object') return null;
        var nav = metadata.navigation;
        if (!nav || typeof nav !== 'object') return null;
        if (typeof nav.tab !== 'string' || nav.tab.length === 0) return null;
        var key = nav.tab.toLowerCase();
        var tab = TAB_ALIASES[key] || key;
        return Object.assign({}, nav, { tab: tab });
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
        var cfg = { mode: 'tenant', phone: '', endpoint: '', dockKey: '', dock: '' };
        if (typeof arg === 'string') {
            cfg.phone = arg;
        } else if (arg && typeof arg === 'object') {
            if (typeof arg.mode === 'string')     cfg.mode = arg.mode;
            if (typeof arg.phone === 'string')    cfg.phone = arg.phone;
            if (typeof arg.endpoint === 'string') cfg.endpoint = arg.endpoint;
            if (typeof arg.dockKey === 'string')  cfg.dockKey = arg.dockKey;
            // Optional initial-dock override (spec 004 cc_base slot): 'floating'
            // lets a surface present Timonel as a launcher rather than the
            // pinned-open default, while still persisting the user's own choice.
            if (arg.dock === 'pinned' || arg.dock === 'floating') cfg.dock = arg.dock;
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
            messages: [],                // { id, role, html, streaming?, toolCall?, cards?, kind, proposed?, receipt? }
            undoToast: null,             // { op_token, label } — the loud Undo for an auto-posted write (spec 007 AC17)
            _undoTimer: null,
            input: '',

            // --- voice input (spec 006 T-012) ---
            // Whether this browser can transcribe speech at all. The mic control
            // reads this to stay disabled (never a dead button) where there is
            // no STT path, and the launcher falls back to opening the drawer for
            // typing. Computed once; SpeechRecognition is the real, key-less STT
            // path (no API key of ours). The browser's own implementation may
            // transcribe server-side at the vendor's cloud (see the voice-input
            // note below), so this is not an audio-stays-on-device claim.
            micSupported: (typeof window !== 'undefined' &&
                !!(window.SpeechRecognition || window.webkitSpeechRecognition)),
            recording: false,
            recSeconds: 0,
            // Live interim transcription shown in the recording bar while the mic
            // is on (wal-ledger parity, 2026-10-22). With interimResults the owner
            // SEES words appear as she speaks ("Te escucho…"), so a tap never looks
            // dead the way it did when nothing surfaced until a final result that,
            // on Android/es-AR, often never came. Doubles as the fallback transcript
            // when onend fires without a final (see startRecording).
            recInterim: '',

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
            // Fallback dock when the user has no persisted preference yet. The
            // product default is pinned ("the agent is the operating surface");
            // a surface may pass dock:'floating' to present a launcher instead.
            _defaultDock: cfg.dock || DEFAULT_DOCK,
            _endpoint: cfg.endpoint,
            _tenantPhone: cfg.phone,
            _dockKey: cfg.dockKey,
            _focusReturn: null,
            _trapHandler: null,
            _recognition: null,
            _recTimer: null,
            _recTranscript: '',
            _seedMessage: '',
            // PR-A fix #4: set true when the greeting endpoint reports
            // kind="empty_catalog". Used to suppress the post-reply chip
            // rail and to drive the .empty-catalog wrapper class.
            _catalogEmpty: false,

            // --- lifecycle ---
            init: function () {
                if (!isOnboarding) {
                    // Tenant mode: read the persisted dock preference.
                    var saved = null;
                    try { saved = localStorage.getItem(this._dockKey); } catch (_) { /* no-op */ }
                    // A floating-launcher surface (spec 006: the voice-first mic
                    // launcher) carries NO pin control, so a stale 'pinned' pref
                    // left by an earlier UI must not auto-open the drawer and
                    // bypass the collapsed-by-default launcher with no way to
                    // un-pin. Honor 'pinned' only where this surface actually
                    // offers pinning; otherwise fall back to the floating default.
                    if (cfg.dock === 'floating' && saved === 'pinned') saved = null;
                    this.docked = (saved === 'pinned' || saved === 'floating') ? saved : this._defaultDock;

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

                // Tenant mode: restore the conversation thread before anything
                // else, so Timonel is never blank after a tab switch or a
                // return visit (spec 006 T-008 / T-009). Order of precedence:
                //   1. sessionStorage (this tab's own copy; survives same-tab
                //      navigation across the separate Control Center documents).
                //   2. the server-side conversation memory (spec 001), when the
                //      session copy is empty (a fresh tab or cleared storage).
                //   3. the proactive greeting, only when both are empty.
                if (!isOnboarding && cfg.phone) {
                    if (self._rehydrateFromSession()) {
                        // Restored from this tab's session; no server round-trip,
                        // no greeting over an existing thread.
                    } else {
                        self._rehydrateFromServer(function (got) {
                            if (!got) self._maybeFetchGreeting();
                        });
                    }
                }
            },

            // --- thread persistence + rehydration (spec 006 T-008 / T-009) ---
            // The visible chat was ephemeral: messages reset on every page load,
            // so making Timonel the primary surface without this would lose the
            // conversation on every tab switch (plan risk 1). sessionStorage is
            // keyed by phone so two tenants on one browser never cross threads,
            // and it is per-tab so a closed tab starts clean. Every accessor is
            // wrapped — a private window or blocked storage degrades to "no
            // persistence", never an exception into the page.
            _threadKey: function () {
                return 'beans:thread:' + (this._tenantPhone || this._mode);
            },

            _serializeThread: function () {
                // Persist only what re-renders a bubble; drop transient flags
                // (streaming) and cap the tail so storage never grows unbounded.
                var out = [];
                var start = Math.max(0, this.messages.length - 100);
                for (var i = start; i < this.messages.length; i++) {
                    var m = this.messages[i] || {};
                    var keep = { id: m.id, role: m.role, kind: m.kind, html: m.html };
                    if (m.toolCall) keep.toolCall = m.toolCall;
                    if (m.cards) keep.cards = m.cards;
                    if (m.kind === 'receipt') {
                        // Persist the settled record so it survives a reload instead of
                        // rehydrating as a blank green box. The Undo toast is transient and is
                        // not restored, so the op_token is not needed here.
                        keep.receipt = m.receipt;
                        if (m.undone) keep.undone = true;
                    } else if (m.kind === 'confirm-card') {
                        // A staged op_token is stale after a reload: never restore an actionable
                        // card with a live "Confirmar" button. Keep an honest record of what was
                        // proposed, as plain text.
                        keep.kind = 'text';
                        keep.role = 'assistant';
                        keep.html = (m.proposed && m.proposed.summary)
                            ? escapeHtml('Te preparé: ' + m.proposed.summary + ' (pedímelo de nuevo para confirmarlo)')
                            : '';
                    }
                    if (keep.kind === 'text' && !keep.html) continue;  // drop an empty bubble
                    out.push(keep);
                }
                return out;
            },

            _saveThread: function () {
                if (this.isOnboarding) return;  // onboarding is ephemeral by design
                try {
                    sessionStorage.setItem(this._threadKey(), JSON.stringify(this._serializeThread()));
                } catch (_) { /* private mode / quota: skip persistence silently */ }
            },

            _rehydrateFromSession: function () {
                if (this.isOnboarding) return false;
                var raw = null;
                try { raw = sessionStorage.getItem(this._threadKey()); } catch (_) { return false; }
                if (!raw) return false;
                var parsed = null;
                try { parsed = JSON.parse(raw); } catch (_) { return false; }
                if (!Array.isArray(parsed) || parsed.length === 0) return false;
                var restored = [];
                for (var i = 0; i < parsed.length; i++) {
                    var m = parsed[i] || {};
                    if (!m.role) continue;
                    // streaming is never restored true: a persisted bubble is a
                    // settled bubble, so no stale cursor sticks on reload.
                    m.streaming = false;
                    restored.push(m);
                }
                if (!restored.length) return false;
                this.messages = restored;
                // A restored thread means the greeting was already shown (or is
                // moot); suppress chips until the next turn re-offers them.
                this.suggestions = [];
                this._scrollSoon();  // land on the latest turn, not the top of a long thread
                return true;
            },

            _rehydrateFromServer: function (done) {
                var self = this;
                var cb = (typeof done === 'function') ? done : function () {};
                var url = '/api/tenants/' + encodeURIComponent(this._tenantPhone) + '/chat/thread';
                fetch(url, { credentials: 'same-origin' })
                    .then(function (resp) { return resp.ok ? resp.json() : null; })
                    .then(function (payload) {
                        var turns = (payload && payload.thread) || [];
                        // Only rehydrate if the user has not already raced in a
                        // message, and there is actually a server thread.
                        if (self.messages.length > 0 || !turns.length) { cb(false); return; }
                        var restored = [];
                        for (var i = 0; i < turns.length; i++) {
                            var t = turns[i] || {};
                            if (t.role !== 'user' && t.role !== 'assistant') continue;
                            var content = t.content || '';
                            restored.push({
                                id: nextId(),
                                role: t.role,
                                kind: 'text',
                                html: t.role === 'assistant' ? renderMarkdown(content) : escapeHtml(content)
                            });
                        }
                        if (!restored.length) { cb(false); return; }
                        self.messages = restored;
                        self.suggestions = [];
                        self._saveThread();  // mirror the server thread into this tab's session
                        self._scrollSoon();
                        cb(true);
                    })
                    .catch(function () { cb(false); });
            },

            _maybeFetchGreeting: function () {
                var self = this;
                var greetingKey = 'beans:greeting:seen:' + this._tenantPhone;
                var alreadySeen = false;
                try {
                    alreadySeen = localStorage.getItem(greetingKey) === '1';
                } catch (_) { /* private mode etc.; treat as not seen */ }
                if (alreadySeen) return;

                var url = '/api/tenants/' + encodeURIComponent(this._tenantPhone) + '/chat/greeting';
                fetch(url, { credentials: 'same-origin' })
                    .then(function (resp) {
                        if (!resp.ok) return null;
                        return resp.json();
                    })
                    .then(function (payload) {
                        if (!payload || !payload.greeting) return;
                        // PR-A fix #4: when the backend reports the catalog
                        // is empty, suppress quick-action chips (Detalle por
                        // producto / Comparar con la semana pasada) for the
                        // life of this session. Those CTAs are off-context
                        // for tenants that have not loaded products yet and
                        // create the false expectation that the buttons do
                        // something useful pre-onboarding.
                        if (payload.kind === 'empty_catalog') {
                            self._catalogEmpty = true;
                            self.suggestions = [];
                            try {
                                if (self.$refs.shell && self.$refs.shell.classList) {
                                    self.$refs.shell.classList.add('empty-catalog');
                                }
                            } catch (_) { /* no shell ref yet, CSS class is belt; suggestions = [] is suspenders */ }
                        }
                        // Only push if the thread is still empty: the user
                        // may have raced and typed something already.
                        if (self.messages.length > 0) return;
                        self.messages.push({
                            id: nextId(),
                            role: 'assistant',
                            kind: 'text',
                            html: escapeHtml(payload.greeting),
                        });
                        self._saveThread();
                        try { localStorage.setItem(greetingKey, '1'); } catch (_) { /* no-op */ }
                    })
                    .catch(function () { /* network error: skip greeting silently */ });
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

            /**
             * Onboarding bootstrap: silently POST a no-op turn so Timonel
             * emits the first question (or the next missing field, if the
             * pending row already has captures) without forcing the user
             * to type or click anything. The trigger token "Hola" matches
             * the dispatcher prompt's worked example, so Gemini routes to
             * the text-only branch instead of trying to call a tool.
             *
             * Idempotent: bails the moment any message exists in the
             * thread (including a seed-pushed user bubble).
             */
            bootstrapOpening: function () {
                if (this.messages.length > 0) return;
                if (!this.isOnboarding) return;
                this.send('Hola', { hideUserBubble: true });
            },

            // --- send + receive ---
            send: function (raw, opts) {
                var text = (raw || '').trim();
                if (!text) return;
                // Block a second submit while a turn is in flight, including the
                // ~600ms streaming window after the reply lands (else a fast
                // double-tap posts twice).
                if (this.state === 'thinking' || this.state === 'tool_running' || this.state === 'streaming') return;

                if (!opts || !opts.hideUserBubble) {
                    this.messages.push({ id: nextId(), role: 'user', kind: 'text', html: escapeHtml(text) });
                    // Persist the user turn immediately: if the owner navigates
                    // before the reply lands, the sent message still survives the
                    // tab switch (spec 006 T-008).
                    this._saveThread();
                }
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
                    //   error: str | null               (legacy; pre-spec 001)
                    //   error_code: str | null          (spec 001 envelope)
                    //   navigation: { tab, filter?, sort? } | null  (spec 001)
                    //   incident_id: str | null         (spec 001)
                    //
                    // Spec 001 (Timonel M1) renames `error` to `error_code`
                    // and ships the safe_node wrapper that emits typed
                    // classes (unknown_product, missing_field, ambiguous_input,
                    // network, llm_unavailable). The widget prefers the new
                    // field and falls back to the legacy one so partial rollouts
                    // do not regress.
                    var toolCalls = metadata.tool_calls || [];
                    var errorCode = metadata.error_code || metadata.error || null;

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

                    // Reply selection (spec 001 envelope rules):
                    //   1. Prefer the server's `response` field when present.
                    //      It is already user-facing and carries the
                    //      incident_id when relevant (per ADR-002 + spec 001).
                    //   2. If `response` is empty and `error_code` is set,
                    //      fall back to the matching ERROR_FALLBACK_COPY
                    //      entry. This is the safety net for cases where
                    //      the dispatcher classified the failure but did
                    //      not produce text.
                    //   3. If both `response` AND `error_code` are missing
                    //      after a 200, treat it as the last-resort
                    //      llm_unavailable fallback. Without this the user
                    //      would see a blank assistant bubble.
                    var displayReply = reply;
                    if (!displayReply && errorCode) {
                        displayReply = ERROR_FALLBACK_COPY[errorCode] || '';
                    }
                    if (!displayReply && !errorCode) {
                        displayReply = ERROR_FALLBACK_COPY.llm_unavailable;
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

                    // spec 007 M3: a proposed write. The SERVER decided auto vs ask
                    // (metadata.proposed_operation.auto) — the model never decides, and the
                    // commit is never a model capability. auto:true -> the client submits the
                    // same non-model /chat/confirm on the owner's behalf and lands an instant
                    // receipt + loud Undo. auto:false -> a confirm card the owner clicks.
                    // One turn can stage more than one write (e.g. "vendí X y gasté Y"), so the
                    // server sends a list; fall back to the single-op key for back-compat.
                    var proposedList = metadata.proposed_operations
                        || (metadata.proposed_operation ? [metadata.proposed_operation] : []);
                    for (var pi = 0; pi < proposedList.length; pi++) {
                        var proposed = proposedList[pi];
                        if (!proposed || !proposed.op_token) continue;
                        // Auto-submit ONLY a reversible, server-approved write. Defense in depth:
                        // never auto-commit an irreversible op even if the server said auto:true —
                        // it must always show the owner a card with its irreversibility flag.
                        if (proposed.auto && !proposed.irreversible) {
                            self._autoConfirm(proposed);
                        } else {
                            self.messages.push({
                                id: nextId(), role: 'assistant', kind: 'confirm-card',
                                proposed: proposed
                            });
                        }
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
                        // PR-A fix #4: also suppress chips when the catalog
                        // is still empty; the post-reply CTAs ("Detalle por
                        // producto", "Comparar con la semana pasada") have
                        // no surface to land on yet.
                        if (!errorCode && !metadata.complete && !self.input.trim() && !self._catalogEmpty) {
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
                    //
                    // Spec 001: navigation flows ONLY from the agent's
                    // structured `metadata.navigation` field. The legacy
                    // inferNavigation() keyword scan was removed; it caused
                    // the Gastos UI flip on disambiguation replies that
                    // mentioned "gasto" inside the option list.
                    if (!self.isOnboarding && !errorCode) {
                        var nav = readNavigation(metadata);
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
                    // Persist the settled thread (assistant bubble + any tool
                    // cards, or the error bubble) so it survives a navigation.
                    self._saveThread();
                });
            },

            // --- two-phase write commit + Undo (spec 007 M3) ---------------------------
            // The commit is NEVER a model capability: both paths POST the op_token to the
            // session-authenticated /chat/confirm, from the owner's own browser. A reversible,
            // grounded, obvious write (server verdict auto:true) is submitted here without a
            // click; everything else waits for the owner to click the confirm card.

            _confirmUrl: function () { return this._endpoint + '/confirm'; },
            _undoUrl: function () { return this._endpoint + '/undo'; },

            // Auto-post: submit on the owner's behalf, then land a receipt + loud Undo. The
            // post is PESSIMISTIC — the receipt renders ONLY on committed:true (AC16); a
            // guard rejection (e.g. not enough stock) shows why it could not post, no receipt.
            _autoConfirm: function (proposed) {
                var self = this;
                fetch(this._confirmUrl(), {
                    method: 'POST', credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ op_token: proposed.op_token })
                }).then(function (r) { return r.json(); }).then(function (data) {
                    if (data && data.committed && data.receipt) {
                        self.messages.push({
                            id: nextId(), role: 'assistant', kind: 'receipt',
                            receipt: data.receipt, op_token: proposed.op_token
                        });
                        if (data.reversible) { self._showUndo(proposed.op_token, data.receipt); }
                    } else {
                        // Pessimistic: nothing posted. Say why, render no receipt, no Undo.
                        var why = (data && data.message) ? data.message
                            : 'No pude anotarlo. Probá de nuevo.';
                        self.messages.push({ id: nextId(), role: 'assistant', kind: 'text',
                            html: escapeHtml(why) });
                    }
                    self._scrollSoon(); self._saveThread();
                }).catch(function () {
                    self.messages.push({ id: nextId(), role: 'assistant', kind: 'text',
                        html: escapeHtml('No pude anotarlo ahora. Probá de nuevo.') });
                    self._scrollSoon();
                });
            },

            // Confirm-card click: commit, then SETTLE THE CARD IN PLACE into a receipt (same
            // message id — it does not vanish and respawn), per AC10.
            confirmOp: function (m) {
                if (!m || !m.proposed || m._busy) return;
                m._busy = true;
                var self = this;
                var token = m.proposed.op_token;
                fetch(this._confirmUrl(), {
                    method: 'POST', credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ op_token: token })
                }).then(function (r) { return r.json(); }).then(function (data) {
                    for (var i = 0; i < self.messages.length; i++) {
                        if (self.messages[i] && self.messages[i].id === m.id) {
                            if (data && data.committed && data.receipt) {
                                self.messages[i].kind = 'receipt';
                                self.messages[i].receipt = data.receipt;
                                self.messages[i].op_token = token;
                                self.messages[i].proposed = null;
                                if (data.reversible) { self._showUndo(token, data.receipt); }
                            } else {
                                self.messages[i].kind = 'text';
                                self.messages[i].proposed = null;
                                self.messages[i].html = escapeHtml(
                                    (data && data.message) || 'No pude anotarlo. Probá de nuevo.');
                            }
                            break;
                        }
                    }
                    self._scrollSoon(); self._saveThread();
                }).catch(function () { m._busy = false; });
            },

            // Dismiss a confirm card the owner does not want.
            dismissOp: function (m) {
                for (var i = 0; i < this.messages.length; i++) {
                    if (this.messages[i] && this.messages[i].id === m.id) {
                        this.messages.splice(i, 1);
                        break;
                    }
                }
                this._saveThread();
            },

            // The loud Undo toast (AC17): persists >= 6s, names the reversal, sits above the
            // composer, with a >= 44px tap target (the CSS enforces the size).
            _showUndo: function (op_token, receipt) {
                var self = this;
                var amount = (receipt && receipt.amount_label) ? (' ' + receipt.amount_label) : '';
                this.undoToast = { op_token: op_token, label: 'Anotado' + amount };
                if (this._undoTimer) { clearTimeout(this._undoTimer); }
                this._undoTimer = setTimeout(function () { self.undoToast = null; }, 8000);
            },

            undoOp: function () {
                if (!this.undoToast) return;
                var self = this;
                var token = this.undoToast.op_token;
                this.undoToast = null;
                if (this._undoTimer) { clearTimeout(this._undoTimer); this._undoTimer = null; }
                fetch(this._undoUrl(), {
                    method: 'POST', credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ op_token: token })
                }).then(function (r) { return r.json(); }).then(function (data) {
                    // Mark the matching receipt as undone (settles in place) and say so.
                    for (var i = 0; i < self.messages.length; i++) {
                        if (self.messages[i] && self.messages[i].op_token === token
                            && self.messages[i].kind === 'receipt') {
                            self.messages[i].undone = true;
                            break;
                        }
                    }
                    self.messages.push({ id: nextId(), role: 'system', kind: 'text',
                        html: escapeHtml('Listo, lo deshice.') });
                    // Refresh the dashboard so the reversal shows immediately.
                    window.dispatchEvent(new CustomEvent('beans:refresh',
                        { detail: { tenantPhone: self._tenantPhone } }));
                    self._scrollSoon(); self._saveThread();
                }).catch(function () {
                    self.messages.push({ id: nextId(), role: 'system', kind: 'text',
                        html: escapeHtml('No pude deshacerlo. Probá desde la lista.') });
                    self._scrollSoon();
                });
            },

            // --- voice input (spec 006 T-012) ---
            // The mic records the owner's speech and drops the transcription
            // into the composer for her to review and send — voice is an input
            // method, not a bypass of her judgement or (once it lands in M3) the
            // write trust floor. The STT path is the browser's SpeechRecognition:
            // a real transcriber that needs no API key of ours. NOTE: the common
            // implementations (Chrome's webkitSpeechRecognition, Safari) stream
            // the captured audio to the browser vendor's cloud speech service to
            // transcribe it, so spoken input leaves the device the same way any
            // web speech input does; this is not an on-device-only guarantee.
            // Where SpeechRecognition is absent, the mic stays disabled and the
            // owner types; Timonel never pretends to hear.
            recTimeLabel: function () {
                var s = this.recSeconds || 0;
                var mm = Math.floor(s / 60);
                var ss = s % 60;
                return mm + ':' + (ss < 10 ? '0' + ss : String(ss));
            },

            toggleRecording: function () {
                if (this.recording) { this.stopRecording(); } else { this.startRecording(); }
            },

            startRecording: function () {
                if (this.recording) return;
                var Rec = (typeof window !== 'undefined') &&
                    (window.SpeechRecognition || window.webkitSpeechRecognition);
                if (!Rec) {
                    // Honest fallback (wal-ledger parity): no STT in THIS browser,
                    // so say so and drop the owner straight into typing rather than
                    // leave a dead mic. The mic button itself is never disabled
                    // (the drawer opened and this ran), so she is never stuck on a
                    // grey control — she lands in the composer, focused, ready to
                    // write, and the one parse path treats it identically.
                    this.open();
                    this.messages.push({
                        id: nextId(), role: 'system', kind: 'text',
                        html: escapeHtml('Este navegador no permite dictado por voz. Escribí tu mensaje y lo proceso igual.')
                    });
                    this._scrollSoon();
                    this.$nextTick(function () {
                        var self2 = this; // Alpine binds `this` to the component
                        if (self2 && self2.$refs && self2.$refs.input) self2.$refs.input.focus();
                    }.bind(this));
                    return;
                }
                var self = this;
                var rec;
                try { rec = new Rec(); } catch (_) { return; }
                rec.lang = 'es-AR';
                // interimResults ON (wal-ledger parity): stream partial words to the
                // recording bar so the owner sees it IS listening. Without this, a tap
                // that never produced a final result (routine on Android Chrome +
                // es-AR) looked like a dead mic — the core "no funciona" report.
                rec.interimResults = true;
                rec.continuous = false;
                rec.maxAlternatives = 1;
                this._recTranscript = '';
                this.recInterim = '';
                rec.onresult = function (e) {
                    // Separate committed (isFinal) text from the live interim tail.
                    // Final text accrues to _recTranscript (what we send); interim is
                    // shown live and kept as a fallback for onend.
                    var interim = '';
                    for (var i = e.resultIndex; i < e.results.length; i++) {
                        var r = e.results[i];
                        if (!r || !r[0]) continue;
                        if (r.isFinal) self._recTranscript += r[0].transcript;
                        else interim += r[0].transcript;
                    }
                    self.recInterim = interim;
                };
                rec.onerror = function (e) {
                    var code = e && e.error;
                    self._stopRecTimer();
                    self.recording = false;
                    self._recognition = null;
                    self._recTranscript = '';  // never send a partial after an error
                    self.recInterim = '';
                    // Make failures VISIBLE — a silent failure is the "I tapped and
                    // nothing happened" report. Only 'aborted' (the owner tapped
                    // Listo / a restart) stays quiet.
                    var msg = null;
                    if (code === 'not-allowed' || code === 'service-not-allowed') {
                        msg = 'No pude usar el micrófono (permiso denegado). Activá el permiso del micrófono para este sitio, o escribí tu mensaje.';
                    } else if (code === 'no-speech') {
                        msg = 'No te escuché. Tocá el micrófono y hablá de nuevo, o escribí tu mensaje.';
                    } else if (code === 'audio-capture') {
                        msg = 'No encontré un micrófono en este dispositivo. Escribí tu mensaje y lo proceso igual.';
                    } else if (code === 'network') {
                        msg = 'El servicio de voz no respondió (red). Probá de nuevo o escribí tu mensaje.';
                    } else if (code && code !== 'aborted') {
                        msg = 'No pude grabar el audio. Probá de nuevo o escribí tu mensaje.';
                    }
                    if (msg) {
                        self.messages.push({ id: nextId(), role: 'system', kind: 'text', html: escapeHtml(msg) });
                        self._scrollSoon();
                    }
                };
                rec.onend = function () {
                    self._stopRecTimer();
                    self.recording = false;
                    self._recognition = null;
                    // Fall back to the last interim if no final landed — on Android
                    // Chrome a short/accented phrase often ends with only interim
                    // text, and dropping it was the "nothing happened" bug.
                    var said = (self._recTranscript || self.recInterim || '').trim();
                    self._recTranscript = '';
                    self.recInterim = '';
                    // Place the transcription in the composer for the owner to
                    // read and send herself — NEVER auto-send. She always sees
                    // what Timonel heard before it acts on her money or stock, so
                    // a mis-hear ("trece" for "tres", a mangled "borrá...") is
                    // caught at a glance instead of becoming an unconfirmed write
                    // (Edut: M2 ships no confirm floor yet — that is M3). Tapping
                    // Enviar routes the text through the identical path a typed
                    // message takes, so when M3's confirm/receipt/undo lands a
                    // spoken write passes the same floor a typed one does.
                    if (said) {
                        self.input = said;
                        self.open();
                        self.$nextTick(function () { if (self.$refs.input) self.$refs.input.focus(); });
                    }
                };
                try {
                    rec.start();  // triggers the browser mic-permission prompt
                } catch (_) {
                    // start() throws if called while already running; reset state.
                    self.recording = false;
                    return;
                }
                this._recognition = rec;
                this.recording = true;
                this.recSeconds = 0;
                this.open();  // voice-first: recording surfaces the drawer
                this._recTimer = setInterval(function () { self.recSeconds += 1; }, 1000);
            },

            stopRecording: function () {
                this._stopRecTimer();
                if (this._recognition) {
                    // Normally onend fires after stop() and resets state; if stop()
                    // throws (already-ended / never-started recognizer), onend may
                    // not fire, so reset here too — never leave the UI stuck
                    // showing "Grabando" with a dead recognizer.
                    try { this._recognition.stop(); }
                    catch (_) { this.recording = false; this._recognition = null; this.recInterim = ''; }
                } else {
                    this.recording = false;
                }
            },

            _stopRecTimer: function () {
                if (this._recTimer) { clearInterval(this._recTimer); this._recTimer = null; }
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
