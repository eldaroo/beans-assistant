"""Service layer for sales use-cases."""

import logging
from datetime import datetime

from backend import cache
from backend.models.schemas import SaleCreate, SaleItemResponse, SaleResponse
from backend.repositories.sales_repository import SalesRepository

logger = logging.getLogger(__name__)


class SaleNotFoundError(ValueError):
    """Raised when a sale does not exist."""


class SaleValidationError(ValueError):
    """Raised for invalid payload/state operations."""


class SaleConflictError(ValueError):
    """Raised for conflicting operations."""


def _is_not_found_error(message: str) -> bool:
    lowered = message.lower()
    return "not found" in lowered or "no encontrado" in lowered


class SalesService:
    """Orchestrates sales repository, mapping and cache behavior."""

    def __init__(self, repository: SalesRepository | None = None):
        self.repository = repository or SalesRepository()

    @staticmethod
    def _sale_row_to_response(sale_row: dict, items: list[dict]) -> SaleResponse:
        sale_dict = dict(sale_row)

        created_at = sale_dict["created_at"]
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()

        paid_at = sale_dict.get("paid_at")
        if isinstance(paid_at, datetime):
            paid_at = paid_at.isoformat()

        return SaleResponse(
            id=sale_dict["id"],
            sale_number=sale_dict["sale_number"],
            status=sale_dict["status"],
            total_amount_cents=sale_dict["total_amount_cents"],
            customer_name=sale_dict.get("customer_name"),
            created_at=created_at,
            paid_at=paid_at,
            total_amount_usd=round(sale_dict["total_amount_cents"] / 100.0, 2),
            items=[
                SaleItemResponse(
                    id=item_dict["id"],
                    sale_id=item_dict["sale_id"],
                    product_id=item_dict["product_id"],
                    quantity=item_dict["quantity"],
                    unit_price_cents=item_dict["unit_price_cents"],
                    line_total_cents=item_dict["line_total_cents"],
                    unit_price_usd=round(item_dict["unit_price_cents"] / 100.0, 2),
                    line_total_usd=round(item_dict["line_total_cents"] / 100.0, 2),
                    product_name=item_dict.get("product_name"),
                    product_sku=item_dict.get("product_sku"),
                )
                for item in items
                for item_dict in [dict(item)]
            ],
        )

    def list_sales(self, phone: str, limit: int, offset: int) -> list[SaleResponse]:
        rows = self.repository.list_sales(limit=limit, offset=offset)
        return [
            self._sale_row_to_response(row, self.repository.list_sale_items(row["id"]))
            for row in rows
        ]

    def get_sale(self, phone: str, sale_id: int) -> SaleResponse:
        row = self.repository.get_sale_by_id(sale_id)
        if not row:
            raise SaleNotFoundError(f"Sale {sale_id} not found")

        items = self.repository.list_sale_items(sale_id)
        return self._sale_row_to_response(row, items)

    def create_sale(self, phone: str, payload: SaleCreate) -> SaleResponse:
        try:
            sale_data = {
                "status": payload.status,
                "items": [
                    {
                        "product_id": item.product_id,
                        "quantity": item.quantity,
                        **({"unit_price_cents": item.unit_price_cents} if item.unit_price_cents else {}),
                    }
                    for item in payload.items
                ],
                **({"customer_name": payload.customer_name} if payload.customer_name else {}),
            }

            result = self.repository.register_sale(sale_data)
            if result.get("status") != "ok":
                raise SaleValidationError(result.get("message", "Failed to create sale"))

            sale_id = result["sale_id"]
            sale_row = self.repository.get_sale_by_id(sale_id)
            if not sale_row:
                raise SaleNotFoundError(f"Sale {sale_id} not found")

            items = self.repository.list_sale_items(sale_id)

            cache.invalidate_stock(phone)
            cache.invalidate_stats(phone)

            return self._sale_row_to_response(sale_row, items)
        except ValueError as exc:
            message = str(exc)
            if _is_not_found_error(message):
                raise SaleNotFoundError(message) from exc
            if isinstance(exc, SaleValidationError):
                raise
            raise SaleValidationError(message) from exc

    def cancel_sale(self, phone: str, sale_id: int) -> dict:
        try:
            result = self.repository.cancel_sale(sale_id)
            if result.get("status") != "ok":
                raise SaleValidationError(result.get("message", "Failed to cancel sale"))

            cache.invalidate_stock(phone)
            cache.invalidate_stats(phone)
            return result
        except ValueError as exc:
            message = str(exc)
            if _is_not_found_error(message):
                raise SaleNotFoundError(f"Sale {sale_id} not found") from exc
            if isinstance(exc, SaleValidationError):
                raise
            raise SaleConflictError(message) from exc
