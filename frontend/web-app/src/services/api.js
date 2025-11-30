// API Service - Centralized data fetching functions
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:3000/api';

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
 * Fetch orders from a specific node
 * @param {number} nodeId - Node number (1, 2, or 3)
 * @returns {Promise<Object>} Response with success flag and orders data
 */
export const fetchOrdersFromNode = async (nodeId) => {
  return fetchAPI(`/node${nodeId}/orders`);
};

/**
 * Fetch orders from all nodes
 * @returns {Promise<Object>} Object with node1, node2, node3 arrays
 */
export const fetchAllOrders = async () => {
  try {
    const [res1, res2, res3] = await Promise.all([
      fetchOrdersFromNode(1),
      fetchOrdersFromNode(2),
      fetchOrdersFromNode(3),
    ]);

    return {
      node1: res1.data || [],
      node2: res2.data || [],
      node3: res3.data || [],
    };
  } catch (error) {
    console.error('Error fetching all orders:', error);
    throw error;
  }
};

/**
 * Create a new order
 * @param {Object} orderData - Order data {quantity, payload}
 * @returns {Promise<Object>} Created order response
 */
export const createOrder = async (orderData) => {
  return fetchAPI('/orders', {
    method: 'POST',
    body: JSON.stringify(orderData),
  });
};

/**
 * Update an existing order
 * @param {string} orderId - UUID of the order
 * @param {Object} orderData - Updated order data
 * @returns {Promise<Object>} Updated order response
 */
export const updateOrder = async (orderId, orderData) => {
  return fetchAPI(`/orders/${orderId}`, {
    method: 'PUT',
    body: JSON.stringify(orderData),
  });
};

/**
 * Delete an order
 * @param {string} orderId - UUID of the order
 * @returns {Promise<Object>} Deletion response
 */
export const deleteOrder = async (orderId) => {
  return fetchAPI(`/orders/${orderId}`, {
    method: 'DELETE',
  });
};

// ==================== NODE STATUS ====================

/**
 * Get status of a specific node
 * @param {number} nodeId - Node number (1, 2, or 3)
 * @returns {Promise<Object>} Node status information
 */
export const getNodeStatus = async (nodeId) => {
  return fetchAPI(`/node${nodeId}/status`);
};

/**
 * Get status of all nodes
 * @returns {Promise<Object>} Status of all nodes
 */
export const getAllNodeStatus = async () => {
  try {
    const [status1, status2, status3] = await Promise.all([
      getNodeStatus(1),
      getNodeStatus(2),
      getNodeStatus(3),
    ]);

    return {
      node1: status1.data || {},
      node2: status2.data || {},
      node3: status3.data || {},
    };
  } catch (error) {
    console.error('Error fetching node status:', error);
    throw error;
  }
};

// ==================== CONCURRENCY OPERATIONS ====================

/**
 * Execute a concurrency test scenario
 * @param {string} scenario - Scenario type
 * @param {Object} params - Scenario parameters
 * @returns {Promise<Object>} Scenario execution results
 */
export const executeConcurrencyScenario = async (scenario, params = {}) => {
  return fetchAPI('/concurrency/execute', {
    method: 'POST',
    body: JSON.stringify({ scenario, ...params }),
  });
};

/**
 * Test transaction isolation
 * @param {string} isolationLevel - Isolation level to test
 * @returns {Promise<Object>} Test results
 */
export const testTransactionIsolation = async (isolationLevel) => {
  return fetchAPI('/concurrency/isolation', {
    method: 'POST',
    body: JSON.stringify({ isolationLevel }),
  });
};

/**
 * Test locking mechanism
 * @param {string} lockType - Lock type (FOR SHARE, FOR UPDATE)
 * @returns {Promise<Object>} Lock test results
 */
export const testLocking = async (lockType) => {
  return fetchAPI('/concurrency/locking', {
    method: 'POST',
    body: JSON.stringify({ lockType }),
  });
};

// ==================== UTILITIES ====================

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
