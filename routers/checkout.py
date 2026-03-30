"""Checkout router - checkout flow endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
import logging

from database import get_db
from models.schemas import CheckoutRequest, OrderResponse
from services import (
    CartService,
    OrderService,
    CheckoutService,
    ProductClient,
    InventoryClient,
    PaymentClient,
    EventPublisher,
    CheckoutError,
    InsufficientInventoryError,
    PaymentFailedError
)
from routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


def get_checkout_service(db: Session = Depends(get_db)) -> CheckoutService:
    """Dependency to get checkout service."""
    product_client = ProductClient()
    cart_service = CartService(db, product_client)
    order_service = OrderService(db)
    inventory_client = InventoryClient()
    payment_client = PaymentClient()
    event_publisher = EventPublisher()

    return CheckoutService(
        db=db,
        cart_service=cart_service,
        order_service=order_service,
        inventory_client=inventory_client,
        payment_client=payment_client,
        product_client=product_client,
        event_publisher=event_publisher
    )


@router.post("/checkout", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def checkout(
    request: CheckoutRequest,
    current_user: dict = Depends(get_current_user),
    checkout_service: CheckoutService = Depends(get_checkout_service)
):
    """
    Process checkout.

    Flow:
    1. Validate cart (not empty)
    2. Reserve inventory
    3. Process payment
    4. Create order (if payment succeeds)
    5. Confirm inventory reservation
    6. Publish order.completed event
    7. Clear cart

    If payment fails, inventory reservation is released automatically.

    Returns:
        Created order

    Raises:
        400: Cart is empty or invalid
        402: Payment failed
        409: Insufficient inventory
        500: Checkout failed
    """
    try:
        user_id = UUID(current_user["user_id"])
        order = await checkout_service.process_checkout(user_id, request)
        return order
    except InsufficientInventoryError as e:
        logger.warning(f"Insufficient inventory for user {current_user['user_id']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except PaymentFailedError as e:
        logger.warning(f"Payment failed for user {current_user['user_id']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(e)
        )
    except CheckoutError as e:
        logger.error(f"Checkout error for user {current_user['user_id']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected checkout error for user {current_user['user_id']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Checkout failed. Please try again."
        )
