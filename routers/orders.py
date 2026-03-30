"""Orders router - order management endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Optional
import logging

from database import get_db
from models.schemas import OrderResponse, OrderListResponse, OrderStatusUpdate
from services.order_service import OrderService
from services.events import EventPublisher
from routers.auth import get_current_user, require_admin

logger = logging.getLogger(__name__)

router = APIRouter()


def get_order_service(db: Session = Depends(get_db)) -> OrderService:
    """Dependency to get order service."""
    return OrderService(db)


@router.get("", response_model=List[OrderListResponse])
async def get_user_orders(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service)
):
    """
    Get current user's orders.

    Returns paginated list of orders, newest first.
    """
    try:
        user_id = UUID(current_user["user_id"])
        orders = order_service.get_user_orders(user_id, limit, offset)

        # Convert to list response
        order_list = []
        for order in orders:
            order_list.append(
                OrderListResponse(
                    id=order.id,
                    status=order.status,
                    total=order.total,
                    currency=order.currency,
                    created_at=order.created_at,
                    item_count=len(order.items)
                )
            )
        return order_list
    except Exception as e:
        logger.error(f"Error getting user orders: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get orders"
        )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    current_user: dict = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service)
):
    """
    Get order details.

    User can only view their own orders.
    """
    try:
        user_id = UUID(current_user["user_id"])
        order = order_service.get_order(order_id, user_id)

        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )

        return OrderResponse.model_validate(order)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting order {order_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get order"
        )


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: UUID,
    current_user: dict = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service)
):
    """
    Cancel an order.

    Can only cancel orders that haven't shipped yet.
    """
    try:
        user_id = UUID(current_user["user_id"])
        order = order_service.cancel_order(order_id, user_id)

        # Publish order.cancelled event
        event_publisher = EventPublisher()
        await event_publisher.publish_order_cancelled(order_id)

        return OrderResponse.model_validate(order)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error cancelling order {order_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel order"
        )


# Admin endpoints
@router.get("/all", response_model=List[OrderListResponse], dependencies=[Depends(require_admin)])
async def get_all_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    order_service: OrderService = Depends(get_order_service)
):
    """
    Get all orders (admin only).

    Returns paginated list of all orders, with optional status filter.
    """
    try:
        orders = order_service.get_all_orders(status_filter, limit, offset)

        # Convert to list response
        order_list = []
        for order in orders:
            order_list.append(
                OrderListResponse(
                    id=order.id,
                    status=order.status,
                    total=order.total,
                    currency=order.currency,
                    created_at=order.created_at,
                    item_count=len(order.items)
                )
            )
        return order_list
    except Exception as e:
        logger.error(f"Error getting all orders: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get orders"
        )


@router.put("/{order_id}/status", response_model=OrderResponse, dependencies=[Depends(require_admin)])
async def update_order_status(
    order_id: UUID,
    status_update: OrderStatusUpdate,
    order_service: OrderService = Depends(get_order_service)
):
    """
    Update order status (admin only).

    Allowed statuses: pending, paid, processing, shipped, delivered, cancelled
    """
    try:
        order = order_service.update_order_status(order_id, status_update.status)

        # Publish order.shipped event if status changed to shipped
        if status_update.status == "shipped":
            event_publisher = EventPublisher()
            await event_publisher.publish_order_shipped(
                order_id,
                tracking_number="TRK-" + str(order_id)[:8]  # Mock tracking number
            )

        return OrderResponse.model_validate(order)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating order status {order_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update order status"
        )
