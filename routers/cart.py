"""Cart router - shopping cart endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
import logging

from database import get_db
from models.schemas import CartResponse, AddToCartRequest, UpdateCartItemRequest
from services.cart_service import CartService
from services.product_client import ProductClient
from routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


def get_cart_service(db: Session = Depends(get_db)) -> CartService:
    """Dependency to get cart service."""
    product_client = ProductClient()
    return CartService(db, product_client)


@router.get("/cart", response_model=CartResponse)
async def get_cart(
    current_user: dict = Depends(get_current_user),
    cart_service: CartService = Depends(get_cart_service)
):
    """
    Get current user's cart.

    Returns cart with product details and subtotal.
    """
    try:
        user_id = UUID(current_user["user_id"])
        cart = cart_service.get_cart(user_id)
        return cart
    except Exception as e:
        logger.error(f"Error getting cart: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get cart"
        )


@router.post("/cart/items", response_model=CartResponse, status_code=status.HTTP_201_CREATED)
async def add_to_cart(
    request: AddToCartRequest,
    current_user: dict = Depends(get_current_user),
    cart_service: CartService = Depends(get_cart_service)
):
    """
    Add item to cart.

    If item already exists, quantity is incremented.
    """
    try:
        user_id = UUID(current_user["user_id"])
        from models.schemas import CartItem
        cart_item = CartItem(
            product_id=request.product_id,
            variant_id=request.variant_id,
            quantity=request.quantity
        )
        cart = cart_service.add_to_cart(user_id, cart_item)
        return cart
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error adding to cart: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add item to cart"
        )


@router.put("/cart/items/{product_id}", response_model=CartResponse)
async def update_cart_item(
    product_id: UUID,
    request: UpdateCartItemRequest,
    variant_id: UUID = None,
    current_user: dict = Depends(get_current_user),
    cart_service: CartService = Depends(get_cart_service)
):
    """
    Update cart item quantity.

    Use query parameter variant_id if updating a product variant.
    """
    try:
        user_id = UUID(current_user["user_id"])
        cart = cart_service.update_cart_item(user_id, product_id, variant_id, request.quantity)
        return cart
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating cart item: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update cart item"
        )


@router.delete("/cart/items/{product_id}", response_model=CartResponse)
async def remove_from_cart(
    product_id: UUID,
    variant_id: UUID = None,
    current_user: dict = Depends(get_current_user),
    cart_service: CartService = Depends(get_cart_service)
):
    """
    Remove item from cart.

    Use query parameter variant_id if removing a product variant.
    """
    try:
        user_id = UUID(current_user["user_id"])
        cart = cart_service.remove_from_cart(user_id, product_id, variant_id)
        return cart
    except Exception as e:
        logger.error(f"Error removing from cart: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove item from cart"
        )


@router.delete("/cart", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cart(
    current_user: dict = Depends(get_current_user),
    cart_service: CartService = Depends(get_cart_service)
):
    """
    Clear all items from cart.
    """
    try:
        user_id = UUID(current_user["user_id"])
        cart_service.clear_cart(user_id)
    except Exception as e:
        logger.error(f"Error clearing cart: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear cart"
        )
