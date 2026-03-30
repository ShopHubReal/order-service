"""Payment service HTTP client."""
import httpx
from typing import Dict, Any
from uuid import UUID
from decimal import Decimal
import logging

from config import config

logger = logging.getLogger(__name__)


class PaymentClient:
    """HTTP client for payment service."""

    def __init__(self):
        self.base_url = config.PAYMENT_SERVICE_URL
        self.timeout = 30.0  # Longer timeout for payment processing

    async def charge_payment(
        self,
        user_id: UUID,
        amount: Decimal,
        payment_method_id: str,
        order_id: UUID = None
    ) -> Dict[str, Any]:
        """
        Charge payment via payment service.

        Args:
            user_id: User ID
            amount: Amount to charge
            payment_method_id: Stripe payment method ID
            order_id: Optional order ID (for reference)

        Returns:
            Payment details {id, status, stripe_payment_intent_id}

        Raises:
            httpx.HTTPError: If payment fails
        """
        try:
            # Generate temporary order ID if not provided
            if order_id is None:
                import uuid
                order_id = uuid.uuid4()

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/payments/charge",
                    json={
                        "order_id": str(order_id),
                        "user_id": str(user_id),
                        "amount": str(amount),
                        "currency": "USD",
                        "payment_method_id": payment_method_id
                    }
                )
                response.raise_for_status()
                result = response.json()

                if result.get("status") != "succeeded":
                    raise Exception(f"Payment failed with status: {result.get('status')}")

                logger.info(f"Payment successful: {result.get('id')}")
                return result
        except httpx.HTTPStatusError as e:
            error_detail = e.response.json().get("detail", str(e))
            logger.error(f"Payment failed: {error_detail}")
            raise Exception(error_detail)
        except Exception as e:
            logger.error(f"Error processing payment: {e}")
            raise
