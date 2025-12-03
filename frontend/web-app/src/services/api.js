// API Service - Centralized data fetching functions
// Supports multiple backend nodes for resilience

// Node URLs - can be configured via environment
const NODE_URLS = {
  node0: import.meta.env.VITE_NODE0_URL || import.meta.env.VITE_API_URL || '',
  node1: import.meta.env.VITE_NODE1_URL || '',
  node2: import.meta.env.VITE_NODE2_URL || '',
};

// Track which nodes are currently available
const nodeStatus = {
  node0: { available: true, lastError: null, lastCheck: null },
  node1: { available: true, lastError: null, lastCheck: null },
  node2: { available: true, lastError: null, lastCheck: null },
};

// Default to first available node
let API_BASE_URL = NODE_URLS.node0 || '';

/**
 * Get the best available API URL (prefers node0, falls back to node1/node2)
 */
const getAvailableApiUrl = () => {
  // Try node0 first (master)
  if (nodeStatus.node0.available && NODE_URLS.node0) {
    return NODE_URLS.node0;
  }
  // Fall back to node1
  if (nodeStatus.node1.available && NODE_URLS.node1) {
    return NODE_URLS.node1;
  }
  // Fall back to node2
  if (nodeStatus.node2.available && NODE_URLS.node2) {
    return NODE_URLS.node2;
  }
  // Return default even if unavailable (let it fail)
  return NODE_URLS.node0 || '';
};

/**
 * Generic fetch wrapper with error handling and timeout
 */
const fetchAPI = async (endpoint, options = {}, timeout = 8000) => {
  const url = `${getAvailableApiUrl()}${endpoint}`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      signal: controller.signal,
      ...options,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    clearTimeout(timeoutId);
    
    // Track node failure
    const baseUrl = getAvailableApiUrl();
    for (const [node, url] of Object.entries(NODE_URLS)) {
      if (url === baseUrl) {
        nodeStatus[node].available = false;
        nodeStatus[node].lastError = error.message;
        nodeStatus[node].lastCheck = new Date().toISOString();
        break;
      }
    }
    
    console.error(`API Error (${endpoint}):`, error);
    throw error;
  }
};

/**
 * Fetch from a specific node URL with timeout
 */
const fetchFromNode = async (nodeUrl, endpoint, options = {}, timeout = 5000) => {
  if (!nodeUrl) {
    throw new Error('Node URL not configured');
  }
  
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(`${nodeUrl}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      signal: controller.signal,
      ...options,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    clearTimeout(timeoutId);
    throw error;
  }
};

/**
 * Safe fetch that returns null on failure instead of throwing
 */
const fetchAPISafe = async (endpoint, options = {}, timeout = 5000) => {
  try {
    return await fetchAPI(endpoint, options, timeout);
  } catch (error) {
    console.warn(`Safe fetch failed for ${endpoint}:`, error.message);
    return null;
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
  const baseUrl = getAvailableApiUrl();
  const response = await fetch(`${baseUrl}/orders/${orderId}`, {
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

/**
 * Subscribe to the orchestrator stream (Server-Sent Events).
 * Caller is responsible for closing the returned EventSource when finished.
 */
export const subscribeToOrchestratorStream = (runId, { onMessage, onError } = {}) => {
  if (typeof EventSource === 'undefined') {
    console.warn('EventSource not supported in this environment.');
    return null;
  }
  const streamUrl = `${API_BASE_URL}/orchestrator/stream/${runId}`.replace('//orchestrator', '/orchestrator');
  const source = new EventSource(streamUrl);
  source.onmessage = (event) => {
    if (!onMessage) return;
    try {
      const payload = JSON.parse(event.data);
      onMessage(payload);
    } catch (err) {
      console.error('Failed to parse orchestrator stream payload', err);
    }
  };
  source.onerror = (err) => {
    console.error('Orchestrator stream error', err);
    onError?.(err);
  };
  return source;
};

// ==================== RECOVERY OPERATIONS ====================

/**
 * Start a recovery job
 * @param {Object} payload - { mode: 'leader'|'node'|'promotion', since_ts?: string, promoted_node?: string }
 * @returns {Promise<Object>} { job_id, status }
 */
export const startRecovery = async (payload) => {
  return fetchAPI('/recovery/start', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

/**
 * Get recovery job status
 * @param {string} jobId - The job ID
 * @returns {Promise<Object>} Job status with metrics
 */
export const getRecoveryStatus = async (jobId) => {
  return fetchAPI(`/recovery/status/${jobId}`);
};

/**
 * Get recovery job logs
 * @param {string} jobId - The job ID
 * @param {number} limit - Max number of log entries
 * @returns {Promise<Object>} { job_id, logs: [] }
 */
export const getRecoveryLogs = async (jobId, limit = 100) => {
  return fetchAPI(`/recovery/logs/${jobId}?limit=${limit}`);
};

/**
 * Abort a running recovery job
 * @param {string} jobId - The job ID
 * @returns {Promise<Object>} { job_id, status }
 */
export const abortRecovery = async (jobId) => {
  return fetchAPI(`/recovery/abort/${jobId}`, {
    method: 'POST',
  });
};

/**
 * Get the currently active recovery job
 * @returns {Promise<Object>} { active_job: Object|null }
 */
export const getActiveRecoveryJob = async () => {
  return fetchAPI('/recovery/active');
};

/**
 * Get recovery flag status (whether writes are gated)
 * @returns {Promise<Object>} { recovery_in_progress, writes_gated }
 */
export const getRecoveryFlag = async () => {
  return fetchAPI('/recovery/flag');
};

/**
 * Request a snapshot from a peer node
 * @param {Object} payload - { peer: string, partition?: 'low'|'high' }
 * @returns {Promise<Object>} Snapshot request status
 */
export const forceSnapshot = async (payload) => {
  return fetchAPI('/recovery/force_snapshot', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

/**
 * Export snapshot from current node
 * @param {string} partition - 'low', 'high', or undefined for all
 * @param {string} format - 'json' or 'csv'
 * @returns {Promise<Object>} Snapshot data
 */
export const exportSnapshot = async (partition, format = 'json') => {
  const params = new URLSearchParams();
  if (partition) params.append('partition', partition);
  params.append('format', format);
  return fetchAPI(`/recovery/snapshot?${params.toString()}`);
};

// ==================== RECOVERY TEST SUITE ====================

/**
 * Get list of available recovery test cases
 * @returns {Promise<Object>} { cases: Array }
 */
export const getRecoveryTestCases = async () => {
  return fetchAPI('/recovery-tests/cases');
};

/**
 * Run a recovery test case
 * @param {string} testCase - Test case ID ('case_1', 'case_2', 'case_3', 'case_4')
 * @returns {Promise<Object>} Test result with logs and states
 */
export const runRecoveryTest = async (testCase) => {
  return fetchAPI('/recovery-tests/run', {
    method: 'POST',
    body: JSON.stringify({ test_case: testCase }),
  });
};

/**
 * Get currently running recovery test
 * @returns {Promise<Object>} { current_test: Object|null }
 */
export const getCurrentRecoveryTest = async () => {
  return fetchAPI('/recovery-tests/current');
};

/**
 * Get recovery test history
 * @returns {Promise<Object>} { history: Array }
 */
export const getRecoveryTestHistory = async () => {
  return fetchAPI('/recovery-tests/history');
};

/**
 * Clear recovery test history
 * @returns {Promise<Object>} { status: 'cleared' }
 */
export const clearRecoveryTestHistory = async () => {
  return fetchAPI('/recovery-tests/history/clear', { method: 'POST' });
};

/**
 * Get simulated node availability states
 * @returns {Promise<Object>} { availability: { node0: bool, node1: bool, node2: bool } }
 */
export const getNodeAvailability = async () => {
  return fetchAPI('/recovery-tests/node-availability');
};

/**
 * Set simulated node availability
 * @param {string} node - Node name ('node0', 'node1', 'node2')
 * @param {boolean} available - Whether node should be available
 * @returns {Promise<Object>} Updated availability states
 */
export const setNodeAvailability = async (node, available) => {
  return fetchAPI('/recovery-tests/node-availability', {
    method: 'POST',
    body: JSON.stringify({ node, available }),
  });
};

// ==================== RESILIENT NODE HEALTH ====================

/**
 * Get all nodes health with resilient fetching
 * Returns data even if some nodes are down
 * @returns {Promise<Object>} Node health states
 */
export const getAllNodesHealth = async () => {
  return fetchAPISafe('/status/nodes', {}, 5000) || { nodes: {}, all_online: false };
};

/**
 * Check if a specific node is reachable
 * @param {string} nodeUrl - Base URL of the node
 * @returns {Promise<boolean>} True if node is reachable
 */
export const checkNodeHealth = async (nodeUrl) => {
  try {
    const result = await fetchFromNode(nodeUrl, '/health', {}, 3000);
    return result?.status === 'ok';
  } catch {
    return false;
  }
};

/**
 * Get node status tracking info
 * @returns {Object} Current node status tracking
 */
export const getNodeStatusTracking = () => {
  return { ...nodeStatus };
};

/**
 * Reset node availability (mark all as available for retry)
 */
export const resetNodeAvailabilityTracking = () => {
  for (const node of Object.keys(nodeStatus)) {
    nodeStatus[node].available = true;
    nodeStatus[node].lastError = null;
  }
};

/**
 * Export node URLs for external use
 */
export { NODE_URLS, getAvailableApiUrl };