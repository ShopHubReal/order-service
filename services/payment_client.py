"""Payment service HTTP client."""
import httpx
from typing import Dict, Any
from uuid import UUID
import logging

from config import config

logger = logging.getLogger(__name__)


class PaymentClient:
    """HTTP client for payment service."""

    def __init__(self):
        self.base_url = config.PAYMENT_SERVICE_URL
        self.timeout = 10.0

    async def refund_payment(self, payment_id: UUID) -> Dict[str, Any]:
        """
        Refund a payment by reversing the transaction.

        Args:
            payment_id: Payment ID to refund

        Returns:
            Refund details

        Raises:
            httpx.HTTPError: If refund fails
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/payment-ops/reverse-transaction",
                    json={"payment_id": str(payment_id)}
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"Refunded payment {payment_id}")
                return result
        except httpx.HTTPStatusError as e:
            error_detail = e.response.json().get("detail", str(e))
            logger.error(f"Payment refund failed for {payment_id}: {error_detail}")
            raise Exception(f"Failed to refund payment {payment_id}: {error_detail}")
        except Exception as e:
            logger.error(f"Error refunding payment {payment_id}: {e}")
            raise
