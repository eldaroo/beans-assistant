"""Service layer for product use-cases."""

import logging
from datetime import datetime
from typing import Any

from backend import cache
from backend.models.schemas import ProductCreate, ProductResponse, ProductUpdate
from backend.repositories.products_repository import ProductsRepository

logger = logging.getLogger(__name__)


class ProductNotFoundError(ValueError):
    """Raised when a product does not exist."""


class ProductConflictError(ValueError):
    """Raised for business conflicts (e.g. duplicate SKU, already inactive)."""


def _is_duplicate_sku_error(error_msg: str) -> bool:
    lowered = error_msg.lower()
    return "duplicate key" in lowered or "unique constraint" in lowered


def _is_returning_not_supported_error(error_msg: str) -> bool:
    lowered = error_msg.lower()
    return "returning" in lowered and ("syntax" in lowered or "operationalerror" in lowered)


class ProductsService:
    """Orchestrates products repository, mapping and cache behavior."""

    RESOURCE_NAME = "products"

    def __init__(self, repository: ProductsRepository | None = None):
        self.repository = repository or ProductsRepository()

    def _current_cache_version(self, phone: str) -> int:
        return cache.get_resource_version(phone, self.RESOURCE_NAME)

    def _bump_cache_version(self, phone: str) -> int:
        return cache.bump_resource_version(phone, self.RESOURCE_NAME)

    @staticmethod
    def _row_to_response(row: dict) -> ProductResponse:
        row_dict = dict(row)
        created_at = row_dict["created_at"]
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()

        return ProductResponse(
            id=row_dict["id"],
            sku=row_dict["sku"],
            name=row_dict["name"],
            description=row_dict.get("description"),
            unit_cost_cents=row_dict["unit_cost_cents"],
            unit_price_cents=row_dict["unit_price_cents"],
            is_active=bool(row_dict["is_active"]),
            created_at=created_at,
            unit_cost_usd=round(row_dict["unit_cost_cents"] / 100.0, 2),
            unit_price_usd=round(row_dict["unit_price_cents"] / 100.0, 2),
        )

    @staticmethod
    def _deserialize_cached_product(cached_item: Any) -> ProductResponse:
        if isinstance(cached_item, ProductResponse):
            return cached_item
        return ProductResponse.model_validate(cached_item)

    def list_products(
        self,
        phone: str,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProductResponse]:
        version = self._current_cache_version(phone)
        cached_products = cache.get_cached_products(
            phone,
            active_only=not include_inactive,
            limit=limit,
            offset=offset,
            version=version,
        )
        if cached_products is not None:
            return [self._deserialize_cached_product(item) for item in cached_products]

        rows = self.repository.list_products(
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
        )
        products = [self._row_to_response(row) for row in rows]
        cache.cache_products(
            phone,
            [p.model_dump() for p in products],
            active_only=not include_inactive,
            limit=limit,
            offset=offset,
            version=version,
        )
        return products

    def get_product(self, phone: str, product_id: int) -> ProductResponse:
        version = self._current_cache_version(phone)
        cached_product = cache.get_cached_product(phone, product_id, version=version)
        if cached_product is not None:
            return self._deserialize_cached_product(cached_product)

        row = self.repository.get_by_id(product_id)
        if not row:
            raise ProductNotFoundError(f"Product {product_id} not found")

        product = self._row_to_response(row)
        cache.cache_product(phone, product_id, product.model_dump(), version=version)
        return product

    def create_product(self, phone: str, payload: ProductCreate) -> ProductResponse:
        product_payload = {
            "sku": payload.sku,
            "name": payload.name,
            "description": payload.description,
            "unit_cost_cents": payload.unit_cost_cents,
            "unit_price_cents": payload.unit_price_cents,
        }
        try:
            try:
                row = self.repository.create(product_payload)
            except Exception as exc:
                if not _is_returning_not_supported_error(str(exc)):
                    raise
                logger.warning("RETURNING not supported in current DB; using legacy insert fallback")
                self.repository.create_without_returning(product_payload)
                row = self.repository.get_by_sku(payload.sku)

            if not row:
                raise RuntimeError("Product created but could not be returned")

            self._bump_cache_version(phone)
            return self._row_to_response(row)
        except Exception as exc:
            if _is_duplicate_sku_error(str(exc)):
                raise ProductConflictError(
                    f"Product with SKU '{payload.sku}' already exists"
                ) from exc
            raise

    def update_product(self, phone: str, product_id: int, payload: ProductUpdate) -> ProductResponse:
        existing_row = self.repository.get_by_id(product_id)
        if not existing_row:
            raise ProductNotFoundError(f"Product {product_id} not found")

        updates: dict[str, Any] = {}
        if payload.sku is not None:
            updates["sku"] = payload.sku
        if payload.name is not None:
            updates["name"] = payload.name
        if payload.description is not None:
            updates["description"] = payload.description
        if payload.unit_cost_cents is not None:
            updates["unit_cost_cents"] = payload.unit_cost_cents
        if payload.unit_price_cents is not None:
            updates["unit_price_cents"] = payload.unit_price_cents

        if not updates:
            return self._row_to_response(existing_row)

        try:
            try:
                updated_row = self.repository.update(product_id, updates)
            except Exception as exc:
                if not _is_returning_not_supported_error(str(exc)):
                    raise
                logger.warning("RETURNING not supported in current DB; using legacy update fallback")
                updated_row = self.repository.update_without_returning(product_id, updates)

            if not updated_row:
                raise ProductNotFoundError(f"Product {product_id} not found")

            self._bump_cache_version(phone)
            return self._row_to_response(updated_row)
        except ProductNotFoundError:
            raise
        except Exception as exc:
            if _is_duplicate_sku_error(str(exc)):
                raise ProductConflictError(
                    f"Product with SKU '{payload.sku}' already exists"
                ) from exc
            raise

    def deactivate_product(self, phone: str, product_id: int) -> dict:
        try:
            result = self.repository.deactivate(product_id)
            self._bump_cache_version(phone)
            return result
        except ValueError as exc:
            msg = str(exc)
            lowered = msg.lower()
            if "no encontrado" in lowered or "not found" in lowered:
                raise ProductNotFoundError(f"Product {product_id} not found") from exc
            raise ProductConflictError(msg) from exc

