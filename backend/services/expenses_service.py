"""Service layer for expenses use-cases."""

from datetime import date, datetime

from backend import cache
from backend.models.schemas import ExpenseCreate, ExpenseResponse
from backend.repositories.expenses_repository import ExpensesRepository


class ExpenseNotFoundError(ValueError):
    """Raised when an expense does not exist."""


class ExpenseValidationError(ValueError):
    """Raised for invalid payload/state operations."""


class ExpenseConflictError(ValueError):
    """Raised for conflicting operations."""


def _is_not_found_error(message: str) -> bool:
    lowered = message.lower()
    return "not found" in lowered or "no encontrado" in lowered


class ExpensesService:
    """Orchestrates expenses repository, mapping and cache behavior."""

    def __init__(self, repository: ExpensesRepository | None = None):
        self.repository = repository or ExpensesRepository()

    @staticmethod
    def _expense_row_to_response(row: dict) -> ExpenseResponse:
        row_dict = dict(row)

        expense_date = row_dict["expense_date"]
        if isinstance(expense_date, datetime):
            expense_date = expense_date.date().isoformat()
        elif isinstance(expense_date, date):
            expense_date = expense_date.isoformat()

        created_at = row_dict["created_at"]
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()

        return ExpenseResponse(
            id=row_dict["id"],
            expense_date=expense_date,
            category=row_dict["category"],
            description=row_dict["description"],
            amount_cents=row_dict["amount_cents"],
            currency=row_dict["currency"],
            created_at=created_at,
            amount_usd=round(row_dict["amount_cents"] / 100.0, 2),
        )

    def list_expenses(self, phone: str, limit: int, offset: int) -> list[ExpenseResponse]:
        rows = self.repository.list_expenses(limit=limit, offset=offset)
        return [self._expense_row_to_response(row) for row in rows]

    def create_expense(self, phone: str, payload: ExpenseCreate) -> ExpenseResponse:
        try:
            expense_data = {
                "amount_cents": payload.amount_cents,
                "description": payload.description,
                "category": payload.category,
                "currency": payload.currency,
                **({"expense_date": payload.expense_date} if payload.expense_date else {}),
            }

            result = self.repository.register_expense(expense_data)
            if result.get("status") != "ok":
                raise ExpenseValidationError(result.get("message", "Failed to create expense"))

            row = self.repository.get_expense_by_id(result["expense_id"])
            if not row:
                raise ExpenseNotFoundError(f"Expense {result['expense_id']} not found")

            cache.invalidate_stats(phone)
            return self._expense_row_to_response(row)
        except ValueError as exc:
            message = str(exc)
            if _is_not_found_error(message):
                raise ExpenseNotFoundError(message) from exc
            if isinstance(exc, ExpenseValidationError):
                raise
            raise ExpenseValidationError(message) from exc

    def cancel_expense(self, phone: str, expense_id: int) -> dict:
        try:
            result = self.repository.cancel_expense(expense_id)
            if result.get("status") != "ok":
                raise ExpenseValidationError(result.get("message", "Failed to cancel expense"))

            cache.invalidate_stats(phone)
            return result
        except ValueError as exc:
            message = str(exc)
            if _is_not_found_error(message):
                raise ExpenseNotFoundError(f"Expense {expense_id} not found") from exc
            if isinstance(exc, ExpenseValidationError):
                raise
            raise ExpenseConflictError(message) from exc
