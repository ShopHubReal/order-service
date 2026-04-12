"""Order service - business logic for order operations."""
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from decimal import Decimal
import logging
import httpx

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
        shipping_address: ShippingAddress,
        payment_id: UUID = None
    ) -> Order:
        """
        Create a new order.

        Args:
            user_id: User ID
            items: List of items [{product_id, variant_id, quantity, unit_price}]
            shipping_address: Shipping address
            payment_id: Optional payment ID from payment service

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
            payment_id=payment_id,
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
        Cancel an order and refund payment if applicable.

        Args:
            order_id: Order ID
            user_id: User ID

        Returns:
            Updated order

        Raises:
            ValueError: If order not found or cannot be cancelled
            httpx.HTTPError: If payment refund fails
        """
        order = self.get_order(order_id, user_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        # Can only cancel orders that haven't shipped yet
        if order.status in ["shipped", "delivered", "cancelled"]:
            raise ValueError(f"Cannot cancel order with status: {order.status}")

        # Refund payment if payment ID exists
        if order.payment_id:
            await self._refund_payment(order.payment_id, order.total)

        order.status = "cancelled"
        self.db.commit()
        self.db.refresh(order)
        logger.info(f"Cancelled order {order_id} with payment refund")

        return order

    async def _refund_payment(self, payment_id: UUID, amount: Decimal) -> None:
        """
        Refund payment via payment service.

        Args:
            payment_id: Payment ID to refund
            amount: Amount to refund

        Raises:
            httpx.HTTPError: If refund request fails
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{config.PAYMENT_SERVICE_URL}/api/payments/{payment_id}/refund",
                    json={"amount": str(amount), "reason": "Order cancellation"}
                )
                response.raise_for_status()
                logger.info(f"Refunded payment {payment_id}, amount: {amount}")
        except httpx.HTTPStatusError as e:
            logger.error(f"Payment refund failed for {payment_id}: {e.response.text}")
            raise ValueError(f"Payment refund failed: {e.response.text}")
        except Exception as e:
            logger.error(f"Error refunding payment {payment_id}: {e}")
            raise
