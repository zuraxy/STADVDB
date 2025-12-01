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
 * @param {string} nodeId - Node name ('Node1', 'Node2', or 'Node3')
 * @returns {Promise<Object>} Response with success flag and orders data
 */
export const fetchOrdersFromNode = async (nodeId) => {
  return fetchAPI(`/fetch/${nodeId}`);
};

/**
 * Fetch all orders from Node1 (central node)
 * @param {number} page - Page number (default: 1)
 * @param {number} limit - Items per page (default: 10)
 * @returns {Promise<Object>} Response with paginated orders
 */
export const fetchAllOrders = async (page = 1, limit = 10) => {
  return fetchAPI(`/fetch/allOrder?page=${page}&limit=${limit}`);
};

/**
 * Fetch orders from all three nodes
 * @returns {Promise<Object>} Object with node1, node2, node3 arrays
 */
export const fetchOrdersFromAllNodes = async () => {
  try {
    const [res1, res2, res3] = await Promise.all([
      fetchOrdersFromNode('Node1'),
      fetchOrdersFromNode('Node2'),
      fetchOrdersFromNode('Node3'),
    ]);

    return {
      node1: res1.data || [],
      node2: res2.data || [],
      node3: res3.data || [],
    };
  } catch (error) {
    console.error('Error fetching orders from all nodes:', error);
    throw error;
  }
};

// ==================== NODE STATUS ====================

/**
 * Test connection to a specific node
 * @param {string} nodeId - Node name ('Node1', 'Node2', or 'Node3')
 * @returns {Promise<Object>} Node connection test result
 */
export const testNodeConnection = async (nodeId) => {
  return fetchAPI(`/test/${nodeId}`);
};

/**
 * Test connections to all database nodes
 * @returns {Promise<Object>} Connection status for all nodes
 */
export const testAllConnections = async () => {
  return fetchAPI('/test-connections');
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

// ==================== READ ENDPOINTS (Python Backend) ====================

/**
 * Fetch all orders with pagination from Python backend
 * @param {number} limit - Maximum number of orders to return (1-1000, default 100)
 * @param {number} offset - Number of orders to skip (default 0)
 * @returns {Promise<Array>} Array of order objects
 */
export const fetchAllOrdersPython = async (limit = 100, offset = 0) => {
  return fetchAPI(`/read/orders?limit=${limit}&offset=${offset}`);
};

/**
 * Get total count of orders from Python backend
 * @returns {Promise<Object>} Object with count property
 */
export const countOrders = async () => {
  return fetchAPI('/read/count');
};

/**
 * Get node statistics from Python backend
 * @returns {Promise<Object>} Object with node stats (total_orders, pending_operations, etc.)
 */
export const getNodeStats = async () => {
  return fetchAPI('/read/node-stats');
};

/**
 * Get a specific order by ID from Python backend
 * @param {string} orderId - UUID of the order
 * @returns {Promise<Object>} Order object
 */
export const getOrderById = async (orderId) => {
  return fetchAPI(`/read/orders/${orderId}`);
};