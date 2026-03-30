"""Auth service HTTP client for JWT validation."""
import httpx
from typing import Optional, Dict
from uuid import UUID
import logging

from config import config

logger = logging.getLogger(__name__)


class AuthClient:
    """HTTP client for auth service."""

    def __init__(self):
        self.base_url = config.AUTH_SERVICE_URL
        self.timeout = 5.0

    async def validate_token(self, token: str) -> Optional[Dict[str, any]]:
        """
        Validate JWT token via auth service.

        Args:
            token: JWT token

        Returns:
            Validation result {valid, user_id, role} or None

        Raises:
            httpx.HTTPError: If validation request fails
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/auth/validate",
                    json={"token": token}
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in [401, 403]:
                logger.warning(f"Token validation failed: {e}")
                return None
            logger.error(f"Auth service error: {e}")
            raise
        except Exception as e:
            logger.error(f"Error validating token: {e}")
            raise
