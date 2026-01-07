"""
Pydantic schemas for API request/response validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ============================================================================
# TENANT SCHEMAS
# ============================================================================

class TenantCreate(BaseModel):
    """Schema for creating a new tenant."""
    phone_number: str = Field(..., description="Phone number in international format (e.g., +5491153695627)")
    business_name: str = Field(..., description="Business name")
    currency: str = Field(default="USD", description="Currency code (USD, AUD, etc.)")
    language: str = Field(default="es", description="Language code (es, en)")


class TenantResponse(BaseModel):
    """Schema for tenant response."""
    phone_number: str
    business_name: str
    currency: str
    language: str
    created_at: str
    status: str

    class Config:
        from_attributes = True


class TenantStats(BaseModel):
    """Schema for tenant statistics."""
    products_count: int
    sales_count: int
    revenue_usd: float
    profit_usd: float
    stock_total: int


# ============================================================================
# PRODUCT SCHEMAS
# ============================================================================

class ProductCreate(BaseModel):
    """Schema for creating a new product."""
    sku: str = Field(..., description="Unique SKU code")
    name: str = Field(..., description="Product name")
    description: Optional[str] = Field(None, description="Product description")
    unit_cost_cents: int = Field(..., description="Production cost in cents", ge=0)
    unit_price_cents: int = Field(..., description="Selling price in cents", ge=0)


class ProductUpdate(BaseModel):
    """Schema for updating a product."""
    sku: Optional[str] = Field(None, description="Unique SKU code")
    name: Optional[str] = Field(None, description="Product name")
    description: Optional[str] = Field(None, description="Product description")
    unit_cost_cents: Optional[int] = Field(None, description="Production cost in cents", ge=0)
    unit_price_cents: Optional[int] = Field(None, description="Selling price in cents", ge=0)


class ProductResponse(BaseModel):
    """Schema for product response."""
    id: int
    sku: str
    name: str
    description: Optional[str]
    unit_cost_cents: int
    unit_price_cents: int
    is_active: int
    created_at: str

    # Computed fields
    unit_cost_usd: Optional[float] = None
    unit_price_usd: Optional[float] = None

    class Config:
        from_attributes = True


# ============================================================================
# SALE SCHEMAS
# ============================================================================

class SaleItemInput(BaseModel):
    """Schema for a sale item (input)."""
    product_id: int = Field(..., description="Product ID")
    quantity: int = Field(..., description="Quantity to sell", gt=0)
    unit_price_cents: Optional[int] = Field(None, description="Custom unit price (overrides catalog price)", ge=0)


class SaleCreate(BaseModel):
    """Schema for creating a new sale."""
    status: str = Field(default="PAID", description="Sale status: PAID, PENDING, CANCELLED")
    items: List[SaleItemInput] = Field(..., description="List of items to sell")
    customer_name: Optional[str] = Field(None, description="Customer name (optional)")


class SaleItemResponse(BaseModel):
    """Schema for sale item response."""
    id: int
    sale_id: int
    product_id: int
    quantity: int
    unit_price_cents: int
    line_total_cents: int

    # Computed fields
    unit_price_usd: Optional[float] = None
    line_total_usd: Optional[float] = None
    product_name: Optional[str] = None
    product_sku: Optional[str] = None

    class Config:
        from_attributes = True


class SaleResponse(BaseModel):
    """Schema for sale response."""
    id: int
    sale_number: str
    status: str
    total_amount_cents: int
    customer_name: Optional[str]
    created_at: str
    paid_at: Optional[str]

    # Computed fields
    total_amount_usd: Optional[float] = None
    items: List[SaleItemResponse] = []

    class Config:
        from_attributes = True


# ============================================================================
# EXPENSE SCHEMAS
# ============================================================================

class ExpenseCreate(BaseModel):
    """Schema for creating a new expense."""
    amount_cents: int = Field(..., description="Expense amount in cents", gt=0)
    description: str = Field(..., description="Expense description")
    category: str = Field(default="GENERAL", description="Expense category (SHIPPING, GENERAL, SUPPLIES, etc.)")
    expense_date: Optional[str] = Field(None, description="Expense date (YYYY-MM-DD, defaults to today)")
    currency: str = Field(default="USD", description="Currency code")


class ExpenseResponse(BaseModel):
    """Schema for expense response."""
    id: int
    expense_date: str
    category: str
    description: str
    amount_cents: int
    currency: str
    created_at: str

    # Computed fields
    amount_usd: Optional[float] = None

    class Config:
        from_attributes = True


# ============================================================================
# STOCK SCHEMAS
# ============================================================================

class StockAddInput(BaseModel):
    """Schema for adding stock to a product."""
    product_id: int = Field(..., description="Product ID")
    quantity: int = Field(..., description="Quantity to add", gt=0)
    reason: Optional[str] = Field("Stock update", description="Reason for stock movement")
    movement_type: str = Field(default="IN", description="Movement type: IN, OUT, ADJUSTMENT")


class StockMovementResponse(BaseModel):
    """Schema for stock movement response."""
    id: int
    product_id: int
    movement_type: str
    quantity: int
    reason: Optional[str]
    reference: Optional[str]
    occurred_at: str
    created_at: str

    # Computed fields
    product_name: Optional[str] = None
    product_sku: Optional[str] = None

    class Config:
        from_attributes = True


class StockCurrentResponse(BaseModel):
    """Schema for current stock response."""
    product_id: int
    sku: str
    name: str
    stock_qty: int

    # Computed fields
    unit_price_cents: Optional[int] = None
    unit_price_usd: Optional[float] = None

    class Config:
        from_attributes = True


# ============================================================================
# ANALYTICS SCHEMAS
# ============================================================================

class RevenueResponse(BaseModel):
    """Schema for revenue analytics."""
    total_revenue_cents: int
    revenue_usd: float


class ProfitResponse(BaseModel):
    """Schema for profit analytics."""
    profit_usd: float


class SalesSummaryItem(BaseModel):
    """Schema for a daily sales summary item."""
    day: str
    paid_sales_count: int
    paid_revenue_cents: int

    # Computed fields
    paid_revenue_usd: Optional[float] = None

    class Config:
        from_attributes = True


# ============================================================================
# GENERIC RESPONSE SCHEMAS
# ============================================================================

class SuccessResponse(BaseModel):
    """Generic success response."""
    status: str = "ok"
    message: Optional[str] = None
    data: Optional[dict] = None


class ErrorResponse(BaseModel):
    """Generic error response."""
    status: str = "error"
    message: str
    code: Optional[str] = None
