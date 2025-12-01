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