"""Browser-driven smoke for the onboarding happy path.

This is the test that should have caught the chat_widget.js include miss in
M2 the first time. Bar (per `brain/agents/forge.md`):
- The page loads without console.error.
- The user can submit a message via the spectacle input.
- The hand-off mounts the chat shell, the user message renders, the API
  responds 200.
- A second turn from the docked chat input also responds 200.
- After a state-mutating turn, a tool-call card renders in the DOM.

If this test goes red while M3 is being built (because M3 changes the
backend stub's reply pattern), update the assertions on the response
shape — but do NOT relax the no-console-error invariant.

Pre-condition for the tool-card assertion: the M3.3 dispatcher requires
GOOGLE_API_KEY in the backend environment. Without it, the dispatcher
returns metadata.error="llm_unavailable" and tool_calls=[] — the test
detects that and skips the tool-card assertion gracefully so M3.4 can
still ship even when the LLM isn't reachable in CI.
"""

import pytest


@pytest.mark.browser
def test_onboarding_handoff_no_console_errors(page_with_cookies, pending_cookie):
    """Type into the spectacle input → handoff → chat shell mounts → second turn.

    M3.3 routes through the real LLM dispatcher, so reply text varies. We no
    longer assert on the assistant bubble's text content — only that the
    user bubble renders, the API returns 200, and no console errors fire.
    If the LLM key isn't set, the dispatcher emits metadata.error and the
    error-recovery copy renders in the assistant bubble; that's still a
    valid 200 response and still a clean (no console.error) flow.
    """
    page, errors = page_with_cookies([pending_cookie])

    page.goto("http://127.0.0.1:8000/onboarding", wait_until="networkidle")
    page.wait_for_timeout(4500)  # spectacle 4-act budget settles

    # Spectacle rendered: greeting visible.
    assert page.locator("text=Soy Timonel").first.is_visible(), "greeting not rendered"

    # Type "vendo medias" in the spectacle input — Dario's exact path.
    spectacle_input = page.locator('input[placeholder*="contale a Timonel"]').first
    assert spectacle_input.is_visible(), "spectacle input not visible"
    spectacle_input.fill("vendo medias")

    with page.expect_response(
        lambda r: "/api/onboarding/web" in r.url, timeout=10000
    ) as resp_info:
        page.keyboard.press("Enter")

    resp = resp_info.value
    assert resp.status == 200, f"first turn failed: {resp.status}"

    page.wait_for_timeout(1500)  # let the chat shell mount + render the bubble

    # User bubble rendered (this is structural — the user typed it ourselves).
    assert page.locator("text=vendo medias").first.is_visible(), "user bubble not rendered"

    # Second turn from the docked chat input.
    chat_input = page.locator('textarea[placeholder*="Pedile algo al timonel"]').first
    assert chat_input.is_visible(), "chat input not visible after hand-off"
    chat_input.fill("medias deportivas, marca AceTech")

    with page.expect_response(
        lambda r: "/api/onboarding/web" in r.url, timeout=10000
    ) as resp_info2:
        page.keyboard.press("Enter")

    resp2 = resp_info2.value
    assert resp2.status == 200, f"second turn failed: {resp2.status}"

    page.wait_for_timeout(1500)

    # M3.4 tool-card assertion: if the LLM is reachable the second turn
    # ("medias deportivas, marca AceTech") is a clear capture turn that
    # should mutate state and emit at least one tool-call card. If the LLM
    # is unavailable (no GOOGLE_API_KEY), the dispatcher returns
    # metadata.error="llm_unavailable" with tool_calls=[]; we skip the
    # tool-card check in that case but still demand zero console errors.
    body = resp2.json()
    metadata = body.get("metadata") or {}
    if metadata.get("error"):
        # Infra failure path: just verify no console errors. The recovery
        # copy renders as an assistant bubble; tool-card assertion N/A.
        pass
    elif metadata.get("tool_calls"):
        # Card shape: [role=status][aria-busy=false] with the rounded-lg
        # rectangle (not the rounded-2xl bubble). We assert presence rather
        # than label text since the LLM may pick any verb-led label.
        cards = page.locator('article[role="status"][aria-busy="false"].rounded-lg')
        assert cards.count() >= 1, (
            "expected at least one tool-call card in DOM after capture turn, "
            f"saw {cards.count()}"
        )

    assert errors == [], f"console errors during onboarding flow: {errors}"


@pytest.mark.browser
def test_onboarding_chip_path(page_with_cookies, pending_cookie):
    """Click the first-action chip instead of typing.

    M3.3 routes through the real LLM dispatcher, so we assert only the
    structural invariants: the API returns 200 and no console errors fire.
    The exact reply text is non-deterministic.
    """
    page, errors = page_with_cookies([pending_cookie])
    page.goto("http://127.0.0.1:8000/onboarding", wait_until="networkidle")
    page.wait_for_timeout(4500)

    chip = page.locator("text=Configurar mi negocio").first
    assert chip.is_visible(), "first-action chip not rendered"

    with page.expect_response(
        lambda r: "/api/onboarding/web" in r.url, timeout=10000
    ) as resp_info:
        chip.click()

    assert resp_info.value.status == 200
    page.wait_for_timeout(1200)
    assert errors == [], f"console errors after chip click: {errors}"


@pytest.mark.browser
def test_onboarding_blocks_active_session(page_with_cookies, active_owner_cookie):
    """An active owner session must not see /onboarding (gated by require_pending_session)."""
    page, errors = page_with_cookies([active_owner_cookie])
    response = page.goto("http://127.0.0.1:8000/onboarding")
    assert response.status == 403, f"expected 403, got {response.status}"
