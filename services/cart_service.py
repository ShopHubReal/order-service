"""Cart service - business logic for cart operations."""
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
import logging

from models.database import Cart
from models.schemas import CartItem, CartItemDetail, CartResponse
from services.product_client import ProductClient
from decimal import Decimal

logger = logging.getLogger(__name__)


class CartService:
    """Service for cart operations."""

    def __init__(self, db: Session, product_client: ProductClient):
        self.db = db
        self.product_client = product_client

    def get_or_create_cart(self, user_id: UUID) -> Cart:
        """Get or create cart for user."""
        cart = self.db.query(Cart).filter(Cart.user_id == user_id).first()
        if not cart:
            cart = Cart(user_id=user_id, items=[])
            self.db.add(cart)
            self.db.commit()
            self.db.refresh(cart)
            logger.info(f"Created new cart for user {user_id}")
        return cart

    def get_cart(self, user_id: UUID) -> Optional[CartResponse]:
        """Get cart with product details."""
        cart = self.get_or_create_cart(user_id)

        if not cart.items:
            return CartResponse(
                user_id=user_id,
                items=[],
                subtotal=Decimal("0.00"),
                item_count=0
            )

        # Fetch product details for all items
        cart_items_with_details = []
        subtotal = Decimal("0.00")

        for item in cart.items:
            try:
                product = self.product_client.get_product(item["product_id"])
                if not product:
                    logger.warning(f"Product {item['product_id']} not found, skipping")
                    continue

                item_total = product.price * item["quantity"]
                cart_items_with_details.append(
                    CartItemDetail(
                        product_id=UUID(item["product_id"]),
                        variant_id=UUID(item["variant_id"]) if item.get("variant_id") else None,
                        quantity=item["quantity"],
                        product_name=product.name,
                        product_price=product.price,
                        image_url=product.image_urls[0] if product.image_urls else None,
                        total=item_total
                    )
                )
                subtotal += item_total
            except Exception as e:
                logger.error(f"Error fetching product {item['product_id']}: {e}")
                continue

        return CartResponse(
            user_id=user_id,
            items=cart_items_with_details,
            subtotal=subtotal,
            item_count=len(cart_items_with_details)
        )

    def add_to_cart(self, user_id: UUID, item: CartItem) -> CartResponse:
        """Add item to cart."""
        cart = self.get_or_create_cart(user_id)

        # Check if item already exists in cart
        items = cart.items or []
        item_found = False

        for existing_item in items:
            if (existing_item["product_id"] == str(item.product_id) and
                existing_item.get("variant_id") == (str(item.variant_id) if item.variant_id else None)):
                # Update quantity
                existing_item["quantity"] += item.quantity
                item_found = True
                break

        if not item_found:
            # Add new item
            items.append({
                "product_id": str(item.product_id),
                "variant_id": str(item.variant_id) if item.variant_id else None,
                "quantity": item.quantity
            })

        cart.items = items
        self.db.commit()
        self.db.refresh(cart)
        logger.info(f"Added item to cart for user {user_id}")

        return self.get_cart(user_id)

    def update_cart_item(self, user_id: UUID, product_id: UUID, variant_id: Optional[UUID], quantity: int) -> CartResponse:
        """Update cart item quantity."""
        cart = self.get_or_create_cart(user_id)
        items = cart.items or []

        item_found = False
        for item in items:
            if (item["product_id"] == str(product_id) and
                item.get("variant_id") == (str(variant_id) if variant_id else None)):
                item["quantity"] = quantity
                item_found = True
                break

        if not item_found:
            raise ValueError("Item not found in cart")

        cart.items = items
        self.db.commit()
        self.db.refresh(cart)
        logger.info(f"Updated cart item for user {user_id}")

        return self.get_cart(user_id)

    def remove_from_cart(self, user_id: UUID, product_id: UUID, variant_id: Optional[UUID]) -> CartResponse:
        """Remove item from cart."""
        cart = self.get_or_create_cart(user_id)
        items = cart.items or []

        items = [
            item for item in items
            if not (item["product_id"] == str(product_id) and
                   item.get("variant_id") == (str(variant_id) if variant_id else None))
        ]

        cart.items = items
        self.db.commit()
        self.db.refresh(cart)
        logger.info(f"Removed item from cart for user {user_id}")

        return self.get_cart(user_id)

    def clear_cart(self, user_id: UUID) -> None:
        """Clear all items from cart."""
        cart = self.get_or_create_cart(user_id)
        cart.items = []
        self.db.commit()
        logger.info(f"Cleared cart for user {user_id}")
