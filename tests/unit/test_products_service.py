import pytest

from backend.models.schemas import ProductCreate, ProductUpdate
from backend.services.products_service import (
    ProductConflictError,
    ProductNotFoundError,
    ProductsService,
)


class FakeRepo:
    def __init__(self):
        self.calls = []
        self.rows = {
            1: {
                "id": 1,
                "sku": "SKU-1",
                "name": "Prod 1",
                "description": None,
                "unit_cost_cents": 100,
                "unit_price_cents": 300,
                "is_active": 1,
                "created_at": "2026-01-01T00:00:00",
            }
        }

    def list_products(self, include_inactive, limit, offset):
        self.calls.append(("list_products", include_inactive, limit, offset))
        return list(self.rows.values())

    def get_by_id(self, product_id):
        self.calls.append(("get_by_id", product_id))
        return self.rows.get(product_id)

    def get_by_sku(self, sku):
        self.calls.append(("get_by_sku", sku))
        for row in self.rows.values():
            if row["sku"] == sku:
                return row
        return None

    def create(self, payload):
        self.calls.append(("create", payload))
        if payload["sku"] == "DUP":
            raise Exception("UNIQUE constraint failed: products.sku")
        return {
            "id": 2,
            "sku": payload["sku"],
            "name": payload["name"],
            "description": payload.get("description"),
            "unit_cost_cents": payload["unit_cost_cents"],
            "unit_price_cents": payload["unit_price_cents"],
            "is_active": 1,
            "created_at": "2026-01-02T00:00:00",
        }

    def create_without_returning(self, payload):
        self.calls.append(("create_without_returning", payload))
        self.rows[2] = {
            "id": 2,
            "sku": payload["sku"],
            "name": payload["name"],
            "description": payload.get("description"),
            "unit_cost_cents": payload["unit_cost_cents"],
            "unit_price_cents": payload["unit_price_cents"],
            "is_active": 1,
            "created_at": "2026-01-02T00:00:00",
        }

    def update(self, product_id, updates):
        self.calls.append(("update", product_id, updates))
        if product_id not in self.rows:
            return None
        self.rows[product_id] = {**self.rows[product_id], **updates}
        return self.rows[product_id]

    def update_without_returning(self, product_id, updates):
        self.calls.append(("update_without_returning", product_id, updates))
        return self.update(product_id, updates)

    def deactivate(self, product_id):
        self.calls.append(("deactivate", product_id))
        if product_id not in self.rows:
            raise ValueError("Producto con ID no encontrado")
        if not self.rows[product_id]["is_active"]:
            raise ValueError("Producto ya desactivado")
        self.rows[product_id]["is_active"] = 0
        return {"status": "ok", "product_id": product_id}


def test_list_products_uses_versioned_cache(monkeypatch):
    repo = FakeRepo()
    service = ProductsService(repository=repo)

    cache_store = {}

    monkeypatch.setattr(
        "backend.services.products_service.cache.get_resource_version",
        lambda _phone, _resource: 7,
    )
    monkeypatch.setattr(
        "backend.services.products_service.cache.get_cached_products",
        lambda phone, active_only=False, limit=None, offset=None, version=None: cache_store.get(
            (phone, active_only, limit, offset, version)
        ),
    )
    monkeypatch.setattr(
        "backend.services.products_service.cache.cache_products",
        lambda phone, products, active_only=False, limit=None, offset=None, version=None: cache_store.setdefault(
            (phone, active_only, limit, offset, version), products
        ),
    )

    first = service.list_products("+1", include_inactive=False, limit=10, offset=0)
    second = service.list_products("+1", include_inactive=False, limit=10, offset=0)

    assert len(first) == 1
    assert len(second) == 1
    assert [c for c in repo.calls if c[0] == "list_products"] == [("list_products", False, 10, 0)]


def test_create_product_bumps_cache_version(monkeypatch):
    repo = FakeRepo()
    service = ProductsService(repository=repo)
    bumped = {"count": 0}

    monkeypatch.setattr(
        "backend.services.products_service.cache.bump_resource_version",
        lambda _phone, _resource: bumped.__setitem__("count", bumped["count"] + 1) or bumped["count"],
    )

    result = service.create_product(
        "+1",
        ProductCreate(
            sku="SKU-NEW",
            name="New Product",
            description=None,
            unit_cost_cents=100,
            unit_price_cents=250,
        ),
    )

    assert result.sku == "SKU-NEW"
    assert bumped["count"] == 1


def test_create_product_duplicate_raises_conflict(monkeypatch):
    repo = FakeRepo()
    service = ProductsService(repository=repo)
    monkeypatch.setattr(
        "backend.services.products_service.cache.bump_resource_version",
        lambda *_args, **_kwargs: 1,
    )

    with pytest.raises(ProductConflictError):
        service.create_product(
            "+1",
            ProductCreate(
                sku="DUP",
                name="Dup",
                description=None,
                unit_cost_cents=100,
                unit_price_cents=200,
            ),
        )


def test_update_product_not_found_raises_domain_error():
    repo = FakeRepo()
    service = ProductsService(repository=repo)

    with pytest.raises(ProductNotFoundError):
        service.update_product("+1", 999, ProductUpdate(name="Updated"))
