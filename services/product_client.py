"""Product service HTTP client."""
import httpx
from typing import Optional
import logging

from config import config
from models.schemas import ProductDetail

logger = logging.getLogger(__name__)


class ProductClient:
    """HTTP client for product service."""

    def __init__(self):
        self.base_url = config.PRODUCT_SERVICE_URL
        self.timeout = 10.0

    def get_product(self, product_id: str) -> Optional[ProductDetail]:
        """
        Get product details from product service.

        Args:
            product_id: Product ID

        Returns:
            Product details or None if not found
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(f"{self.base_url}/api/products/{product_id}")
                response.raise_for_status()
                return ProductDetail(**response.json())
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Product {product_id} not found")
                return None
            logger.error(f"HTTP error getting product {product_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting product {product_id}: {e}")
            raise
