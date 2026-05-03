# Browser-driven E2E tests

These tests are the close-phase gate per `brain/agents/forge.md`. Any phase that ships UI interactivity (Alpine, custom events, hand-offs, page transitions) must close with `pytest -m browser` green. The bar is `console.error == 0` during the happy path.

## Why

Tests + curl + 200/401/403 status codes do not validate JS execution. They pass while the JS crashes. Two real incidents on this project:

1. M1 portal-auth: the OAuth callback redirected to `/portal`, a route that did not exist. Unit tests green, smoke status codes green, browser crashed on first login.
2. M2 onboarding: `onboarding.html` did not include `chat_widget.js`, so `window.beansChat` was undefined → cascade of Alpine errors at hand-off. Unit tests green, smoke status codes green, browser crashed on first chip click.

Browser-driven smoke catches both at the first assertion.

## Pre-conditions to run

1. Backend running at `http://127.0.0.1:8000`. Start with:
   ```
   USE_POSTGRES=true POSTGRES_HOST=localhost POSTGRES_PORT=5433 \
     POSTGRES_DB=beansco_main POSTGRES_USER=beansco POSTGRES_PASSWORD=changeme123 \
     INTERNAL_SERVICE_TOKEN=test-internal-token-local \
     python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --log-level warning
   ```
2. Postgres on `:5433` with the project schemas applied (see `postgres/init/`).
3. `.env` at the project root with `SESSION_SECRET=...`. Cookies are forged using that secret so the live server validates them.
4. Playwright Chromium installed: `playwright install chromium` (one-time).

If any of those is missing the suite skips with a clear reason — it does NOT fail.

## Run

```
pytest -m browser -v
```

Default `pytest` runs do NOT include browser tests; the marker is opt-in.

## How to write a new test

Use the fixtures in `conftest.py`:

- `pending_cookie` / `active_owner_cookie` / `active_admin_cookie` — forge a session cookie that the live server accepts.
- `page_with_cookies(cookies)` — returns `(page, errors)`. Errors is a live list. Asserting `errors == []` at the end of the test enforces the no-console-error invariant.

Skeleton:

```python
import pytest

@pytest.mark.browser
def test_my_flow(page_with_cookies, pending_cookie):
    page, errors = page_with_cookies([pending_cookie])
    page.goto("http://127.0.0.1:8000/some-page", wait_until="networkidle")
    # ...interact: click, fill, press_enter...
    # ...assertions about the API response and the rendered UI...
    assert errors == [], f"console errors: {errors}"
```

## What gets filtered out of `errors`

The Tailwind CDN production-warning is cosmetic and noisy. The fixture filters it out so it does not pollute assertions. Everything else (real `console.error`, uncaught `pageerror`) is kept.

## When to add a new browser test

Whenever Forge ships a phase that adds:
- A new template + JS factory pair.
- A new event contract (custom events, postMessage, etc.).
- A new redirect path or auth state machine.
- A user-visible interactivity flow that the existing browser tests do not cover.

The new test goes in this directory. It does not have to be exhaustive — it has to recreate the happy path the user will execute on first reload.
