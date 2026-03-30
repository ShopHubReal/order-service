"""Configuration for Order Service."""
import os
from typing import Optional


class Config:
    """Application configuration."""

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/orders_db"
    )

    # Redis
    REDIS_URL: str = os.getenv(
        "REDIS_URL",
        "redis://localhost:6379/0"
    )

    # RabbitMQ
    RABBITMQ_URL: str = os.getenv(
        "RABBITMQ_URL",
        "amqp://guest:guest@localhost:5672/"
    )

    # Service URLs
    AUTH_SERVICE_URL: str = os.getenv(
        "AUTH_SERVICE_URL",
        "http://auth-service:8006"
    )
    PRODUCT_SERVICE_URL: str = os.getenv(
        "PRODUCT_SERVICE_URL",
        "http://product-service:8001"
    )
    INVENTORY_SERVICE_URL: str = os.getenv(
        "INVENTORY_SERVICE_URL",
        "http://inventory-service:8003"
    )
    PAYMENT_SERVICE_URL: str = os.getenv(
        "PAYMENT_SERVICE_URL",
        "http://payment-service:8005"
    )

    # Application
    SERVICE_NAME: str = "order-service"
    SERVICE_PORT: int = int(os.getenv("SERVICE_PORT", "8004"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Cart settings
    CART_EXPIRY_DAYS: int = int(os.getenv("CART_EXPIRY_DAYS", "30"))

    # Order settings
    TAX_RATE: float = float(os.getenv("TAX_RATE", "0.08"))  # 8% tax
    SHIPPING_COST: float = float(os.getenv("SHIPPING_COST", "9.99"))
    FREE_SHIPPING_THRESHOLD: float = float(os.getenv("FREE_SHIPPING_THRESHOLD", "100.00"))

    # RabbitMQ Exchanges
    ORDERS_EXCHANGE: str = "orders"

    # JWT (for validation)
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")


config = Config()
