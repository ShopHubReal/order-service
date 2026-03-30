"""RabbitMQ event publisher for order events."""
import aio_pika
import json
from typing import List, Dict, Any
from uuid import UUID
import logging

from config import config

logger = logging.getLogger(__name__)


class EventPublisher:
    """RabbitMQ event publisher."""

    def __init__(self):
        self.rabbitmq_url = config.RABBITMQ_URL
        self.exchange_name = config.ORDERS_EXCHANGE
        self.connection = None
        self.channel = None
        self.exchange = None

    async def connect(self):
        """Connect to RabbitMQ."""
        try:
            self.connection = await aio_pika.connect_robust(self.rabbitmq_url)
            self.channel = await self.connection.channel()
            self.exchange = await self.channel.declare_exchange(
                self.exchange_name,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            logger.info(f"Connected to RabbitMQ: {self.exchange_name}")
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise

    async def disconnect(self):
        """Disconnect from RabbitMQ."""
        try:
            if self.connection:
                await self.connection.close()
                logger.info("Disconnected from RabbitMQ")
        except Exception as e:
            logger.error(f"Error disconnecting from RabbitMQ: {e}")

    async def publish_event(self, routing_key: str, payload: Dict[str, Any]):
        """
        Publish event to RabbitMQ.

        Args:
            routing_key: Routing key (e.g., 'order.completed')
            payload: Event payload
        """
        if not self.exchange:
            await self.connect()

        try:
            message = aio_pika.Message(
                body=json.dumps(payload, default=str).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )
            await self.exchange.publish(message, routing_key=routing_key)
            logger.info(f"Published event: {routing_key}")
        except Exception as e:
            logger.error(f"Failed to publish event {routing_key}: {e}")
            raise

    async def publish_order_created(self, order_id: UUID, user_id: UUID, total: float):
        """Publish order.created event."""
        await self.publish_event(
            "order.created",
            {
                "event": "order.created",
                "order_id": str(order_id),
                "user_id": str(user_id),
                "total": total
            }
        )

    async def publish_order_completed(
        self,
        order_id: UUID,
        user_id: UUID,
        items: List[Dict[str, Any]],
        total: float
    ):
        """Publish order.completed event."""
        await self.publish_event(
            "order.completed",
            {
                "event": "order.completed",
                "order_id": str(order_id),
                "user_id": str(user_id),
                "items": items,
                "total": total
            }
        )

    async def publish_order_cancelled(self, order_id: UUID):
        """Publish order.cancelled event."""
        await self.publish_event(
            "order.cancelled",
            {
                "event": "order.cancelled",
                "order_id": str(order_id)
            }
        )

    async def publish_order_shipped(self, order_id: UUID, tracking_number: str):
        """Publish order.shipped event."""
        await self.publish_event(
            "order.shipped",
            {
                "event": "order.shipped",
                "order_id": str(order_id),
                "tracking_number": tracking_number
            }
        )
