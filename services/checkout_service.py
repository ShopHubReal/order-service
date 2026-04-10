"""Checkout service - orchestrates the checkout flow with proper error handling."""
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from uuid import UUID
import logging

from models.schemas import CheckoutRequest, OrderResponse, ShippingAddress
from models.database import Order
from services.cart_service import CartService
from services.order_service import OrderService
from services.inventory_client import InventoryClient
from services.payment_client import PaymentClient
from services.product_client import ProductClient
from services.events import EventPublisher

logger = logging.getLogger(__name__)


class CheckoutError(Exception):
    """Base exception for checkout errors."""
    pass


class InsufficientInventoryError(CheckoutError):
    """Exception raised when inventory is insufficient."""
    pass


class PaymentFailedError(CheckoutError):
    """Exception raised when payment fails."""
    pass


class CheckoutService:
    """Service for checkout flow orchestration."""

    def __init__(
        self,
        db: Session,
        cart_service: CartService,
        order_service: OrderService,
        inventory_client: InventoryClient,
        payment_client: PaymentClient,
        product_client: ProductClient,
        event_publisher: EventPublisher
    ):
        self.db = db
        self.cart_service = cart_service
        self.order_service = order_service
        self.inventory_client = inventory_client
        self.payment_client = payment_client
        self.product_client = product_client
        self.event_publisher = event_publisher

    async def process_checkout(
        self,
        user_id: UUID,
        checkout_request: CheckoutRequest
    ) -> OrderResponse:
        """
        Process checkout with proper error handling and rollback.

        Flow:
        1. Validate cart (not empty)
        2. Reserve inventory
        3. Process payment
        4. If payment succeeds:
           - Create order
           - Confirm inventory reservation
           - Publish order.completed event
           - Clear cart
        5. If payment fails:
           - Release inventory reservation
           - Raise error

        Args:
            user_id: User ID
            checkout_request: Checkout request

        Returns:
            Created order

        Raises:
            CheckoutError: If checkout fails
        """
        reservation_id: Optional[UUID] = None
        order: Optional[Order] = None

        try:
            # Step 1: Validate cart
            cart = self.cart_service.get_cart(user_id)
            if not cart or not cart.items:
                raise CheckoutError("Cart is empty")

            logger.info(f"Processing checkout for user {user_id} with {len(cart.items)} items")

            # Prepare items for reservation
            reserve_items = []
            order_items = []

            for cart_item in cart.items:
                # Fetch fresh product details
                product = self.product_client.get_product(str(cart_item.product_id))
                if not product:
                    raise CheckoutError(f"Product {cart_item.product_id} not found")

                if product.status != "active":
                    raise CheckoutError(f"Product {product.name} is no longer available")

                reserve_items.append({
                    "product_id": str(cart_item.product_id),
                    "variant_id": str(cart_item.variant_id) if cart_item.variant_id else None,
                    "quantity": cart_item.quantity
                })

                order_items.append({
                    "product_id": str(cart_item.product_id),
                    "variant_id": str(cart_item.variant_id) if cart_item.variant_id else None,
                    "quantity": cart_item.quantity,
                    "unit_price": str(product.price)
                })

            # Step 2: Reserve inventory
            logger.info(f"Reserving inventory for user {user_id}")
            try:
                reservation = await self.inventory_client.reserve_inventory(
                    user_id=user_id,
                    items=reserve_items
                )
                reservation_id = reservation["reservation_id"]
                logger.info(f"Inventory reserved: {reservation_id}")
            except Exception as e:
                logger.error(f"Inventory reservation failed: {e}")
                raise InsufficientInventoryError(f"Inventory reservation failed: {str(e)}")

            # Step 3: Process payment
            logger.info(f"Processing payment for user {user_id}, amount: {cart.subtotal}")
            try:
                payment = await self.payment_client.charge_payment(
                    user_id=user_id,
                    amount=cart.subtotal,
                    payment_method_id=checkout_request.payment_method_id
                )
                logger.info(f"Payment successful: {payment['id']}")
            except Exception as e:
                logger.error(f"Payment failed: {e}")
                # Release inventory reservation
                if reservation_id:
                    try:
                        await self.inventory_client.release_reservation(reservation_id)
                        logger.info(f"Released inventory reservation: {reservation_id}")
                    except Exception as release_error:
                        logger.error(f"Failed to release reservation {reservation_id}: {release_error}")

                raise PaymentFailedError(f"Payment failed: {str(e)}")

            # Step 4: Create order (payment succeeded)
            logger.info(f"Creating order for user {user_id}")
            order = self.order_service.create_order(
                user_id=user_id,
                items=order_items,
                shipping_address=checkout_request.shipping_address,
                payment_id=UUID(payment['id'])  # Store payment ID for refunds
            )

            # Update order status to paid
            order = self.order_service.update_order_status(order.id, "paid")

            # Step 5: Confirm inventory reservation
            try:
                await self.inventory_client.confirm_reservation(reservation_id)
                logger.info(f"Confirmed inventory reservation: {reservation_id}")
            except Exception as e:
                logger.error(f"Failed to confirm reservation {reservation_id}: {e}")
                # Order already created, but log the error
                # This should be handled by eventual consistency mechanisms

            # Step 6: Publish order.completed event
            try:
                await self.event_publisher.publish_order_completed(
                    order_id=order.id,
                    user_id=user_id,
                    items=order_items,
                    total=float(order.total)
                )
                logger.info(f"Published order.completed event for order {order.id}")
            except Exception as e:
                logger.error(f"Failed to publish order.completed event: {e}")
                # Order created successfully, event publishing is non-critical

            # Step 7: Clear cart
            self.cart_service.clear_cart(user_id)
            logger.info(f"Cleared cart for user {user_id}")

            # Return order response
            return OrderResponse.model_validate(order)

        except (CheckoutError, InsufficientInventoryError, PaymentFailedError):
            # Re-raise checkout-specific errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error during checkout: {e}")
            # If we have a reservation, try to release it
            if reservation_id:
                try:
                    await self.inventory_client.release_reservation(reservation_id)
                    logger.info(f"Released inventory reservation: {reservation_id}")
                except Exception as release_error:
                    logger.error(f"Failed to release reservation {reservation_id}: {release_error}")

            raise CheckoutError(f"Checkout failed: {str(e)}")
