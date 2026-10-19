/*
 * cc_chat_bridge.js — the chat-to-screen refresh contract across the separate
 * Control Center documents (spec 004, S7 / T-011 / AC8).
 *
 * The legacy dashboard (tenant_detail.html) was ONE Alpine scope with four
 * tabs, so a chat turn could switch a tab and refetch in-place. The Control
 * Center is now one document per domain (home, productos, stock, ventas,
 * resultado, and the migrated read-only pages). Timonel is mounted once in
 * cc_base and emits the same two window events it always did:
 *
 *   beans:refresh  { tenantPhone }          — fired on every clean tenant turn.
 *   beans:navigate { tab, filter?, sort? }  — fired only when a tool actually
 *                                             executed (metadata.navigation).
 *
 * This bridge re-establishes the contract for the split-document world WITHOUT
 * touching the widget internals (out of scope):
 *
 *   - beans:refresh  -> the current page refetches ITS OWN data. A CRUD page
 *     registers `window.ccRefetch` in its Alpine init(); the bridge calls it.
 *     A page with no in-place refetch (the server-rendered home / read-only
 *     pages) registers none, so a read-only turn leaves it untouched — it
 *     never claims to refresh a screen it cannot refetch.
 *
 *   - beans:navigate -> the agent opened a domain screen. Across documents the
 *     honest way to honor "Stock abierto" is to actually OPEN the stock page.
 *     If the target domain is a DIFFERENT document than the one we are on, the
 *     bridge navigates there (so the claim is true); if it is the SAME page,
 *     beans:refresh already updated it in place. A domain with no owner page is
 *     ignored — the bridge never navigates somewhere it cannot reach, and so
 *     never leaves a false "X abierto" claim standing against a dead screen.
 *
 * All four navigable domains (products, stock, sales, expenses) have owner
 * pages as of spec 004 cohorts B/C, so every navigate target is reachable.
 */
(function () {
    'use strict';

    // Grace before a cross-document jump. Deliberately LONGER than the widget's
    // own completion-redirect grace (REDIRECT_GRACE_MS = 1500ms in
    // chat_widget.js): a turn that carries BOTH metadata.navigation AND
    // metadata.complete+redirect_to schedules two full-page navigations, and
    // the bridge cannot see redirect_to (beans:navigate.detail is only
    // {tab,filter,sort}). Keeping this grace above 1500ms guarantees the
    // server-instructed completion redirect fires first and tears down this
    // document — so the bridge's assign() never silently preempts it. The
    // common case (navigate without a completion redirect) still opens promptly
    // after the owner reads the reply bubble. (Council Winston, HIGH.)
    var NAV_GRACE_MS = 1600;

    var root = document.body;
    var phone = (root && root.getAttribute('data-cc-phone')) || '';

    // A cross-document open scheduled this turn. The widget dispatches
    // beans:navigate BEFORE beans:refresh, so when a write turn is about to
    // jump, the refresh handler skips the refetch (no fetch + loading flash on
    // a page about to unload). (Council Winston, LOW.)
    var navPending = false;

    // Normalize a path for same-page comparison: drop a single trailing slash so
    // a framework slash-redirect cannot cause a redundant full reload to the
    // same screen. (Council Amelia, LOW.)
    function normPath(p) {
        return (p.length > 1 && p.charAt(p.length - 1) === '/') ? p.slice(0, -1) : p;
    }

    // Map the widget's navigation tab (English keys; the widget already aliases
    // the Spanish backend cues to these via TAB_ALIASES) to the owner page that
    // OWNS that domain. Expenses live on the Resultado page (AC6), so the
    // "gastos" cue opens /resultado. encodeURIComponent on the phone is a
    // security boundary: a hostile data-cc-phone (e.g. "//host", "../x") becomes
    // an inert encoded segment on a same-origin path, never an open redirect or
    // traversal (council Tamir).
    function routeForTab(tab) {
        if (!phone) return null;
        var p = encodeURIComponent(phone);
        switch (tab) {
            case 'products': return '/productos/' + p;
            case 'stock':    return '/stock/' + p;
            case 'sales':    return '/ventas/' + p;
            case 'expenses': return '/resultado/' + p;
            default:         return null;   // unknown domain: do not claim a screen
        }
    }

    // beans:refresh — refetch the current page in place when it can, else no-op.
    window.addEventListener('beans:refresh', function () {
        if (navPending) return;  // a cross-document open is already scheduled
        if (typeof window.ccRefetch === 'function') {
            try { window.ccRefetch(); } catch (e) { /* a refetch error surfaces in the page's own error banner */ }
        }
        // No ccRefetch (home / read-only pages): nothing to refetch in place. A
        // write turn also fires beans:navigate, which takes the owner to the
        // domain page where the change is visible on a fresh load; a read-only
        // turn changed nothing, so the stale-free home needs no reload.
    });

    // beans:navigate — open the acted-on domain page across documents.
    //
    // Spec 006 T-011 extends beans:navigate with an owner-form {tab, module}
    // consumed by the shell tab-router in cc_base.html. This bridge owns only
    // the LEGACY domain form (tab in {products,stock,sales,expenses}, no
    // module). A payload carrying a `module` is the owner-form; skip it here so
    // the two listeners partition the event space and neither double-acts
    // (D-031: extend the bridge, do not replace it).
    window.addEventListener('beans:navigate', function (e) {
        var detail = (e && e.detail) || {};
        if (detail.module) return;  // owner-form: the shell tab-router handles it
        if (!detail.tab) return;
        var target = routeForTab(detail.tab);
        if (!target) return;  // unreachable domain (incl. owner-tab ids): shell router / no-op

        // Same document as the one we are on: beans:refresh already updated it.
        var here = normPath(decodeURIComponent(window.location.pathname));
        if (here === normPath(decodeURIComponent(target))) return;

        navPending = true;
        window.setTimeout(function () {
            window.location.assign(target);
        }, NAV_GRACE_MS);
    });
})();
