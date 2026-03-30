"""Pydantic schemas for Order Service."""
from pydantic import BaseModel, Field, UUID4, EmailStr
from typing import Optional, List
from decimal import Decimal
from datetime import datetime


# Shipping Address Schemas
class ShippingAddress(BaseModel):
    """Shipping address schema."""

    street: str = Field(..., min_length=1, max_length=255)
    city: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=2, max_length=50)
    postal_code: str = Field(..., min_length=1, max_length=20)
    country: str = Field(..., min_length=2, max_length=2)  # ISO 3166-1 alpha-2


# Cart Schemas
class CartItem(BaseModel):
    """Cart item input schema."""

    product_id: UUID4
    variant_id: Optional[UUID4] = None
    quantity: int = Field(..., gt=0)


class CartItemDetail(BaseModel):
    """Cart item with product details."""

    product_id: UUID4
    variant_id: Optional[UUID4] = None
    quantity: int
    product_name: str
    product_price: Decimal
    image_url: Optional[str] = None
    total: Decimal


class CartResponse(BaseModel):
    """Cart response schema."""

    user_id: UUID4
    items: List[CartItemDetail]
    subtotal: Decimal
    item_count: int

    class Config:
        from_attributes = True


class AddToCartRequest(BaseModel):
    """Request to add item to cart."""

    product_id: UUID4
    variant_id: Optional[UUID4] = None
    quantity: int = Field(..., gt=0)


class UpdateCartItemRequest(BaseModel):
    """Request to update cart item quantity."""

    quantity: int = Field(..., gt=0)


# Checkout Schemas
class CheckoutRequest(BaseModel):
    """Checkout request schema."""

    shipping_address: ShippingAddress
    payment_method_id: str = Field(..., min_length=1)  # Stripe payment method ID


# Order Schemas
class OrderItemResponse(BaseModel):
    """Order item response schema."""

    id: UUID4
    product_id: UUID4
    variant_id: Optional[UUID4]
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    """Order response schema."""

    id: UUID4
    user_id: UUID4
    status: str
    items: List[OrderItemResponse]
    subtotal: Decimal
    tax: Decimal
    shipping: Decimal
    total: Decimal
    currency: str
    shipping_address: Optional[dict]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    """Order list response schema."""

    id: UUID4
    status: str
    total: Decimal
    currency: str
    created_at: datetime
    item_count: int

    class Config:
        from_attributes = True


class OrderStatusUpdate(BaseModel):
    """Order status update schema (admin)."""

    status: str = Field(..., pattern="^(pending|paid|processing|shipped|delivered|cancelled)$")


# Product detail schema (from product service)
class ProductDetail(BaseModel):
    """Product details from product service."""

    id: UUID4
    name: str
    price: Decimal
    image_urls: List[str] = []
    status: str


# Error schemas
class ErrorResponse(BaseModel):
    """Error response schema."""

    detail: str
    error_code: Optional[str] = None


# Health check
class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    timestamp: datetime
