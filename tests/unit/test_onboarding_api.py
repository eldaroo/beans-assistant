from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import onboarding as onboarding_api


def test_onboarding_api_exposes_structured_messages(monkeypatch):
    app = FastAPI()
    app.include_router(onboarding_api.router, prefix="/api/onboarding")
    client = TestClient(app)

    monkeypatch.setattr(
        onboarding_api.onboarding_service,
        "handle_message",
        lambda phone, message, sender_name=None: {
            "response": "Bienvenida fallback",
            "messages": [
                {"type": "text", "text": "Bienvenido al onboarding"},
            ],
            "metadata": {
                "step": "welcome",
                "phase": "setup",
                "onboarding_complete": False,
                "tenant_created": False,
                "product_created": False,
            },
        },
    )

    response = client.post("/api/onboarding/+5491112345678", json={"message": "hola"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == "Bienvenida fallback"
    assert payload["messages"][0]["type"] == "text"
    assert payload["messages"][0]["text"] == "Bienvenido al onboarding"
