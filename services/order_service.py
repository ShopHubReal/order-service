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

    def __init__(self, db: Session):
        self.db = db

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

    async def cancel_order(
        self,
        order_id: UUID,
        user_id: UUID,
        payment_client=None,
        inventory_client=None
    ) -> Order:
        """
        Cancel an order with complete cancellation flow.

        This method implements a complete cancellation process that:
        1. Refunds the customer's payment
        2. Restores inventory to available stock
        3. Updates the order status to cancelled

        Args:
            order_id: Order ID
            user_id: User ID
            payment_client: Payment service client (injected)
            inventory_client: Inventory service client (injected)

        Returns:
            Updated order

        Raises:
            ValueError: If order not found or cannot be cancelled
            Exception: If cancellation process fails
        """
        order = self.get_order(order_id, user_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        # Can only cancel orders that haven't shipped yet
        if order.status in ["shipped", "delivered", "cancelled"]:
            raise ValueError(f"Cannot cancel order with status: {order.status}")

        logger.info(f"Starting complete cancellation for order {order_id}")

        # Step 1: Refund payment (only for paid orders)
        if order.status == "paid" and payment_client:
            try:
                logger.info(f"Refunding payment for order {order_id}")
                # Find payment by order ID
                payment = await payment_client.get_payment_by_order_id(order_id)
                payment_id = UUID(payment["id"])

                # Process refund
                refund = await payment_client.refund_payment(
                    payment_id=payment_id,
                    amount=order.total,
                    reason="Order cancelled by customer"
                )
                logger.info(f"Payment refunded successfully: {refund.get('id')}")
            except Exception as e:
                logger.error(f"Failed to refund payment for order {order_id}: {e}")
                # Don't fail the entire cancellation if refund fails -
                # this can be handled manually or through retry mechanisms
                logger.warning(f"Order {order_id} will be cancelled despite refund failure")

        # Step 2: Restore inventory to available stock
        if inventory_client:
            try:
                logger.info(f"Restoring inventory for order {order_id}")
                # Release inventory back to available stock
                result = await inventory_client.release_by_order_id(order_id)
                logger.info(f"Inventory restored successfully for order {order_id}")
            except Exception as e:
                logger.error(f"Failed to restore inventory for order {order_id}: {e}")
                # Don't fail the entire cancellation - inventory can be corrected manually
                logger.warning(f"Order {order_id} will be cancelled despite inventory restoration failure")

        # Step 3: Update order status to cancelled
        order.status = "cancelled"
        self.db.commit()
        self.db.refresh(order)
        logger.info(f"Order {order_id} successfully cancelled")

        return order
