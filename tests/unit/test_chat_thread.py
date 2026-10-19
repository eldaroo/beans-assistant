"""Server-side chat-thread rehydration source (spec 006 T-009 / AC4).

The widget rehydrates from the server conversation memory when the browser's
sessionStorage is empty. These tests cover the server source of that thread:
ChatService.get_history returns the turns the dispatcher recorded, lean and in
order, honoring the same staleness expiry as the write path.
"""
import pytest

from backend.services.chat_service import ChatService


@pytest.mark.unit
def test_prior_turn_appears_after_fresh_load():
    """AC4: a prior server-side turn is readable back (the fresh-load case)."""
    phone = "+549110000T009a"
    ChatService._history_by_key.pop(ChatService._history_key(phone), None)

    ChatService._append_history(phone, "cuántas ventas hoy", "Hoy llevás 2 ventas cobradas.")

    thread = ChatService.get_history(phone)
    assert thread == [
        {"role": "user", "content": "cuántas ventas hoy"},
        {"role": "assistant", "content": "Hoy llevás 2 ventas cobradas."},
    ]


@pytest.mark.unit
def test_empty_thread_reads_back_empty():
    """A tenant with no server-side turns reads back an empty list, not an error."""
    phone = "+549110000T009b"
    ChatService._history_by_key.pop(ChatService._history_key(phone), None)
    assert ChatService.get_history(phone) == []


@pytest.mark.unit
def test_blank_and_metadata_only_turns_are_dropped():
    """Lean read: empty-content turns are not surfaced for rehydration."""
    phone = "+549110000T009c"
    ChatService._history_by_key.pop(ChatService._history_key(phone), None)
    ChatService._append_history(phone, "hola", "")  # assistant produced no text
    thread = ChatService.get_history(phone)
    assert thread == [{"role": "user", "content": "hola"}]


@pytest.mark.unit
def test_stale_thread_expires_and_reads_empty(monkeypatch):
    """A thread older than the TTL reads back empty (no stale resurrection)."""
    phone = "+549110000T009d"
    ChatService._history_by_key.pop(ChatService._history_key(phone), None)
    ChatService._append_history(phone, "hola", "qué tal")
    # Force the last-seen stamp well past the TTL (1.0 = 1970, definitely stale;
    # a literal 0.0 would be treated as "never seen" by the falsy guard).
    key = ChatService._history_key(phone)
    ChatService._last_seen_by_key[key] = 1.0
    assert ChatService.get_history(phone) == []
