// API Service - Centralized data fetching functions
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

/**
 * Generic fetch wrapper with error handling
 */
const fetchAPI = async (endpoint, options = {}) => {
  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error(`API Error (${endpoint}):`, error);
    throw error;
  }
};

// ==================== ORDER OPERATIONS ====================

/**
 * Fetch all orders from current node
 * @returns {Promise<Array>} Array of all orders
 */
export const fetchAllOrders = async () => {
  return fetchAPI('/orders');
};

/**
 * Fetch orders from a specific node's local database
 * @param {string} nodeName - Name of the node (e.g., 'node1', 'node2')
 * @returns {Promise<Array>} Array of orders from that node
 */
export const fetchNodeOrders = async (nodeName) => {
  console.log(`📡 Fetching orders from ${nodeName}...`);
  if (nodeName === 'node0') {
    // Node0 is the master, fetch normally
    return fetchAPI('/orders');
  }
  // Proxy through node0 to get local data from other nodes
  try {
    const result = await fetchAPI(`/proxy/node/${nodeName}/orders`);
    console.log(`✅ ${nodeName} returned ${result?.length || 0} orders`);
    return result;
  } catch (error) {
    console.error(`❌ Failed to fetch from ${nodeName}:`, error);
    throw error;
  }
};

/**
 * Fetch a single order by ID
 * @param {string} orderId - UUID of the order
 * @returns {Promise<Object|null>} Order object or null if not found
 */
export const fetchOrder = async (orderId) => {
  return fetchAPI(`/orders/${orderId}`);
};

/**
 * Create a new order
 * @param {Object} orderData - Order data { quantity: number, payload?: object }
 * @returns {Promise<Object>} Created order object
 */
export const createOrder = async (orderData) => {
  return fetchAPI('/orders', {
    method: 'POST',
    body: JSON.stringify(orderData),
  });
};

/**
 * Update an existing order
 * @param {string} orderId - UUID of the order to update
 * @param {Object} orderData - Updated data { quantity?: number, payload?: object }
 * @returns {Promise<Object>} Updated order object
 */
export const updateOrder = async (orderId, orderData) => {
  return fetchAPI(`/orders/${orderId}`, {
    method: 'PUT',
    body: JSON.stringify(orderData),
  });
};

/**
 * Delete an order
 * @param {string} orderId - UUID of the order to delete
 * @returns {Promise<void>}
 */
export const deleteOrder = async (orderId) => {
  const response = await fetch(`${API_BASE_URL}/orders/${orderId}`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
    },
  });
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  // DELETE returns 204 No Content, so no JSON to parse
  return;
};

// ==================== NODE STATUS ====================

/**
 * Fetch replication + peer node status metadata
 * @returns {Promise<Object>} Replication workers + node health snapshot
 */
export const fetchReplicationStatus = async () => {
  return fetchAPI('/status/replication');
};

/**
 * Fetch detailed metrics from all nodes
 * @returns {Promise<Object>} Metrics from each node with applier and replicator stats
 */
export const fetchAllNodeMetrics = async () => {
  // Fetch from the current node's /status/replication endpoint
  // This endpoint already contains metrics for all nodes
  try {
    const response = await fetchAPI('/status/replication');
    
    // Transform the response to match our expected format
    const metrics = {};
    
    if (response.nodes && Array.isArray(response.nodes)) {
      response.nodes.forEach(node => {
        const nodeKey = node.name.toLowerCase();
        metrics[nodeKey] = {
          node: node.name,
          status: node.status,
          applier: response.applier || {},
          replicator: response.replicator || {},
          role: node.role,
        };
      });
    }
    
    // Also include the current node's metrics
    if (response.node) {
      const nodeKey = response.node.toLowerCase();
      metrics[nodeKey] = {
        node: response.node,
        applier: response.applier || {},
        replicator: response.replicator || {},
        promoted: response.promoted,
      };
    }
    
    return metrics;
  } catch (error) {
    console.error('Failed to fetch node metrics:', error);
    return {};
  }
};

// ==================== HEALTH CHECK ====================

/**
 * Health check endpoint
 * @returns {Promise<Object>} API health status
 */
export const healthCheck = async () => {
  return fetchAPI('/health');
};

/**
 * Export API base URL for direct use if needed
 */
export { API_BASE_URL };

// ==================== TRANSACTION ORCHESTRATOR ====================

/**
 * Start a new orchestrator run for a given scenario
 * @param {Object} payload - Request body with scenario, isolation level, and optional custom transactions
 * @returns {Promise<Object>} Details containing run_id
 */
export const runOrchestratorScenario = async (payload) => {
  return fetchAPI('/orchestrator/run', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

/**
 * Fetch orchestration status, including per-client progress and summary details
 * @param {string} runId - Run identifier
 * @returns {Promise<Object>} Run snapshot
 */
export const getOrchestratorStatus = async (runId) => {
  return fetchAPI(`/orchestrator/status/${runId}`);
};

/**
 * Fetch structured event logs for a run
 * @param {string} runId - Run identifier
 * @returns {Promise<Object>} Log array
 */
export const getOrchestratorLogs = async (runId) => {
  return fetchAPI(`/orchestrator/logs/${runId}`);
};

/**
 * Abort an in-flight orchestrator run
 * @param {string} runId - Run identifier
 * @returns {Promise<Object>} Confirmation payload
 */
export const abortOrchestratorRun = async (runId) => {
  return fetchAPI(`/orchestrator/abort/${runId}`, {
    method: 'POST',
  });
};