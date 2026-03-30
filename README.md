# Order Service

ShopHub Order Service - Shopping cart, checkout flow, and order management for the ShopHub e-commerce platform.

## Overview

The Order Service is a FastAPI microservice that handles:
- **Shopping cart management**: Add, update, remove items
- **Checkout flow**: Inventory reservation → Payment processing → Order creation
- **Order management**: View orders, cancel orders, update status (admin)
- **Event publishing**: Order lifecycle events via RabbitMQ

## Architecture

### Key Features

1. **Production-grade checkout flow** with proper error handling:
   - Inventory reservation with automatic rollback on payment failure
   - Payment processing via payment service
   - Atomic order creation
   - Event-driven notifications

2. **Service dependencies**:
   - `auth-service`: JWT validation
   - `product-service`: Product details
   - `inventory-service`: Stock reservation/confirmation
   - `payment-service`: Payment processing

3. **Event publishing** (RabbitMQ):
   - `order.created`: Order created
   - `order.completed`: Order paid and confirmed
   - `order.cancelled`: Order cancelled
   - `order.shipped`: Order shipped (with tracking)

## Tech Stack

- **FastAPI 0.109**: Web framework
- **SQLAlchemy 2.0**: ORM
- **PostgreSQL**: Database (`orders_db`)
- **RabbitMQ**: Message broker
- **Pydantic**: Data validation
- **httpx**: Async HTTP client

## Database Schema

### Tables

**orders**:
- `id` (UUID, primary key)
- `user_id` (UUID, indexed)
- `status` (varchar: pending, paid, processing, shipped, delivered, cancelled)
- `subtotal`, `tax`, `shipping`, `total` (numeric)
- `currency` (varchar)
- `shipping_address` (JSONB)
- `created_at`, `updated_at` (timestamp)

**order_items**:
- `id` (UUID, primary key)
- `order_id` (UUID, foreign key → orders)
- `product_id`, `variant_id` (UUID)
- `quantity` (int)
- `unit_price`, `total_price` (numeric)
- `created_at` (timestamp)

**carts**:
- `id` (UUID, primary key)
- `user_id` (UUID, unique, indexed)
- `items` (JSONB: array of {product_id, variant_id, quantity})
- `updated_at` (timestamp)

## API Endpoints

### Cart Endpoints

```
GET    /api/orders/cart                    # Get cart
POST   /api/orders/cart/items              # Add item to cart
PUT    /api/orders/cart/items/{id}         # Update item quantity
DELETE /api/orders/cart/items/{id}         # Remove item
DELETE /api/orders/cart                    # Clear cart
```

### Checkout

```
POST   /api/orders/checkout                # Process checkout
```

### Orders

```
GET    /api/orders                         # Get user's orders
GET    /api/orders/{order_id}              # Get order details
POST   /api/orders/{order_id}/cancel       # Cancel order
```

### Admin Endpoints

```
GET    /api/orders/all?status={status}     # Get all orders (admin)
PUT    /api/orders/{order_id}/status       # Update order status (admin)
```

### Health

```
GET    /health                             # Health check
GET    /                                   # Root info
```

## Checkout Flow

The checkout process follows a careful orchestration with proper error handling:

```python
1. Validate cart (not empty)
2. Reserve inventory:
   - Call inventory-service: POST /api/inventory/reserve
   - Get reservation_id and expiration time
3. Process payment:
   - Call payment-service: POST /api/payments/charge
   - If FAILS → Release inventory reservation → Raise error
4. Create order (payment succeeded):
   - Create order in database with status="pending"
   - Update status to "paid"
5. Confirm inventory reservation:
   - Call inventory-service: POST /api/inventory/confirm/{reservation_id}
6. Publish order.completed event (RabbitMQ)
7. Clear cart
8. Return order
```

### Error Handling

- **Insufficient inventory**: Returns 409 Conflict, no reservation created
- **Payment failed**: Returns 402 Payment Required, releases inventory reservation
- **General checkout error**: Returns 400/500, releases inventory if reserved

## Configuration

Environment variables (see `config.py`):

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/orders_db

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# Service URLs
AUTH_SERVICE_URL=http://auth-service:8006
PRODUCT_SERVICE_URL=http://product-service:8001
INVENTORY_SERVICE_URL=http://inventory-service:8003
PAYMENT_SERVICE_URL=http://payment-service:8005

# Application
SERVICE_PORT=8004
LOG_LEVEL=INFO

# Order settings
TAX_RATE=0.08
SHIPPING_COST=9.99
FREE_SHIPPING_THRESHOLD=100.00
```

## Running Locally

### Prerequisites

- Python 3.11+
- PostgreSQL
- RabbitMQ

### Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/orders_db
export RABBITMQ_URL=amqp://guest:guest@localhost:5672/
export AUTH_SERVICE_URL=http://localhost:8006
export PRODUCT_SERVICE_URL=http://localhost:8001
export INVENTORY_SERVICE_URL=http://localhost:8003
export PAYMENT_SERVICE_URL=http://localhost:8005

# Run service
python main.py
```

Service will be available at `http://localhost:8004`

### Docker

```bash
# Build image
docker build -t order-service:latest .

# Run container
docker run -p 8004:8004 \
  -e DATABASE_URL=postgresql://... \
  -e RABBITMQ_URL=amqp://... \
  order-service:latest
```

## Development

### Project Structure

```
order-service/
├── main.py                     # FastAPI app entry point
├── config.py                   # Configuration
├── database.py                 # Database connection
├── models/
│   ├── database.py            # SQLAlchemy models
│   └── schemas.py             # Pydantic schemas
├── routers/
│   ├── cart.py                # Cart endpoints
│   ├── checkout.py            # Checkout endpoint
│   ├── orders.py              # Order endpoints
│   ├── auth.py                # Auth dependencies
│   └── health.py              # Health check
├── services/
│   ├── cart_service.py        # Cart business logic
│   ├── order_service.py       # Order business logic
│   ├── checkout_service.py    # Checkout orchestration
│   ├── product_client.py      # Product service client
│   ├── inventory_client.py    # Inventory service client
│   ├── payment_client.py      # Payment service client
│   ├── auth_client.py         # Auth service client
│   └── events.py              # RabbitMQ event publisher
├── tests/                     # Unit tests
├── Dockerfile
├── requirements.txt
└── README.md
```

### Testing

```bash
# Run tests (when implemented)
pytest

# Run with coverage
pytest --cov=. --cov-report=html
```

## Service Dependencies

### Outbound Calls

- **auth-service**: `POST /api/auth/validate` - JWT validation (all endpoints)
- **product-service**: `GET /api/products/{id}` - Fetch product details
- **inventory-service**:
  - `POST /api/inventory/reserve` - Reserve stock
  - `POST /api/inventory/confirm/{id}` - Confirm reservation
  - `POST /api/inventory/release/{id}` - Release reservation
- **payment-service**: `POST /api/payments/charge` - Process payment

### Event Publishing

Publishes to RabbitMQ exchange: `orders`

Events:
- `order.created` → Analytics (future)
- `order.completed` → Notification service (send confirmation email)
- `order.cancelled` → Inventory service (release stock)
- `order.shipped` → Notification service (send shipping email)

## Deployment

### Kubernetes

See `k8s/` directory for Kubernetes manifests (deployment, service, configmap, secrets).

### Environment-specific Configuration

- **Development**: Local database, mock payment service
- **Staging**: AWS RDS, Stripe test mode
- **Production**: AWS RDS Multi-AZ, Stripe live mode, read replicas

## Monitoring

- **Health checks**: `GET /health`
- **Logs**: JSON structured logs to stdout
- **Metrics**: Prometheus metrics (future)
- **Tracing**: OpenTelemetry (future)

## Security

- JWT-based authentication via auth-service
- Role-based access control (admin endpoints)
- Input validation via Pydantic
- SQL injection protection via SQLAlchemy ORM
- HTTPS in production (via API gateway)

## License

Proprietary - ShopHub, Inc.

## Contact

ShopHub Engineering Team
