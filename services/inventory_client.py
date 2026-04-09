"""Inventory service HTTP client."""
import httpx
from typing import List, Dict, Any
from uuid import UUID
import logging

from config import config

logger = logging.getLogger(__name__)


class InventoryClient:
    """HTTP client for inventory service."""

    def __init__(self):
        self.base_url = config.INVENTORY_SERVICE_URL
        self.timeout = 15.0

    async def reserve_inventory(
        self,
        user_id: UUID,
        items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Reserve inventory for checkout.

        Args:
            user_id: User ID
            items: List of items to reserve [{product_id, variant_id, quantity}]

        Returns:
            Reservation details {reservation_id, expires_at, items}

        Raises:
            httpx.HTTPError: If reservation fails
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Generate a temporary order ID for reservation
                import uuid
                temp_order_id = str(uuid.uuid4())

                response = await client.post(
                    f"{self.base_url}/api/inventory/reserve",
                    json={
                        "order_id": temp_order_id,
                        "items": items
                    }
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"Reserved inventory: {result.get('reservation_id')}")
                return result
        except httpx.HTTPStatusError as e:
            error_detail = e.response.json().get("detail", str(e))
            logger.error(f"Inventory reservation failed: {error_detail}")
            raise Exception(error_detail)
        except Exception as e:
            logger.error(f"Error reserving inventory: {e}")
            raise

    async def confirm_reservation(self, reservation_id: UUID) -> Dict[str, Any]:
        """
        Confirm inventory reservation after successful payment.

        Args:
            reservation_id: Reservation ID

        Returns:
            Confirmation response

        Raises:
            httpx.HTTPError: If confirmation fails
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/inventory/confirm/{reservation_id}"
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"Confirmed reservation: {reservation_id}")
                return result
        except Exception as e:
            logger.error(f"Error confirming reservation {reservation_id}: {e}")
            raise

    async def release_reservation(self, reservation_id: UUID) -> Dict[str, Any]:
        """
        Release inventory reservation (on payment failure or timeout).

        Args:
            reservation_id: Reservation ID

        Returns:
            Release response

        Raises:
            httpx.HTTPError: If release fails
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/inventory/release/{reservation_id}"
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"Released reservation: {reservation_id}")
                return result
        except Exception as e:
            logger.error(f"Error releasing reservation {reservation_id}: {e}")
            raise

    async def release_by_order_id(self, order_id: UUID) -> Dict[str, Any]:
        """
        Release inventory reservation by order ID (for order cancellation).

        Args:
            order_id: Order ID

        Returns:
            Release response {message, order_id}

        Raises:
            httpx.HTTPError: If release fails
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/inventory/release/{order_id}"
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"Released inventory for order: {order_id}")
                return result
        except Exception as e:
            logger.error(f"Error releasing inventory for order {order_id}: {e}")
            raise
