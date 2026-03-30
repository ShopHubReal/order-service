"""Auth dependencies for route protection."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict
import logging

from services.auth_client import AuthClient

logger = logging.getLogger(__name__)

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, any]:
    """
    Validate JWT token and get current user.

    Args:
        credentials: HTTP authorization credentials

    Returns:
        User info dict {user_id, email, role}

    Raises:
        HTTPException: If token is invalid
    """
    token = credentials.credentials
    auth_client = AuthClient()

    try:
        result = await auth_client.validate_token(token)

        if not result or not result.get("valid"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"}
            )

        return {
            "user_id": result.get("user_id"),
            "email": result.get("email"),
            "role": result.get("role")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def require_admin(current_user: Dict[str, any] = Depends(get_current_user)) -> Dict[str, any]:
    """
    Require admin role.

    Args:
        current_user: Current user from get_current_user

    Returns:
        User info dict

    Raises:
        HTTPException: If user is not admin
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return current_user
