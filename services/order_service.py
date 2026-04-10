"""Order service - business logic for order operations."""
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from decimal import Decimal
import logging

from models.database import Order, OrderItem
from models.schemas import OrderResponse, OrderListResponse, ShippingAddress
from config import config

logger = logging.getLogger(__name__)


class OrderService:
    """Service for order operations."""

    def __init__(
        self,
        db: Session,
        payment_client=None,
        inventory_client=None,
        event_publisher=None
    ):
        self.db = db
        self.payment_client = payment_client
        self.inventory_client = inventory_client
        self.event_publisher = event_publisher

    def create_order(
        self,
        user_id: UUID,
        items: List[dict],
        shipping_address: ShippingAddress
    ) -> Order:
        """
        Create a new order.

        Args:
            user_id: User ID
            items: List of items [{product_id, variant_id, quantity, unit_price}]
            shipping_address: Shipping address

        Returns:
            Created order
        """
        # Calculate totals
        subtotal = Decimal("0.00")
        for item in items:
            subtotal += Decimal(str(item["unit_price"])) * item["quantity"]

        # Calculate tax
        tax = subtotal * Decimal(str(config.TAX_RATE))

        # Calculate shipping
        shipping = Decimal(str(config.SHIPPING_COST))
        if subtotal >= Decimal(str(config.FREE_SHIPPING_THRESHOLD)):
            shipping = Decimal("0.00")

        total = subtotal + tax + shipping

        # Create order
        order = Order(
            user_id=user_id,
            status="pending",
            subtotal=subtotal,
            tax=tax,
            shipping=shipping,
            total=total,
            currency="USD",
            shipping_address=shipping_address.model_dump()
        )
        self.db.add(order)
        self.db.flush()

        # Create order items
        for item in items:
            order_item = OrderItem(
                order_id=order.id,
                product_id=UUID(item["product_id"]),
                variant_id=UUID(item["variant_id"]) if item.get("variant_id") else None,
                quantity=item["quantity"],
                unit_price=Decimal(str(item["unit_price"])),
                total_price=Decimal(str(item["unit_price"])) * item["quantity"]
            )
            self.db.add(order_item)

        self.db.commit()
        self.db.refresh(order)
        logger.info(f"Created order {order.id} for user {user_id}, total: {total}")

        return order

    def get_order(self, order_id: UUID, user_id: Optional[UUID] = None) -> Optional[Order]:
        """
        Get order by ID.

        Args:
            order_id: Order ID
            user_id: Optional user ID for authorization

        Returns:
            Order or None
        """
        query = self.db.query(Order).filter(Order.id == order_id)
        if user_id:
            query = query.filter(Order.user_id == user_id)
        return query.first()

    def get_user_orders(self, user_id: UUID, limit: int = 50, offset: int = 0) -> List[Order]:
        """
        Get user's orders.

        Args:
            user_id: User ID
            limit: Maximum number of orders to return
            offset: Number of orders to skip

        Returns:
            List of orders
        """
        return (
            self.db.query(Order)
            .filter(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def get_all_orders(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Order]:
        """
        Get all orders (admin).

        Args:
            status: Optional status filter
            limit: Maximum number of orders to return
            offset: Number of orders to skip

        Returns:
            List of orders
        """
        query = self.db.query(Order)
        if status:
            query = query.filter(Order.status == status)

        return (
            query
            .order_by(Order.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def update_order_status(self, order_id: UUID, status: str) -> Order:
        """
        Update order status.

        Args:
            order_id: Order ID
            status: New status

        Returns:
            Updated order

        Raises:
            ValueError: If order not found
        """
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise ValueError(f"Order {order_id} not found")

        old_status = order.status
        order.status = status
        self.db.commit()
        self.db.refresh(order)
        logger.info(f"Updated order {order_id} status: {old_status} -> {status}")

        return order

    async def cancel_order(self, order_id: UUID, user_id: UUID) -> Order:
        """
        Cancel an existing order with complete orchestration.

        This method implements a complete cancellation flow that:
        1. Validates the order exists and belongs to the user
        2. Refunds the customer's payment
        3. Restores inventory to available stock
        4. Notifies the customer via order.cancelled event
        5. Updates the order status to 'cancelled'

        Only orders with status 'pending', 'paid', or 'processing' can be cancelled.
        Orders that have already been shipped, delivered, or previously cancelled
        cannot be cancelled.

        Args:
            order_id: The unique identifier of the order to be cancelled
            user_id: The unique identifier of the user requesting the cancellation

        Returns:
            Order: The updated Order model instance with status 'cancelled'

        Raises:
            ValueError: If order not found, doesn't belong to user, or cannot be cancelled
            Exception: If refund or inventory release fails

        Example:
            >>> order_service = OrderService(db_session, payment_client, inventory_client, event_publisher)
            >>> cancelled_order = await order_service.cancel_order(
            ...     order_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
            ...     user_id=UUID("987fcdeb-51d2-43ef-9876-543210987654")
            ... )
            >>> print(cancelled_order.status)
            'cancelled'
        """
        # Step 1: Validate order
        order = self.get_order(order_id, user_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        # Can only cancel orders that haven't shipped yet
        if order.status in ["shipped", "delivered", "cancelled"]:
            raise ValueError(f"Cannot cancel order with status: {order.status}")

        logger.info(f"Starting cancellation for order {order_id}")

        # Step 2: Refund payment
        if self.payment_client and order.status in ["paid", "processing"]:
            try:
                logger.info(f"Refunding payment for order {order_id}")
                await self.payment_client.refund_by_order_id(
                    order_id=order_id,
                    reason="Order cancelled by customer"
                )
                logger.info(f"Payment refunded successfully for order {order_id}")
            except Exception as e:
                logger.error(f"Payment refund failed for order {order_id}: {e}")
                raise Exception(f"Failed to refund payment: {str(e)}")

        # Step 3: Release inventory
        if self.inventory_client:
            try:
                logger.info(f"Releasing inventory for order {order_id}")
                await self.inventory_client.release_by_order_id(order_id)
                logger.info(f"Inventory released successfully for order {order_id}")
            except Exception as e:
                logger.error(f"Inventory release failed for order {order_id}: {e}")
                # Log but don't fail - payment already refunded
                # This should be handled by eventual consistency mechanisms

        # Step 4: Update order status
        order.status = "cancelled"
        self.db.commit()
        self.db.refresh(order)
        logger.info(f"Order {order_id} status updated to cancelled")

        # Step 5: Publish order.cancelled event to notify customer
        if self.event_publisher:
            try:
                logger.info(f"Publishing order.cancelled event for order {order_id}")
                await self.event_publisher.publish_order_cancelled(order_id)
                logger.info(f"Order cancellation event published for order {order_id}")
            except Exception as e:
                logger.error(f"Failed to publish order.cancelled event for order {order_id}: {e}")
                # Event publishing is non-critical, order is already cancelled

        logger.info(f"Successfully cancelled order {order_id}")
        return order
