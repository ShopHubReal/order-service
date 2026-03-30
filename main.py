"""Order Service - FastAPI application."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from contextlib import asynccontextmanager

from config import config
from database import init_db
from routers import cart_router, checkout_router, orders_router, health_router
from services.events import EventPublisher

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global event publisher
event_publisher = EventPublisher()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info(f"Starting {config.SERVICE_NAME}...")
    try:
        init_db()
        logger.info("Database initialized")

        # Connect to RabbitMQ
        try:
            await event_publisher.connect()
            logger.info("Connected to RabbitMQ")
        except Exception as e:
            logger.warning(f"Failed to connect to RabbitMQ: {e}. Events will not be published.")

        logger.info(f"{config.SERVICE_NAME} started successfully on port {config.SERVICE_PORT}")
    except Exception as e:
        logger.error(f"Failed to start service: {e}")
        raise

    yield

    # Shutdown
    logger.info(f"Shutting down {config.SERVICE_NAME}...")
    try:
        await event_publisher.disconnect()
        logger.info("Disconnected from RabbitMQ")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# Create FastAPI app
app = FastAPI(
    title="Order Service",
    description="ShopHub Order Service - Shopping cart, checkout, and order management",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_code": "INTERNAL_ERROR"
        }
    )


# Include routers
app.include_router(health_router, tags=["health"])
app.include_router(cart_router, prefix="/api/orders", tags=["cart"])
app.include_router(checkout_router, prefix="/api/orders", tags=["checkout"])
app.include_router(orders_router, prefix="/api/orders", tags=["orders"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=config.SERVICE_PORT,
        reload=False,
        log_level=config.LOG_LEVEL.lower()
    )
