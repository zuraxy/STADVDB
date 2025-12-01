# API Documentation

## Base URL
```
http://localhost:3000/api
```

Set via environment variable: `VITE_API_URL`

## Endpoints

### Orders
- `GET /node1/orders` - Fetch all orders from Node 1 (Central)
- `GET /node2/orders` - Fetch orders from Node 2 (Even IDs)
- `GET /node3/orders` - Fetch orders from Node 3 (Odd IDs)
- `POST /orders` - Create new order
- `PUT /orders/:orderId` - Update existing order
- `DELETE /orders/:orderId` - Delete order

### Node Status
- `GET /node1/status` - Get Node 1 status
- `GET /node2/status` - Get Node 2 status
- `GET /node3/status` - Get Node 3 status

### Concurrency Testing
- `POST /concurrency/execute` - Execute concurrency scenario
- `POST /concurrency/isolation` - Test transaction isolation
- `POST /concurrency/locking` - Test locking mechanisms

### Health
- `GET /health` - API health check

## Response Format

All endpoints return JSON in this format:
```json
{
  "success": true,
  "data": [...],
  "message": "Optional message"
}
```

## Usage

Import functions from `src/services/api.js`:
```javascript
import { fetchAllOrders, createOrder, deleteOrder } from '../services/api';

// Fetch all orders from all nodes
const orders = await fetchAllOrders();

// Create new order
const newOrder = await createOrder({ quantity: 5, payload: {...} });

// Delete order
await deleteOrder(orderId);
```
