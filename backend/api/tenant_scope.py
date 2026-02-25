"""
Shared tenant scoping utilities for API endpoints.
"""
from contextlib import contextmanager
from fastapi import HTTPException, status

from database_config import tenant_context, TenantNotFoundError, TenantContextError


@contextmanager
def tenant_scope(phone: str):
    """
    Ensure the request runs inside the correct tenant DB context.

    Raises:
        HTTPException(404): tenant does not exist
        HTTPException(500): tenant context setup failure
    """
    try:
        with tenant_context(phone):
            yield
    except TenantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except TenantContextError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to configure tenant context: {exc}",
        ) from exc
