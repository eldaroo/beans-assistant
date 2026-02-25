from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import products as products_api
from backend.services.products_service import ProductConflictError, ProductNotFoundError


@pytest.fixture
def client(monkeypatch):
    @contextmanager
    def _tenant_scope(_phone: str):
        yield

    monkeypatch.setattr(products_api, "tenant_scope", _tenant_scope)

    app = FastAPI()
    app.include_router(products_api.router, prefix="/api/tenants")
    return TestClient(app)


def test_list_products_uses_pagination_and_cache(client, monkeypatch):
    calls = {"list_products": 0}

    def _list_products(phone, include_inactive=False, limit=100, offset=0):
        calls["list_products"] += 1
        assert phone == "+123"
        assert include_inactive is False
        assert limit == 2
        assert offset == 1
        return [
            {
                "id": 1,
                "sku": "SKU-1",
                "name": "Product 1",
                "description": None,
                "unit_cost_cents": 100,
                "unit_price_cents": 200,
                "is_active": True,
                "created_at": "2026-01-01T00:00:00",
                "unit_cost_usd": 1.0,
                "unit_price_usd": 2.0,
            }
        ]

    monkeypatch.setattr(products_api.products_service, "list_products", _list_products)

    response_1 = client.get("/api/tenants/+123/products?limit=2&offset=1")
    assert response_1.status_code == 200
    assert response_1.json()[0]["sku"] == "SKU-1"
    assert calls["list_products"] == 1


def test_create_product_duplicate_sku_returns_409(client, monkeypatch):
    def _create_product(*_args, **_kwargs):
        raise ProductConflictError("Product with SKU 'DUP-1' already exists")

    monkeypatch.setattr(products_api.products_service, "create_product", _create_product)

    payload = {
        "sku": "DUP-1",
        "name": "Duplicate",
        "unit_cost_cents": 100,
        "unit_price_cents": 200,
    }
    response = client.post("/api/tenants/+123/products", json=payload)
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_update_product_not_found_returns_404(client, monkeypatch):
    def _update_product(*_args, **_kwargs):
        raise ProductNotFoundError("Product 999 not found")

    monkeypatch.setattr(products_api.products_service, "update_product", _update_product)

    response = client.put("/api/tenants/+123/products/999", json={"name": "Updated"})
    assert response.status_code == 404


def test_deactivate_product_conflict_returns_409(client, monkeypatch):
    def _deactivate_product(*_args, **_kwargs):
        raise ProductConflictError("El producto 'X' ya está desactivado")

    monkeypatch.setattr(products_api.products_service, "deactivate_product", _deactivate_product)

    response = client.delete("/api/tenants/+123/products/1")
    assert response.status_code == 409
