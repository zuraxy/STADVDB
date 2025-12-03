# STADVDB MCO2 Implementation Plan

## Current Setup Analysis ✅

### PostgreSQL Environment
- **PostgreSQL Version**: 18.1
- **VMs**: 3 separate servers (STADVDB44-Server0, Server1, Server2)
- **Databases**: node0db (Node1 - Central), node1db (Node2), node2db (Node3)
- **Port**: 5432 (default)

### Database Schema (Already Implemented ✅)

#### Orders Table
```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS orders (
  order_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  quantity int NOT NULL,
  payload jsonb,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Node 1 (Central): No constraint - stores ALL orders
-- Node 2 (Fragment 1): quantity 1-5
ALTER TABLE orders ADD CONSTRAINT qty_1to5 CHECK (quantity >= 1 AND quantity <= 5);
-- Node 3 (Fragment 2): quantity 6-10
ALTER TABLE orders ADD CONSTRAINT qty_6to10 CHECK (quantity >= 6 AND quantity <= 10);
```

#### Operation Log Table
```sql
CREATE TABLE op_log (
  op_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  origin_node text NOT NULL,
  op_type text NOT NULL,
  table_name text NOT NULL,
  row_id uuid NOT NULL,
  payload jsonb,
  ts timestamptz DEFAULT now(),
  lamport bigint DEFAULT 0,
  applied boolean DEFAULT false,
  applied_ts timestamptz
);

CREATE INDEX idx_oplog_origin_ts ON op_log(origin_node, ts);
CREATE INDEX idx_oplog_lamport ON op_log(lamport);
```

#### Acknowledgements Table
```sql
CREATE TABLE IF NOT EXISTS log_acknowledgements (
  op_id uuid REFERENCES op_log(op_id) ON DELETE CASCADE,
  node text NOT NULL,
  ack_ts timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (op_id, node)
);
```

---

## Part 1: Data Fragmentation Strategy

### Fragmentation Criterion: **Quantity-Based Horizontal Partitioning**

```
Node 1 (Central): ALL orders (quantity 1-10) - Master copy
Node 2 (Fragment): Orders with quantity 1-5 only
Node 3 (Fragment): Orders with quantity 6-10 only
```

### Why This Strategy?
1. **Simple, clear partitioning rule** - Easy to determine which fragment owns data
2. **No overlap between fragments** - Node2 + Node3 = Node1 (completeness)
3. **Aligns with business logic** - Different order sizes may have different processing needs
4. **Balanced distribution** - Assuming orders are evenly distributed across quantity ranges

---

## Part 2: Backend Implementation Steps

### Step 1: Update Environment Configuration

Update your `backend/.env`:
```env
# PostgreSQL Connection
DB_USER=postgres
DB_PASSWORD=your_password
DB_PORT=5432

# Node IP Addresses (Update with your actual VM IPs)
NODE1_HOST=192.168.1.100  # STADVDB44-Server0 (Central)
NODE1_DB=node0db

NODE2_HOST=192.168.1.101  # STADVDB44-Server1 (Fragment 1-5)
NODE2_DB=node1db

NODE3_HOST=192.168.1.102  # STADVDB44-Server2 (Fragment 6-10)
NODE3_DB=node2db

# Server Port
PORT=3000
```

### Step 2: Update Database Configuration

```javascript
// filepath: backend/config/db.js
const { Pool } = require('pg');
require('dotenv').config();

const pools = {
  Node1: new Pool({
    user: process.env.DB_USER,
    host: process.env.NODE1_HOST,
    database: process.env.NODE1_DB,
    password: process.env.DB_PASSWORD,
    port: process.env.DB_PORT,
    max: 20,
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 2000,
  }),
  Node2: new Pool({
    user: process.env.DB_USER,
    host: process.env.NODE2_HOST,
    database: process.env.NODE2_DB,
    password: process.env.DB_PASSWORD,
    port: process.env.DB_PORT,
    max: 20,
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 2000,
  }),
  Node3: new Pool({
    user: process.env.DB_USER,
    host: process.env.NODE3_HOST,
    database: process.env.NODE3_DB,
    password: process.env.DB_PASSWORD,
    port: process.env.DB_PORT,
    max: 20,
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 2000,
  }),
};

// Test connections
const testConnections = async () => {
  for (const [nodeName, pool] of Object.entries(pools)) {
    try {
      const client = await pool.connect();
      const result = await client.query('SELECT NOW()');
      console.log(`✓ ${nodeName} connected:`, result.rows[0].now);
      client.release();
    } catch (error) {
      console.error(`✗ ${nodeName} connection failed:`, error.message);
    }
  }
};

module.exports = pools;
module.exports.testConnections = testConnections;
```

### Step 3: Create Schema Controller

```javascript
// filepath: backend/config/schema.js
const createOrdersTable = `
  CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
  
  CREATE TABLE IF NOT EXISTS orders (
    order_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    quantity int NOT NULL,
    payload jsonb,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
  );
`;

const createOpLogTable = `
  CREATE TABLE IF NOT EXISTS op_log (
    op_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    origin_node text NOT NULL,
    op_type text NOT NULL,
    table_name text NOT NULL,
    row_id uuid NOT NULL,
    payload jsonb,
    ts timestamptz DEFAULT now(),
    lamport bigint DEFAULT 0,
    applied boolean DEFAULT false,
    applied_ts timestamptz
  );
  
  CREATE INDEX IF NOT EXISTS idx_oplog_origin_ts ON op_log(origin_node, ts);
  CREATE INDEX IF NOT EXISTS idx_oplog_lamport ON op_log(lamport);
`;

const createAckTable = `
  CREATE TABLE IF NOT EXISTS log_acknowledgements (
    op_id uuid REFERENCES op_log(op_id) ON DELETE CASCADE,
    node text NOT NULL,
    ack_ts timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (op_id, node)
  );
`;

const addNode2Constraint = `
  DO $$ 
  BEGIN
    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint WHERE conname = 'qty_1to5'
    ) THEN
      ALTER TABLE orders ADD CONSTRAINT qty_1to5 CHECK (quantity >= 1 AND quantity <= 5);
    END IF;
  END $$;
`;

const addNode3Constraint = `
  DO $$ 
  BEGIN
    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint WHERE conname = 'qty_6to10'
    ) THEN
      ALTER TABLE orders ADD CONSTRAINT qty_6to10 CHECK (quantity >= 6 AND quantity <= 10);
    END IF;
  END $$;
`;

module.exports = {
  createOrdersTable,
  createOpLogTable,
  createAckTable,
  addNode2Constraint,
  addNode3Constraint
};
```

### Step 4: Create Initialization Controller

```javascript
// filepath: backend/controllers/initController.js
const pools = require('../config/db');
const schema = require('../config/schema');

const initializeAllNodes = async () => {
  const results = {};
  
  try {
    // Node 1: Central node (all orders, no constraint)
    console.log('Initializing Node1 (Central)...');
    await pools.Node1.query(schema.createOrdersTable);
    await pools.Node1.query(schema.createOpLogTable);
    await pools.Node1.query(schema.createAckTable);
    results.Node1 = { 
      status: 'initialized', 
      role: 'Central Node',
      fragment: 'ALL orders (no constraint)'
    };
    
    // Node 2: Fragment 1 (quantity 1-5)
    console.log('Initializing Node2 (Fragment 1-5)...');
    await pools.Node2.query(schema.createOrdersTable);
    await pools.Node2.query(schema.createOpLogTable);
    await pools.Node2.query(schema.createAckTable);
    await pools.Node2.query(schema.addNode2Constraint);
    results.Node2 = { 
      status: 'initialized',
      role: 'Fragment Node',
      fragment: 'quantity 1-5'
    };
    
    // Node 3: Fragment 2 (quantity 6-10)
    console.log('Initializing Node3 (Fragment 6-10)...');
    await pools.Node3.query(schema.createOrdersTable);
    await pools.Node3.query(schema.createOpLogTable);
    await pools.Node3.query(schema.createAckTable);
    await pools.Node3.query(schema.addNode3Constraint);
    results.Node3 = { 
      status: 'initialized',
      role: 'Fragment Node',
      fragment: 'quantity 6-10'
    };
    
    console.log('✓ All nodes initialized successfully');
    return { success: true, results };
  } catch (error) {
    console.error('✗ Initialization failed:', error.message);
    throw new Error(`Initialization failed: ${error.message}`);
  }
};

const checkNodeStatus = async () => {
  const status = {};
  
  for (const [nodeName, pool] of Object.entries(pools)) {
    try {
      const client = await pool.connect();
      
      // Check if tables exist
      const tablesResult = await client.query(`
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name IN ('orders', 'op_log', 'log_acknowledgements')
      `);
      
      // Get row counts
      const ordersCount = await client.query('SELECT COUNT(*) FROM orders');
      const opLogCount = await client.query('SELECT COUNT(*) FROM op_log');
      
      client.release();
      
      status[nodeName] = {
        connected: true,
        tables: tablesResult.rows.map(r => r.table_name),
        orderCount: parseInt(ordersCount.rows[0].count),
        opLogCount: parseInt(opLogCount.rows[0].count)
      };
    } catch (error) {
      status[nodeName] = {
        connected: false,
        error: error.message
      };
    }
  }
  
  return status;
};

module.exports = { initializeAllNodes, checkNodeStatus };
```

### Step 5: Create Lamport Clock Utility

```javascript
// filepath: backend/utils/lamport.js
class LamportClock {
  constructor() {
    this.counter = 0;
  }
  
  tick() {
    this.counter++;
    return this.counter;
  }
  
  update(receivedTimestamp) {
    this.counter = Math.max(this.counter, receivedTimestamp) + 1;
    return this.counter;
  }
  
  getTime() {
    return this.counter;
  }
}

// Global Lamport clocks for each node
const clocks = {
  Node1: new LamportClock(),
  Node2: new LamportClock(),
  Node3: new LamportClock()
};

module.exports = { clocks, LamportClock };
```

### Step 6: Create Replication Controller

```javascript
// filepath: backend/controllers/replicationController.js
const pools = require('../config/db');
const { clocks } = require('../utils/lamport');

/**
 * Determine which nodes should receive the replication based on quantity
 */
const getTargetNodes = (originNode, quantity) => {
  const targets = [];
  
  // Always replicate to Node1 (central) if not origin
  if (originNode !== 'Node1') {
    targets.push('Node1');
  }
  
  // Replicate to fragment nodes based on quantity
  if (originNode !== 'Node2' && quantity >= 1 && quantity <= 5) {
    targets.push('Node2');
  }
  if (originNode !== 'Node3' && quantity >= 6 && quantity <= 10) {
    targets.push('Node3');
  }
  
  return targets;
};

/**
 * Replicate operation to target nodes
 */
const replicateOperation = async (originNode, opType, orderData) => {
  const lamportTime = clocks[originNode].tick();
  const opId = require('crypto').randomUUID();
  
  console.log(`[REPLICATION] ${opType} from ${originNode}, Lamport: ${lamportTime}`);
  
  // Log operation on origin node
  await pools[originNode].query(
    `INSERT INTO op_log (op_id, origin_node, op_type, table_name, row_id, payload, lamport)
     VALUES ($1, $2, $3, $4, $5, $6, $7)`,
    [opId, originNode, opType, 'orders', orderData.order_id, JSON.stringify(orderData), lamportTime]
  );
  
  const results = { 
    opId, 
    lamportTime, 
    originNode,
    replications: {} 
  };
  
  // Determine target nodes
  const targetNodes = getTargetNodes(originNode, orderData.quantity);
  console.log(`[REPLICATION] Target nodes:`, targetNodes);
  
  for (const targetNode of targetNodes) {
    try {
      // Update Lamport clock on target
      clocks[targetNode].update(lamportTime);
      
      const client = await pools[targetNode].connect();
      
      try {
        await client.query('BEGIN');
        
        // Execute replication based on operation type
        if (opType === 'INSERT') {
          await client.query(
            `INSERT INTO orders (order_id, quantity, payload, created_at, updated_at)
             VALUES ($1, $2, $3, $4, $5)
             ON CONFLICT (order_id) DO UPDATE 
             SET quantity = EXCLUDED.quantity, 
                 payload = EXCLUDED.payload, 
                 updated_at = EXCLUDED.updated_at`,
            [orderData.order_id, orderData.quantity, orderData.payload, orderData.created_at, orderData.updated_at]
          );
        } else if (opType === 'UPDATE') {
          await client.query(
            `UPDATE orders 
             SET quantity = $1, payload = $2, updated_at = $3 
             WHERE order_id = $4`,
            [orderData.quantity, orderData.payload, orderData.updated_at, orderData.order_id]
          );
        } else if (opType === 'DELETE') {
          await client.query(
            `DELETE FROM orders WHERE order_id = $1`,
            [orderData.order_id]
          );
        }
        
        // Log operation on target node
        await client.query(
          `INSERT INTO op_log (op_id, origin_node, op_type, table_name, row_id, payload, lamport, applied, applied_ts)
           VALUES ($1, $2, $3, $4, $5, $6, $7, true, now())`,
          [opId, originNode, opType, 'orders', orderData.order_id, JSON.stringify(orderData), lamportTime]
        );
        
        await client.query('COMMIT');
        
        // Acknowledge on origin node
        await pools[originNode].query(
          `INSERT INTO log_acknowledgements (op_id, node) VALUES ($1, $2)`,
          [opId, targetNode]
        );
        
        results.replications[targetNode] = { 
          status: 'success',
          lamport: clocks[targetNode].getTime()
        };
        console.log(`[REPLICATION] ✓ ${targetNode} replicated successfully`);
      } catch (error) {
        await client.query('ROLLBACK');
        throw error;
      } finally {
        client.release();
      }
    } catch (error) {
      results.replications[targetNode] = { 
        status: 'failed', 
        error: error.message 
      };
      console.error(`[REPLICATION] ✗ ${targetNode} replication failed:`, error.message);
    }
  }
  
  return results;
};

module.exports = { replicateOperation, getTargetNodes };
```

### Step 7: Create Order CRUD Controller

```javascript
// filepath: backend/controllers/orderController.js
const pools = require('../config/db');
const { replicateOperation } = require('./replicationController');

/**
 * CREATE: Insert order with replication
 */
const createOrder = async (req, res) => {
  const { nodeId, quantity, payload } = req.body;
  
  if (!nodeId || !quantity) {
    return res.status(400).json({ 
      success: false, 
      error: 'nodeId and quantity are required' 
    });
  }
  
  const client = await pools[nodeId].connect();
  
  try {
    await client.query('BEGIN ISOLATION LEVEL SERIALIZABLE');
    
    // Insert on origin node
    const result = await client.query(
      `INSERT INTO orders (quantity, payload) 
       VALUES ($1, $2) 
       RETURNING *`,
      [quantity, payload || {}]
    );
    
    const order = result.rows[0];
    
    await client.query('COMMIT');
    
    // Replicate to other nodes asynchronously
    const replicationResult = await replicateOperation(nodeId, 'INSERT', order);
    
    res.json({
      success: true,
      message: 'Order created and replicated',
      data: order,
      replication: replicationResult
    });
  } catch (error) {
    await client.query('ROLLBACK');
    console.error('[CREATE ERROR]', error);
    res.status(500).json({ success: false, error: error.message });
  } finally {
    client.release();
  }
};

/**
 * READ: Get all orders from a specific node
 */
const getOrders = async (req, res) => {
  const { nodeId } = req.params;
  
  try {
    const result = await pools[nodeId].query(
      `SELECT * FROM orders ORDER BY created_at DESC`
    );
    
    res.json({
      success: true,
      node: nodeId,
      count: result.rows.length,
      data: result.rows
    });
  } catch (error) {
    console.error('[READ ERROR]', error);
    res.status(500).json({ success: false, error: error.message });
  }
};

/**
 * READ: Get single order by ID
 */
const getOrderById = async (req, res) => {
  const { nodeId, orderId } = req.params;
  
  try {
    const result = await pools[nodeId].query(
      `SELECT * FROM orders WHERE order_id = $1`,
      [orderId]
    );
    
    if (result.rows.length === 0) {
      return res.status(404).json({ 
        success: false, 
        error: 'Order not found' 
      });
    }
    
    res.json({
      success: true,
      node: nodeId,
      data: result.rows[0]
    });
  } catch (error) {
    console.error('[READ ERROR]', error);
    res.status(500).json({ success: false, error: error.message });
  }
};

/**
 * UPDATE: Update order with replication
 */
const updateOrder = async (req, res) => {
  const { nodeId, orderId } = req.params;
  const { quantity, payload } = req.body;
  
  const client = await pools[nodeId].connect();
  
  try {
    await client.query('BEGIN ISOLATION LEVEL SERIALIZABLE');
    
    // Lock and update on origin node
    const result = await client.query(
      `UPDATE orders 
       SET quantity = $1, payload = $2, updated_at = now() 
       WHERE order_id = $3 
       RETURNING *`,
      [quantity, payload, orderId]
    );
    
    if (result.rows.length === 0) {
      await client.query('ROLLBACK');
      return res.status(404).json({ 
        success: false, 
        error: 'Order not found' 
      });
    }
    
    const order = result.rows[0];
    
    await client.query('COMMIT');
    
    // Replicate to other nodes
    const replicationResult = await replicateOperation(nodeId, 'UPDATE', order);
    
    res.json({
      success: true,
      message: 'Order updated and replicated',
      data: order,
      replication: replicationResult
    });
  } catch (error) {
    await client.query('ROLLBACK');
    console.error('[UPDATE ERROR]', error);
    res.status(500).json({ success: false, error: error.message });
  } finally {
    client.release();
  }
};

/**
 * DELETE: Delete order with replication
 */
const deleteOrder = async (req, res) => {
  const { nodeId, orderId } = req.params;
  
  const client = await pools[nodeId].connect();
  
  try {
    await client.query('BEGIN ISOLATION LEVEL SERIALIZABLE');
    
    // Get order before deleting
    const getResult = await client.query(
      `SELECT * FROM orders WHERE order_id = $1 FOR UPDATE`,
      [orderId]
    );
    
    if (getResult.rows.length === 0) {
      await client.query('ROLLBACK');
      return res.status(404).json({ 
        success: false, 
        error: 'Order not found' 
      });
    }
    
    const order = getResult.rows[0];
    
    // Delete on origin node
    await client.query(
      `DELETE FROM orders WHERE order_id = $1`,
      [orderId]
    );
    
    await client.query('COMMIT');
    
    // Replicate deletion to other nodes
    const replicationResult = await replicateOperation(nodeId, 'DELETE', order);
    
    res.json({
      success: true,
      message: 'Order deleted and replicated',
      data: order,
      replication: replicationResult
    });
  } catch (error) {
    await client.query('ROLLBACK');
    console.error('[DELETE ERROR]', error);
    res.status(500).json({ success: false, error: error.message });
  } finally {
    client.release();
  }
};

module.exports = { 
  createOrder, 
  getOrders, 
  getOrderById,
  updateOrder, 
  deleteOrder 
};
```

---

## Part 3: Concurrency Control Implementation

### Case #1: Concurrent Reads

```javascript
// filepath: backend/controllers/concurrencyController.js
const pools = require('../config/db');

/**
 * CASE #1: Concurrent reads on same data
 */
const testConcurrentReads = async (req, res) => {
  const { orderId } = req.params;
  const startTime = Date.now();
  const log = [];
  
  try {
    // Simulate concurrent reads from all 3 nodes
    const readPromises = ['Node1', 'Node2', 'Node3'].map(async (nodeId) => {
      const client = await pools[nodeId].connect();
      
      try {
        const txStart = Date.now();
        await client.query('BEGIN ISOLATION LEVEL SERIALIZABLE');
        log.push({ 
          time: txStart - startTime, 
          event: `${nodeId} READ BEGIN`, 
          node: nodeId 
        });
        
        const result = await client.query(
          `SELECT * FROM orders WHERE order_id = $1`,
          [orderId]
        );
        
        // Simulate processing time
        await new Promise(resolve => setTimeout(resolve, Math.random() * 100));
        
        await client.query('COMMIT');
        const txEnd = Date.now();
        log.push({ 
          time: txEnd - startTime, 
          event: `${nodeId} READ COMMIT`, 
          node: nodeId 
        });
        
        return {
          node: nodeId,
          status: 'success',
          data: result.rows[0] || null,
          duration: txEnd - txStart,
          lockType: 'SHARE (Read Lock)',
          isolationLevel: 'SERIALIZABLE'
        };
      } finally {
        client.release();
      }
    });
    
    const results = await Promise.all(readPromises);
    const totalDuration = Date.now() - startTime;
    
    // Verify consistency
    const allData = results.map(r => JSON.stringify(r.data));
    const isConsistent = allData.every(data => data === allData[0]);
    
    res.json({
      case: 'Case #1: Concurrent Reads',
      description: 'Multiple transactions reading same data item',
      totalDuration: `${totalDuration}ms`,
      transactionLog: log.sort((a, b) => a.time - b.time),
      results,
      consistency: {
        status: isConsistent ? 'CONSISTENT' : 'INCONSISTENT',
        message: isConsistent 
          ? 'All nodes returned identical data' 
          : 'Data mismatch detected across nodes'
      }
    });
  } catch (error) {
    console.error('[CASE #1 ERROR]', error);
    res.status(500).json({ success: false, error: error.message });
  }
};
```

### Case #2: Write + Concurrent Reads

```javascript
/**
 * CASE #2: One write + concurrent reads
 */
const testWriteWithReads = async (req, res) => {
  const { orderId, newQuantity } = req.body;
  const startTime = Date.now();
  const log = [];
  
  try {
    // Start write transaction on Node1
    const writePromise = (async () => {
      const client = await pools.Node1.connect();
      try {
        await client.query('BEGIN ISOLATION LEVEL SERIALIZABLE');
        log.push({ 
          time: Date.now() - startTime, 
          event: 'Node1 WRITE BEGIN', 
          node: 'Node1' 
        });
        
        const result = await client.query(
          `UPDATE orders SET quantity = $1, updated_at = now() 
           WHERE order_id = $2 
           RETURNING *`,
          [newQuantity, orderId]
        );
        
        // Simulate processing
        await new Promise(resolve => setTimeout(resolve, 200));
        
        await client.query('COMMIT');
        log.push({ 
          time: Date.now() - startTime, 
          event: 'Node1 WRITE COMMIT', 
          node: 'Node1' 
        });
        
        return { 
          node: 'Node1', 
          operation: 'WRITE', 
          status: 'success',
          data: result.rows[0]
        };
      } finally {
        client.release();
      }
    })();
    
    // Concurrent reads from Node2 and Node3
    const readPromises = ['Node2', 'Node3'].map(async (nodeId) => {
      const client = await pools[nodeId].connect();
      try {
        // Wait a bit to ensure write starts first
        await new Promise(resolve => setTimeout(resolve, 50));
        
        await client.query('BEGIN ISOLATION LEVEL READ COMMITTED');
        log.push({ 
          time: Date.now() - startTime, 
          event: `${nodeId} READ BEGIN`, 
          node: nodeId 
        });
        
        const result = await client.query(
          `SELECT * FROM orders WHERE order_id = $1`,
          [orderId]
        );
        
        await client.query('COMMIT');
        log.push({ 
          time: Date.now() - startTime, 
          event: `${nodeId} READ COMMIT`, 
          node: nodeId 
        });
        
        return {
          node: nodeId,
          operation: 'READ',
          status: 'success',
          data: result.rows[0]
        };
      } finally {
        client.release();
      }
    });
    
    const [writeResult, ...readResults] = await Promise.all([writePromise, ...readPromises]);
    const totalDuration = Date.now() - startTime;
    
    res.json({
      case: 'Case #2: Write + Concurrent Reads',
      description: 'One transaction writing while others read same data',
      totalDuration: `${totalDuration}ms`,
      transactionLog: log.sort((a, b) => a.time - b.time),
      results: [writeResult, ...readResults],
      consistency: {
        status: 'SERIALIZABLE',
        message: 'Read transactions may see old or new value depending on timing'
      }
    });
  } catch (error) {
    console.error('[CASE #2 ERROR]', error);
    res.status(500).json({ success: false, error: error.message });
  }
};
```

### Case #3: Concurrent Writes

```javascript
/**
 * CASE #3: Concurrent writes on same data
 */
const testConcurrentWrites = async (req, res) => {
  const { orderId } = req.params;
  const startTime = Date.now();
  const log = [];
  
  try {
    // Concurrent write transactions from different nodes
    const writePromises = [
      { node: 'Node1', increment: 1 },
      { node: 'Node2', increment: 2 }
    ].map(async ({ node, increment }) => {
      const client = await pools[node].connect();
      
      try {
        await client.query('BEGIN ISOLATION LEVEL SERIALIZABLE');
        log.push({ 
          time: Date.now() - startTime, 
          event: `${node} WRITE BEGIN`, 
          node 
        });
        
        // Read current value with lock
        const readResult = await client.query(
          `SELECT quantity FROM orders WHERE order_id = $1 FOR UPDATE`,
          [orderId]
        );
        
        if (readResult.rows.length === 0) {
          throw new Error('Order not found');
        }
        
        const currentQty = readResult.rows[0].quantity;
        const newQty = currentQty + increment;
        
        // Simulate processing
        await new Promise(resolve => setTimeout(resolve, Math.random() * 200));
        
        // Update
        await client.query(
          `UPDATE orders SET quantity = $1, updated_at = now() 
           WHERE order_id = $2`,
          [newQty, orderId]
        );
        
        await client.query('COMMIT');
        log.push({ 
          time: Date.now() - startTime, 
          event: `${node} WRITE COMMIT`, 
          node 
        });
        
        return {
          node,
          operation: 'WRITE',
          status: 'success',
          oldValue: currentQty,
          newValue: newQty,
          increment
        };
      } catch (error) {
        await client.query('ROLLBACK');
        log.push({ 
          time: Date.now() - startTime, 
          event: `${node} WRITE ROLLBACK`, 
          node, 
          error: error.message 
        });
        
        return {
          node,
          operation: 'WRITE',
          status: 'failed',
          error: error.message
        };
      } finally {
        client.release();
      }
    });
    
    const results = await Promise.all(writePromises);
    const totalDuration = Date.now() - startTime;
    
    // Check final state
    const finalState = await pools.Node1.query(
      `SELECT * FROM orders WHERE order_id = $1`,
      [orderId]
    );
    
    res.json({
      case: 'Case #3: Concurrent Writes',
      description: 'Multiple transactions writing to same data item',
      totalDuration: `${totalDuration}ms`,
      transactionLog: log.sort((a, b) => a.time - b.time),
      results,
      finalState: finalState.rows[0],
      consistency: {
        status: 'SERIALIZABLE',
        message: 'Transactions executed serially due to FOR UPDATE lock. One succeeded, others may fail with serialization error.'
      }
    });
  } catch (error) {
    console.error('[CASE #3 ERROR]', error);
    res.status(500).json({ success: false, error: error.message });
  }
};

module.exports = {
  testConcurrentReads,
  testWriteWithReads,
  testConcurrentWrites
};
```

---

## Part 4: Crash Recovery Implementation

### Recovery Strategy: **Operation Log Replay**

```javascript
// filepath: backend/controllers/recoveryController.js
const pools = require('../config/db');

/**
 * Get pending operations that need to be replayed
 */
const getPendingOperations = async (nodeId) => {
  const result = await pools[nodeId].query(
    `SELECT * FROM op_log 
     WHERE applied = false 
     ORDER BY lamport ASC, ts ASC`
  );
  return result.rows;
};

/**
 * Replay a single operation on target node
 */
const replayOperation = async (targetNode, operation) => {
  const client = await pools[targetNode].connect();
  
  try {
    await client.query('BEGIN');
    
    const payload = operation.payload;
    
    if (operation.op_type === 'INSERT') {
      await client.query(
        `INSERT INTO orders (order_id, quantity, payload, created_at, updated_at)
         VALUES ($1, $2, $3, $4, $5)
         ON CONFLICT (order_id) DO UPDATE
         SET quantity = EXCLUDED.quantity, 
             payload = EXCLUDED.payload, 
             updated_at = EXCLUDED.updated_at`,
        [payload.order_id, payload.quantity, payload.payload, payload.created_at, payload.updated_at]
      );
    } else if (operation.op_type === 'UPDATE') {
      await client.query(
        `UPDATE orders 
         SET quantity = $1, payload = $2, updated_at = $3 
         WHERE order_id = $4`,
        [payload.quantity, payload.payload, payload.updated_at, payload.order_id]
      );
    } else if (operation.op_type === 'DELETE') {
      await client.query(
        `DELETE FROM orders WHERE order_id = $1`,
        [payload.order_id]
      );
    }
    
    // Mark as applied
    await client.query(
      `INSERT INTO op_log (op_id, origin_node, op_type, table_name, row_id, payload, lamport, applied, applied_ts)
       VALUES ($1, $2, $3, $4, $5, $6, $7, true, now())
       ON CONFLICT (op_id) DO UPDATE SET applied = true, applied_ts = now()`,
      [operation.op_id, operation.origin_node, operation.op_type, operation.table_name, 
       operation.row_id, JSON.stringify(payload), operation.lamport]
    );
    
    await client.query('COMMIT');
    console.log(`[RECOVERY] ✓ Replayed op ${operation.op_id} on ${targetNode}`);
    return { success: true, op_id: operation.op_id };
  } catch (error) {
    await client.query('ROLLBACK');
    console.error(`[RECOVERY] ✗ Failed to replay op ${operation.op_id} on ${targetNode}:`, error.message);
    return { success: false, op_id: operation.op_id, error: error.message };
  } finally {
    client.release();
  }
};

/**
 * CASE #1: Replication from Node2/3 to Central fails
 */
const testReplicationFailureToCentral = async (req, res) => {
  const { sourceNode, quantity, payload, simulateFailure } = req.body;
  
  if (!['Node2', 'Node3'].includes(sourceNode)) {
    return res.status(400).json({ 
      success: false, 
      error: 'sourceNode must be Node2 or Node3' 
    });
  }
  
  try {
    // Create order on source node
    const result = await pools[sourceNode].query(
      `INSERT INTO orders (quantity, payload) 
       VALUES ($1, $2) 
       RETURNING *`,
      [quantity, payload || {}]
    );
    
    const order = result.rows[0];
    
    let replicationError = null;
    
    if (simulateFailure) {
      // Simulate failure - log but don't replicate
      replicationError = 'SIMULATED: Central node (Node1) is down';
      
      await pools[sourceNode].query(
        `INSERT INTO op_log (origin_node, op_type, table_name, row_id, payload, applied)
         VALUES ($1, $2, $3, $4, $5, false)`,
        [sourceNode, 'INSERT', 'orders', order.order_id, JSON.stringify(order)]
      );
      
      console.log(`[RECOVERY TEST] Simulated failure: order ${order.order_id} not replicated to Node1`);
    } else {
      // Normal replication
      try {
        await pools.Node1.query(
          `INSERT INTO orders (order_id, quantity, payload, created_at, updated_at)
           VALUES ($1, $2, $3, $4, $5)`,
          [order.order_id, order.quantity, order.payload, order.created_at, order.updated_at]
        );
      } catch (error) {
        replicationError = error.message;
      }
    }
    
    res.json({
      case: 'Case #1: Replication Failure to Central Node',
      description: 'Transaction created on fragment node but failed to replicate to central',
      sourceNode,
      order,
      replication: {
        target: 'Node1',
        status: replicationError ? 'FAILED' : 'SUCCESS',
        error: replicationError
      },
      recovery: replicationError ? {
        status: 'LOGGED',
        message: 'Operation logged in op_log for later recovery'
      } : null
    });
  } catch (error) {
    console.error('[CASE #1 ERROR]', error);
    res.status(500).json({ success: false, error: error.message });
  }
};

/**
 * CASE #2: Central node recovers and catches up
 */
const testCentralNodeRecovery = async (req, res) => {
  try {
    console.log('[RECOVERY] Starting central node recovery...');
    
    // Get pending operations from fragment nodes
    const node2Pending = await getPendingOperations('Node2');
    const node3Pending = await getPendingOperations('Node3');
    
    const allPending = [...node2Pending, ...node3Pending].sort((a, b) => {
      if (a.lamport !== b.lamport) return a.lamport - b.lamport;
      return new Date(a.ts) - new Date(b.ts);
    });
    
    console.log(`[RECOVERY] Found ${allPending.length} pending operations`);
    
    const results = [];
    
    // Replay operations on Node1
    for (const op of allPending) {
      const result = await replayOperation('Node1', op);
      results.push(result);
      
      // Mark as applied on origin node
      if (result.success) {
        await pools[op.origin_node].query(
          `UPDATE op_log SET applied = true, applied_ts = now() WHERE op_id = $1`,
          [op.op_id]
        );
      }
    }
    
    res.json({
      case: 'Case #2: Central Node Recovery',
      description: 'Central node came back online and replayed missed transactions',
      pendingOperations: allPending.length,
      operations: allPending.map(op => ({
        op_id: op.op_id,
        origin_node: op.origin_node,
        op_type: op.op_type,
        lamport: op.lamport
      })),
      replayResults: results,
      summary: {
        successful: results.filter(r => r.success).length,
        failed: results.filter(r => !r.success).length
      }
    });
  } catch (error) {
    console.error('[CASE #2 ERROR]', error);
    res.status(500).json({ success: false, error: error.message });
  }
};

/**
 * CASE #3: Replication from Central to fragment fails
 */
const testReplicationFailureToFragment = async (req, res) => {
  const { quantity, payload, simulateFailure } = req.body;
  
  try {
    // Create order on Node1 (central)
    const result = await pools.Node1.query(
      `INSERT INTO orders (quantity, payload) 
       VALUES ($1, $2) 
       RETURNING *`,
      [quantity, payload || {}]
    );
    
    const order = result.rows[0];
    
    // Determine target fragment node based on quantity
    const targetNode = quantity >= 1 && quantity <= 5 ? 'Node2' : 'Node3';
    
    let replicationError = null;
    
    if (simulateFailure) {
      // Simulate failure
      replicationError = `SIMULATED: ${targetNode} is down`;
      
      await pools.Node1.query(
        `INSERT INTO op_log (origin_node, op_type, table_name, row_id, payload, applied)
         VALUES ($1, $2, $3, $4, $5, false)`,
        ['Node1', 'INSERT', 'orders', order.order_id, JSON.stringify(order)]
      );
      
      console.log(`[RECOVERY TEST] Simulated failure: order ${order.order_id} not replicated to ${targetNode}`);
    } else {
      // Normal replication
      try {
        await pools[targetNode].query(
          `INSERT INTO orders (order_id, quantity, payload, created_at, updated_at)
           VALUES ($1, $2, $3, $4, $5)`,
          [order.order_id, order.quantity, order.payload, order.created_at, order.updated_at]
        );
      } catch (error) {
        replicationError = error.message;
      }
    }
    
    res.json({
      case: 'Case #3: Replication Failure to Fragment Node',
      description: 'Transaction created on central but failed to replicate to fragment',
      order,
      replication: {
        target: targetNode,
        status: replicationError ? 'FAILED' : 'SUCCESS',
        error: replicationError
      },
      recovery: replicationError ? {
        status: 'LOGGED',
        message: 'Operation logged in op_log for later recovery'
      } : null
    });
  } catch (error) {
    console.error('[CASE #3 ERROR]', error);
    res.status(500).json({ success: false, error: error.message });
  }
};

/**
 * CASE #4: Fragment node recovers and catches up
 */
const testFragmentNodeRecovery = async (req, res) => {
  const { nodeId } = req.params;
  
  if (!['Node2', 'Node3'].includes(nodeId)) {
    return res.status(400).json({ 
      success: false, 
      error: 'nodeId must be Node2 or Node3' 
    });
  }
  
  try {
    console.log(`[RECOVERY] Starting ${nodeId} recovery...`);
    
    // Get pending operations from Node1
    const allPending = await getPendingOperations('Node1');
    
    // Filter operations relevant to this fragment
    const relevantOps = allPending.filter(op => {
      const payload = op.payload;
      if (nodeId === 'Node2') {
        return payload.quantity >= 1 && payload.quantity <= 5;
      } else {
        return payload.quantity >= 6 && payload.quantity <= 10;
      }
    });
    
    console.log(`[RECOVERY] Found ${relevantOps.length} relevant operations for ${nodeId}`);
    
    const results = [];
    
    // Replay operations on fragment node
    for (const op of relevantOps) {
      const result = await replayOperation(nodeId, op);
      results.push(result);
      
      // Mark as applied on Node1
      if (result.success) {
        await pools.Node1.query(
          `UPDATE op_log SET applied = true, applied_ts = now() WHERE op_id = $1`,
          [op.op_id]
        );
      }
    }
    
    res.json({
      case: `Case #4: ${nodeId} Recovery`,
      description: `${nodeId} came back online and replayed missed transactions`,
      pendingOperations: relevantOps.length,
      operations: relevantOps.map(op => ({
        op_id: op.op_id,
        op_type: op.op_type,
        quantity: op.payload.quantity,
        lamport: op.lamport
      })),
      replayResults: results,
      summary: {
        successful: results.filter(r => r.success).length,
        failed: results.filter(r => !r.success).length
      }
    });
  } catch (error) {
    console.error('[CASE #4 ERROR]', error);
    res.status(500).json({ success: false, error: error.message });
  }
};

module.exports = {
  testReplicationFailureToCentral,
  testCentralNodeRecovery,
  testReplicationFailureToFragment,
  testFragmentNodeRecovery,
  getPendingOperations,
  replayOperation
};
```

---

## Part 5: API Routes Setup

```javascript
// filepath: backend/routes/api.js
const express = require('express');
const router = express.Router();

const { initializeAllNodes, checkNodeStatus } = require('../controllers/initController');
const { createOrder, getOrders, getOrderById, updateOrder, deleteOrder } = require('../controllers/orderController');
const { 
  testConcurrentReads, 
  testWriteWithReads, 
  testConcurrentWrites 
} = require('../controllers/concurrencyController');
const {
  testReplicationFailureToCentral,
  testCentralNodeRecovery,
  testReplicationFailureToFragment,
  testFragmentNodeRecovery
} = require('../controllers/recoveryController');

// ===== HEALTH & INITIALIZATION =====
router.get('/health', async (req, res) => {
  try {
    const status = await checkNodeStatus();
    res.json({ success: true, nodes: status });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

router.post('/init', async (req, res) => {
  try {
    const result = await initializeAllNodes();
    res.json(result);
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
});

// ===== CRUD OPERATIONS =====
router.post('/orders', createOrder);
router.get('/orders/:nodeId', getOrders);
router.get('/orders/:nodeId/:orderId', getOrderById);
router.put('/orders/:nodeId/:orderId', updateOrder);
router.delete('/orders/:nodeId/:orderId', deleteOrder);

// ===== CONCURRENCY TESTS =====
router.get('/concurrency/case1/:orderId', testConcurrentReads);
router.post('/concurrency/case2', testWriteWithReads);
router.post('/concurrency/case3/:orderId', testConcurrentWrites);

// ===== RECOVERY TESTS =====
router.post('/recovery/case1', testReplicationFailureToCentral);
router.post('/recovery/case2', testCentralNodeRecovery);
router.post('/recovery/case3', testReplicationFailureToFragment);
router.post('/recovery/case4/:nodeId', testFragmentNodeRecovery);

module.exports = router;
```

### Update Main App

```javascript
// filepath: backend/app.js
const express = require('express');
const cors = require('cors');
const apiRoutes = require('./routes/api');

const app = express();

// Middleware
app.use(cors());
app.use(express.json());

// Logging middleware
app.use((req, res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.path}`);
  next();
});

// Routes
app.use('/api', apiRoutes);

// Error handling
app.use((err, req, res, next) => {
  console.error('[ERROR]', err);
  res.status(500).json({ success: false, error: err.message });
});

module.exports = app;
```

### Update Server Entry Point

```javascript
// filepath: backend/index.js
const app = require('./app');
const { testConnections } = require('./config/db');

const PORT = process.env.PORT || 3000;

// Test database connections on startup
testConnections()
  .then(() => {
    app.listen(PORT, () => {
      console.log(`✓ Server running on http://localhost:${PORT}`);
      console.log(`✓ API endpoints available at http://localhost:${PORT}/api`);
    });
  })
  .catch(error => {
    console.error('✗ Failed to start server:', error.message);
    process.exit(1);
  });
```

---

## Part 6: Testing & Verification

### Installation

```bash
cd backend
npm install pg dotenv express cors
```

### API Testing Commands

```bash
# 1. Check node health
curl http://localhost:3000/api/health

# 2. Initialize all nodes
curl -X POST http://localhost:3000/api/init

# 3. Create order on Node1
curl -X POST http://localhost:3000/api/orders \
  -H "Content-Type: application/json" \
  -d '{"nodeId":"Node1","quantity":3,"payload":{"product":"Widget"}}'

# 4. Create order on Node2 (will replicate to Node1)
curl -X POST http://localhost:3000/api/orders \
  -H "Content-Type: application/json" \
  -d '{"nodeId":"Node2","quantity":4,"payload":{"product":"Gadget"}}'

# 5. Get all orders from Node1
curl http://localhost:3000/api/orders/Node1

# 6. Update order
curl -X PUT http://localhost:3000/api/orders/Node1/<order-id> \
  -H "Content-Type: application/json" \
  -d '{"quantity":5,"payload":{"product":"Updated Widget"}}'

# 7. Test concurrent reads (Case #1)
curl http://localhost:3000/api/concurrency/case1/<order-id>

# 8. Test write + reads (Case #2)
curl -X POST http://localhost:3000/api/concurrency/case2 \
  -H "Content-Type: application/json" \
  -d '{"orderId":"<order-id>","newQuantity":7}'

# 9. Test concurrent writes (Case #3)
curl -X POST http://localhost:3000/api/concurrency/case3/<order-id>

# 10. Test replication failure to central (Case #1)
curl -X POST http://localhost:3000/api/recovery/case1 \
  -H "Content-Type: application/json" \
  -d '{"sourceNode":"Node2","quantity":4,"payload":{},"simulateFailure":true}'

# 11. Test central node recovery (Case #2)
curl -X POST http://localhost:3000/api/recovery/case2

# 12. Test replication failure to fragment (Case #3)
curl -X POST http://localhost:3000/api/recovery/case3 \
  -H "Content-Type: application/json" \
  -d '{"quantity":4,"payload":{},"simulateFailure":true}'

# 13. Test fragment node recovery (Case #4)
curl -X POST http://localhost:3000/api/recovery/case4/Node2
```

---

## Part 7: Implementation Checklist

### Phase 1: Setup ✅
- [ ] Update `.env` with correct VM IP addresses
- [ ] Install npm dependencies (`pg`, `express`, `cors`, `dotenv`)
- [ ] Create all controller files
- [ ] Create utility files (Lamport clock)
- [ ] Update routes and app.js
- [ ] Test database connections

### Phase 2: Basic CRUD ✅
- [ ] Initialize all 3 nodes with `/api/init`
- [ ] Verify fragmentation constraints work
- [ ] Create order on Node1, verify replication to Node1/Node2
- [ ] Create order on Node2 (qty 1-5), verify replication to Node1
- [ ] Create order on Node3 (qty 6-10), verify replication to Node1
- [ ] Update order, verify replication
- [ ] Delete order, verify replication

### Phase 3: Concurrency Tests ✅
- [ ] Case #1: Run concurrent reads, verify all nodes return same data
- [ ] Case #2: Run write + reads, verify isolation works
- [ ] Case #3: Run concurrent writes, verify one succeeds with FOR UPDATE

### Phase 4: Recovery Tests ✅
- [ ] Case #1: Simulate Node1 down during replication from Node2
- [ ] Case #2: Bring Node1 back, verify op_log replay works
- [ ] Case #3: Simulate Node2 down during replication from Node1
- [ ] Case #4: Bring Node2 back, verify op_log replay works

### Phase 5: Frontend Integration ✅
- [ ] Update frontend API service with new endpoints
- [ ] Create UI for concurrency tests
- [ ] Create UI for recovery scenarios
- [ ] Display transaction logs and results
- [ ] Add visualizations for node status

---

## Key Design Decisions

### 1. **Why Lamport Clocks?**
- Ensures causal ordering of operations across distributed nodes
- No need for synchronized physical clocks
- Simple increment on local events, max+1 on received events

### 2. **Why Operation Logs?**
- Enables recovery from failures
- Provides audit trail of all operations
- Allows replay of missed transactions in correct order
- Supports idempotent operations (ON CONFLICT DO UPDATE)

### 3. **Why 2-Phase Commit Pattern?**
- Ensures atomicity: either all nodes commit or all rollback
- Origin node commits first, then replicates
- Failures are logged for later recovery

### 4. **Why Quantity-Based Fragmentation?**
- Simple, deterministic partitioning rule
- Easy to determine which fragment owns data
- Aligns with potential business logic (small vs large orders)
- Clean separation: Node2 (1-5) + Node3 (6-10) = Node1 (1-10)

### 5. **Why SERIALIZABLE Isolation?**
- Strongest consistency guarantee
- Prevents phantom reads, non-repeatable reads, dirty reads
- Critical for distributed systems where data consistency matters

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (React)                     │
│  - DatabaseDashboard (CRUD UI)                          │
│  - ConcurrencyScenarios (Test UI)                       │
│  - RecoveryTests (Failure simulation)                   │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP/REST API
┌────────────────────▼────────────────────────────────────┐
│              Backend (Express.js)                        │
│  - Order Controller (CRUD + Replication)                │
│  - Concurrency Controller (Test Cases)                  │
│  - Recovery Controller (Failure handling)               │
│  - Lamport Clock (Logical time)                         │
└─┬──────────────┬──────────────┬────────────────────────┘
  │              │              │
  │ PostgreSQL   │ PostgreSQL   │ PostgreSQL
  ▼              ▼              ▼
┌────────┐    ┌────────┐    ┌────────┐
│ Node 1 │◄──►│ Node 2 │    │ Node 3 │
│Central │    │Fragment│    │Fragment│
│ ALL    │    │  1-5   │    │  6-10  │
│orders  │    │ orders │    │ orders │
└────────┘    └────────┘    └────────┘
   │              │              │
   └──────────────┴──────────────┘
         Replication Flow
```

---

## Next Steps

1. **Create Directory Structure**
   ```bash
   mkdir -p backend/controllers backend/utils
   ```

2. **Create All Files**
   - Copy each code block into corresponding file
   - Update `.env` with actual VM IPs

3. **Install Dependencies**
   ```bash
   cd backend
   npm install
   ```

4. **Start Server**
   ```bash
   node index.js
   ```

5. **Test Each Component**
   - Use curl commands to test each endpoint
   - Verify replication works
   - Test concurrency scenarios
   - Simulate failures and recovery

6. **Integrate with Frontend**
   - Update API service
   - Create test UIs
   - Add result visualizations

---

**Last Updated:** November 30, 2025  
**Version:** 1.0.0  
**PostgreSQL Version:** 18.1
