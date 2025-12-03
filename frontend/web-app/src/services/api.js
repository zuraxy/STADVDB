// API Service - Centralized data fetching functions
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

// Node-specific base URLs for direct communication
const NODE_URLS = {
  node0: import.meta.env.VITE_NODE0_URL || API_BASE_URL,
  node1: import.meta.env.VITE_NODE1_URL || '',
  node2: import.meta.env.VITE_NODE2_URL || '',
};

// Default timeout for API requests (ms)
const DEFAULT_TIMEOUT = 5000;

/**
 * Create an AbortController with timeout
 */
const createTimeoutController = (timeoutMs = DEFAULT_TIMEOUT) => {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  return { controller, timeoutId };
};

/**
 * Generic fetch wrapper with error handling and timeout
 */
const fetchAPI = async (endpoint, options = {}) => {
  const { controller, timeoutId } = createTimeoutController(options.timeout || DEFAULT_TIMEOUT);
  
  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
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
    if (error.name === 'AbortError') {
      console.error(`API Timeout (${endpoint}): Request timed out`);
      throw new Error(`Request timeout: ${endpoint}`);
    }
    console.error(`API Error (${endpoint}):`, error);
    throw error;
  }
};

/**
 * Fetch from a specific node with graceful error handling
 * Returns { success: boolean, data?: any, error?: string }
 */
const fetchFromNode = async (nodeUrl, endpoint, options = {}) => {
  if (!nodeUrl) {
    return { success: false, error: 'Node URL not configured' };
  }
  
  const { controller, timeoutId } = createTimeoutController(options.timeout || DEFAULT_TIMEOUT);
  
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
      return { success: false, error: `HTTP ${response.status}` };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      return { success: false, error: 'Request timeout' };
    }
    return { success: false, error: error.message || 'Network error' };
  }
};

// ==================== ORDER OPERATIONS ====================

/**
 * Fetch all orders from current node
 * @returns {Promise<Array>} Array of all orders
 */
export const fetchAllOrders = async () => {
  try {
    return await fetchAPI('/orders', { timeout: 8000 });
  } catch (error) {
    console.warn('Failed to fetch orders from primary node:', error);
    return [];
  }
};

/**
 * Fetch orders from a specific node's local database with graceful fallback
 * @param {string} nodeName - Name of the node (e.g., 'node1', 'node2')
 * @returns {Promise<Array>} Array of orders from that node (empty on failure)
 */
export const fetchNodeOrders = async (nodeName) => {
  console.log(`📡 Fetching orders from ${nodeName}...`);
  
  // Try direct node connection first if URL is configured
  const directUrl = NODE_URLS[nodeName];
  if (directUrl) {
    const directResult = await fetchFromNode(directUrl, '/orders/local/all', { timeout: 5000 });
    if (directResult.success) {
      console.log(`✅ ${nodeName} (direct) returned ${directResult.data?.length || 0} orders`);
      return directResult.data || [];
    }
    console.warn(`⚠️ Direct connection to ${nodeName} failed:`, directResult.error);
  }
  
  // Fallback: proxy through API base URL
  if (nodeName === 'node0') {
    try {
      const result = await fetchAPI('/orders', { timeout: 5000 });
      console.log(`✅ ${nodeName} returned ${result?.length || 0} orders`);
      return result || [];
    } catch (error) {
      console.error(`❌ Failed to fetch from ${nodeName}:`, error);
      return [];
    }
  }
  
  // Proxy through primary node for other nodes
  try {
    const result = await fetchAPI(`/proxy/node/${nodeName}/orders`, { timeout: 5000 });
    console.log(`✅ ${nodeName} (proxied) returned ${result?.length || 0} orders`);
    return result || [];
  } catch (error) {
    console.error(`❌ Failed to fetch from ${nodeName}:`, error);
    return [];
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
 * Fetch replication + peer node status metadata with graceful timeout
 * Enhanced to include disabled status from peer nodes
 * @returns {Promise<Object>} Replication workers + node health snapshot
 */
export const fetchReplicationStatus = async () => {
  try {
    const status = await fetchAPI('/status/replication', { timeout: 5000 });
    
    // Enhance with disabled status from all nodes
    // Try to fetch disabled status from peers in parallel
    if (status.nodes && status.nodes.length > 0) {
      const disabledChecks = await Promise.allSettled(
        status.nodes.map(async (node) => {
          try {
            const disabledStatus = await getNodeDisabledStatus(node.name);
            return { name: node.name, ...disabledStatus };
          } catch {
            return { name: node.name, disabled: false, unreachable: true };
          }
        })
      );
      
      // Merge disabled status into nodes
      for (let i = 0; i < status.nodes.length; i++) {
        const check = disabledChecks[i];
        if (check.status === 'fulfilled') {
          const checkResult = check.value;
          status.nodes[i].disabled = checkResult.disabled;
          status.nodes[i].unreachable = checkResult.unreachable;
          
          // Update status to 'disabled' if node is disabled
          if (checkResult.disabled) {
            status.nodes[i].status = 'disabled';
          }
        }
      }
    }
    
    return status;
  } catch (error) {
    console.warn('Failed to fetch replication status:', error);
    // Return minimal structure so UI doesn't crash
    return {
      node: 'unknown',
      nodes: [],
      error: error.message,
    };
  }
};

/**
 * Check health of a specific node directly
 * @param {string} nodeName - Name of the node
 * @returns {Promise<Object>} { online: boolean, error?: string }
 */
export const checkNodeHealth = async (nodeName) => {
  const nodeUrl = NODE_URLS[nodeName];
  if (!nodeUrl) {
    // Try via proxy
    try {
      const status = await fetchAPI('/status/replication', { timeout: 3000 });
      const nodeInfo = status?.nodes?.find(n => n.name?.toLowerCase() === nodeName.toLowerCase());
      return {
        online: nodeInfo?.status === 'online',
        status: nodeInfo?.status || 'unknown',
        error: nodeInfo?.error,
      };
    } catch {
      return { online: false, status: 'error', error: 'Cannot reach node' };
    }
  }
  
  const result = await fetchFromNode(nodeUrl, '/health', { timeout: 3000 });
  return {
    online: result.success,
    status: result.success ? 'online' : 'error',
    error: result.error,
  };
};

/**
 * Fetch health status from all nodes independently
 * @returns {Promise<Object>} { node0: {...}, node1: {...}, node2: {...} }
 */
export const fetchAllNodeHealth = async () => {
  const nodes = ['node0', 'node1', 'node2'];
  const results = await Promise.all(
    nodes.map(async (nodeName) => {
      const health = await checkNodeHealth(nodeName);
      return [nodeName, health];
    })
  );
  return Object.fromEntries(results);
};

/**
 * Fetch detailed metrics from all nodes
 * @returns {Promise<Object>} Metrics from each node with applier and replicator stats
 */
export const fetchAllNodeMetrics = async () => {
  // Fetch from the current node's /status/replication endpoint
  // This endpoint already contains metrics for all nodes
  try {
    const response = await fetchAPI('/status/replication', { timeout: 5000 });
    
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

// ==================== NODE POWER CONTROL ====================

/**
 * Toggle a node's disabled state (simulated power off/on)
 * @param {string} nodeName - The node to toggle ('node0', 'node1', 'node2')
 * @param {boolean} disable - True to disable (power off), false to enable (power on)
 * @returns {Promise<Object>} { node, disabled, status }
 */
export const toggleNodePower = async (nodeName, disable) => {
  // Try direct node connection first
  const nodeUrl = NODE_URLS[nodeName];
  if (nodeUrl) {
    const result = await fetchFromNode(nodeUrl, '/admin/toggle-disabled', {
      method: 'POST',
      body: JSON.stringify({ disabled: disable }),
      timeout: 5000,
    });
    if (result.success) {
      return result.data;
    }
  }
  
  // Fallback to proxy via primary node
  return fetchAPI(`/admin/node/${nodeName}/toggle`, {
    method: 'POST',
    body: JSON.stringify({ disabled: disable }),
  });
};

/**
 * Get the disabled status of a specific node
 * @param {string} nodeName - The node to check
 * @returns {Promise<Object>} { node, disabled }
 */
export const getNodeDisabledStatus = async (nodeName) => {
  const nodeUrl = NODE_URLS[nodeName];
  if (nodeUrl) {
    const result = await fetchFromNode(nodeUrl, '/admin/disabled-status', { timeout: 3000 });
    if (result.success) {
      return result.data;
    }
    return { node: nodeName, disabled: false, unreachable: true, error: result.error };
  }
  
  try {
    return await fetchAPI(`/admin/node/${nodeName}/disabled-status`);
  } catch {
    return { node: nodeName, disabled: false, unreachable: true };
  }
};

/**
 * Get disabled status for all nodes
 * @returns {Promise<Object>} { node0: {...}, node1: {...}, node2: {...} }
 */
export const getAllNodesDisabledStatus = async () => {
  const nodes = ['node0', 'node1', 'node2'];
  const results = await Promise.all(
    nodes.map(async (nodeName) => {
      const status = await getNodeDisabledStatus(nodeName);
      return [nodeName, status];
    })
  );
  return Object.fromEntries(results);
};

// ==================== AVAILABLE NODES FOR ORCHESTRATOR ====================

/**
 * Get list of available (online and enabled) nodes for orchestrator
 * @returns {Promise<Array<string>>} List of available node names
 */
export const getAvailableNodes = async () => {
  try {
    const [health, disabled] = await Promise.all([
      fetchAllNodeHealth(),
      getAllNodesDisabledStatus(),
    ]);
    
    const available = [];
    for (const nodeName of ['node0', 'node1', 'node2']) {
      const isOnline = health[nodeName]?.online;
      const isDisabled = disabled[nodeName]?.disabled;
      const isUnreachable = disabled[nodeName]?.unreachable;
      
      if (isOnline && !isDisabled && !isUnreachable) {
        available.push(nodeName);
      }
    }
    
    return available;
  } catch (error) {
    console.error('Failed to get available nodes:', error);
    return ['node0', 'node1', 'node2']; // Fallback to all nodes
  }
};