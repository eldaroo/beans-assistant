"""Service layer for stock use-cases."""

from datetime import datetime
from typing import Any

from backend import cache
from backend.models.schemas import StockAddInput, StockCurrentResponse, StockMovementResponse
from backend.repositories.stock_repository import StockRepository


class StockNotFoundError(ValueError):
    """Raised when the target stock/product does not exist."""


class StockValidationError(ValueError):
    """Raised for invalid payload/state operations."""


def _is_not_found_error(message: str) -> bool:
    lowered = message.lower()
    return "not found" in lowered or "no encontrado" in lowered


class StockService:
    """Orchestrates stock repository, mapping and cache behavior."""

    def __init__(self, repository: StockRepository | None = None):
        self.repository = repository or StockRepository()

    @staticmethod
    def _movement_row_to_response(row: dict) -> StockMovementResponse:
        row_dict = dict(row)

        occurred_at = row_dict["occurred_at"]
        if isinstance(occurred_at, datetime):
            occurred_at = occurred_at.isoformat()

        created_at = row_dict["created_at"]
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()

        return StockMovementResponse(
            id=row_dict["id"],
            product_id=row_dict["product_id"],
            movement_type=row_dict["movement_type"],
            quantity=row_dict["quantity"],
            reason=row_dict.get("reason"),
            reference=row_dict.get("reference"),
            occurred_at=occurred_at,
            created_at=created_at,
            product_name=row_dict.get("product_name"),
            product_sku=row_dict.get("product_sku"),
        )

    @staticmethod
    def _stock_current_row_to_response(row: dict) -> StockCurrentResponse:
        row_dict = dict(row)
        unit_price_cents = row_dict.get("unit_price_cents")
        unit_price_usd = round(unit_price_cents / 100.0, 2) if unit_price_cents is not None else None

        return StockCurrentResponse(
            product_id=row_dict["product_id"],
            sku=row_dict["sku"],
            name=row_dict["name"],
            stock_qty=row_dict["stock_qty"],
            unit_price_cents=unit_price_cents,
            unit_price_usd=unit_price_usd,
        )

    @staticmethod
    def _deserialize_stock_current(cached_item: Any) -> StockCurrentResponse:
        if isinstance(cached_item, StockCurrentResponse):
            return cached_item
        return StockCurrentResponse.model_validate(cached_item)

    def get_current_stock(self, phone: str, limit: int, offset: int) -> list[StockCurrentResponse]:
        cached_stock = cache.get_cached_stock(phone, limit=limit, offset=offset)
        if cached_stock is not None:
            return [self._deserialize_stock_current(item) for item in cached_stock]

        rows = self.repository.list_current_stock(limit=limit, offset=offset)
        stock = [self._stock_current_row_to_response(row) for row in rows]
        cache.cache_stock(phone, [item.model_dump() for item in stock], limit=limit, offset=offset)
        return stock

    def add_stock(self, phone: str, stock_input: StockAddInput) -> dict:
        try:
            payload = {
                "product_id": stock_input.product_id,
                "quantity": stock_input.quantity,
                "reason": stock_input.reason,
                "movement_type": stock_input.movement_type,
            }
            result = self.repository.add_stock(payload)
            if result.get("status") != "ok":
                raise StockValidationError(result.get("message", "Failed to add stock"))

            cache.invalidate_stock(phone)
            return result
        except ValueError as exc:
            message = str(exc)
            if _is_not_found_error(message):
                raise StockNotFoundError(f"Product {stock_input.product_id} not found") from exc
            if isinstance(exc, StockValidationError):
                raise
            raise StockValidationError(message) from exc

    def adjust_stock(self, phone: str, product_id: int, quantity: int, reason: str) -> tuple[str, dict]:
        if quantity == 0:
            return "No adjustment needed", {"quantity": 0}

        try:
            payload = {
                "product_id": product_id,
                "quantity": abs(quantity),
                "reason": reason,
                "movement_type": "IN" if quantity > 0 else "OUT",
            }
            result = self.repository.add_stock(payload) if quantity > 0 else self.repository.remove_stock(payload)
            if result.get("status") != "ok":
                raise StockValidationError(result.get("message", "Failed to adjust stock"))

            cache.invalidate_stock(phone)
            return f"Stock adjusted successfully ({'+' if quantity > 0 else ''}{quantity})", result
        except ValueError as exc:
            message = str(exc)
            if _is_not_found_error(message):
                raise StockNotFoundError(f"Product {product_id} not found") from exc
            if isinstance(exc, StockValidationError):
                raise
            raise StockValidationError(message) from exc

    def get_stock_movements(self, phone: str, limit: int, offset: int) -> list[StockMovementResponse]:
        rows = self.repository.list_stock_movements(limit=limit, offset=offset)
        return [self._movement_row_to_response(row) for row in rows]
