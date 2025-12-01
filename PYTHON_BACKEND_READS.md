# Python Backend Read Endpoints Implementation

## Summary
Consolidated to use `replication/` (Python FastAPI backend) as the primary backend with minimal read-only API surface for frontend consumption.

## Changes Made

### 1. Backend - Added Read Functions to `replication/crud.py`

Added three new read functions after the existing `insert_ack` function:

- **`get_all_orders(pool, limit, offset)`**: Fetches orders with pagination
  - Returns: `list[OrderRead]`
  - SQL: `SELECT * FROM orders ORDER BY created_at DESC LIMIT ... OFFSET ...`

- **`count_orders(pool)`**: Gets total order count
  - Returns: `int`
  - SQL: `SELECT COUNT(*) FROM orders`

- **`get_node_stats(pool, node_name)`**: Gets node statistics
  - Returns: `dict` with:
    - `node_name`: Name of the node
    - `total_orders`: Total orders in database
    - `pending_operations`: Count of unapplied operations
    - `total_operations`: Total operations logged
    - `last_operation`: ISO timestamp of last operation
    - `status`: "connected"

**Note**: `get_order(pool, order_id)` already existed at line 150.

### 2. Backend - Created `replication/routes/reads.py`

New router file with 4 read-only endpoints:

- **`GET /read/orders`**: List orders with pagination
  - Query params: `limit` (1-1000, default 100), `offset` (default 0)
  - Response: `List[OrderRead]`

- **`GET /read/orders/{order_id}`**: Get specific order by UUID
  - Path param: `order_id` (UUID)
  - Response: `OrderRead` or 404

- **`GET /read/count`**: Get total order count
  - Response: `{"count": int}`

- **`GET /read/node-stats`**: Get current node statistics
  - Response: Node stats object

### 3. Backend - Updated `replication/main.py`

- Imported `reads` module in routes import
- Mounted reads router: `app.include_router(reads.router, prefix="/read", tags=["Read"])`

### 4. Backend - Updated `replication/routes/__init__.py`

- Added `reads` to module exports

### 5. Frontend - Added Methods to `src/services/api.js`

Added 4 new API service methods for Python backend:

- **`fetchAllOrdersPython(limit, offset)`**: Fetch paginated orders
- **`countOrders()`**: Get total order count
- **`getNodeStats()`**: Get node statistics
- **`getOrderById(orderId)`**: Get specific order by UUID

### 6. Frontend - Created `.env` file

Created `frontend/web-app/.env` with:
```
VITE_API_URL=/api
```

This ensures all API calls go through Nginx proxy at `/api`.

## API Endpoint Summary

All endpoints are prefixed with `/read` when accessed through FastAPI.

With Nginx proxy, frontend will access these as:
- `GET /api/read/orders?limit=100&offset=0`
- `GET /api/read/orders/{order_id}`
- `GET /api/read/count`
- `GET /api/read/node-stats`

## Next Steps

### Immediate:
1. **Deploy Python backend to VMs**: Use PM2 or systemd to run the FastAPI server on port 8000
2. **Update Nginx configuration**: Add proxy rules for `/api/read/*` to forward to Python backend at `localhost:8000`
3. **Update frontend components**: Modify `DatabaseDashboard.jsx` and `DatabaseStatus.jsx` to use the new API methods

### Nginx Configuration Update Needed:
```nginx
location /api/read/ {
    proxy_pass http://localhost:8000/read/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
    proxy_cache_bypass $http_upgrade;
}
```

### Frontend Component Updates:

**DatabaseDashboard.jsx**:
```javascript
import { fetchAllOrdersPython, countOrders } from '../services/api';

// Replace existing fetch calls with:
const orders = await fetchAllOrdersPython(limit, offset);
const { count } = await countOrders();
```

**DatabaseStatus.jsx**:
```javascript
import { getNodeStats } from '../services/api';

// Replace existing status fetch with:
const stats = await getNodeStats();
```

## Migration Path

Current architecture:
- Node.js backend (port 3000) - legacy, being phased out
- Python backend (port 8000) - new primary backend

Target architecture:
- Python backend only (port 8000)
- All frontend API calls go through Python FastAPI
- Node.js backend can be retired once all frontend components are updated

## Files Modified

1. ✅ `replication/crud.py` - Added 3 read functions
2. ✅ `replication/routes/reads.py` - Created new router
3. ✅ `replication/routes/__init__.py` - Added reads export
4. ✅ `replication/main.py` - Mounted reads router
5. ✅ `frontend/web-app/src/services/api.js` - Added 4 new methods
6. ✅ `frontend/web-app/.env` - Created with VITE_API_URL

## Testing Checklist

- [ ] Python backend starts without errors: `cd replication && uvicorn main:app --reload`
- [ ] Read endpoints respond correctly:
  - [ ] `curl http://localhost:8000/read/orders?limit=10`
  - [ ] `curl http://localhost:8000/read/count`
  - [ ] `curl http://localhost:8000/read/node-stats`
- [ ] Frontend builds without errors: `cd frontend/web-app && npm run build`
- [ ] Frontend development server works: `npm run dev`
- [ ] Nginx proxy routes `/api/read/*` to Python backend
- [ ] Frontend components successfully fetch data from new endpoints
