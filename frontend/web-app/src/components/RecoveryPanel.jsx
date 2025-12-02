import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Play, Square, Download, AlertTriangle, CheckCircle, XCircle, Loader2, Database } from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

/**
 * Recovery Panel Component
 * Displays node health, recovery status, and controls for recovery operations
 */
export function RecoveryPanel() {
  const [replicationStatus, setReplicationStatus] = useState(null);
  const [recoveryFlag, setRecoveryFlag] = useState(null);
  const [activeJob, setActiveJob] = useState(null);
  const [jobLogs, setJobLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [pollingActive, setPollingActive] = useState(false);

  // Fetch replication status
  const fetchReplicationStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/status/replication`);
      if (response.ok) {
        const data = await response.json();
        setReplicationStatus(data);
      }
    } catch (err) {
      console.error('Failed to fetch replication status:', err);
    }
  }, []);

  // Fetch recovery flag status
  const fetchRecoveryFlag = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/recovery/flag`);
      if (response.ok) {
        const data = await response.json();
        setRecoveryFlag(data);
      }
    } catch (err) {
      console.error('Failed to fetch recovery flag:', err);
    }
  }, []);

  // Fetch active job
  const fetchActiveJob = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/recovery/active`);
      if (response.ok) {
        const data = await response.json();
        setActiveJob(data.active_job);
        return data.active_job;
      }
    } catch (err) {
      console.error('Failed to fetch active job:', err);
    }
    return null;
  }, []);

  // Fetch job logs
  const fetchJobLogs = useCallback(async (jobId) => {
    if (!jobId) return;
    try {
      const response = await fetch(`${API_BASE_URL}/recovery/logs/${jobId}?limit=50`);
      if (response.ok) {
        const data = await response.json();
        setJobLogs(data.logs || []);
      }
    } catch (err) {
      console.error('Failed to fetch job logs:', err);
    }
  }, []);

  // Start a recovery job
  const startRecovery = async (mode, options = {}) => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`${API_BASE_URL}/recovery/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, ...options }),
      });
      
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Failed to start recovery');
      }
      
      const data = await response.json();
      setPollingActive(true);
      
      // Immediately fetch active job
      await fetchActiveJob();
      
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // Abort the active job
  const abortRecovery = async () => {
    if (!activeJob?.job_id) return;
    
    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/recovery/abort/${activeJob.job_id}`, {
        method: 'POST',
      });
      
      if (response.ok) {
        setPollingActive(false);
        await fetchActiveJob();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // Request snapshot from a peer
  const forceSnapshot = async (peer, partition = null) => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`${API_BASE_URL}/recovery/force_snapshot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ peer, partition }),
      });
      
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Failed to request snapshot');
      }
      
      const data = await response.json();
      alert(`Snapshot request queued for ${peer}`);
      
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // Download logs as text file
  const downloadLogs = () => {
    if (!jobLogs.length) return;
    
    const logText = jobLogs
      .map(log => `[${log.timestamp}] ${log.level.toUpperCase()}: ${log.message} ${JSON.stringify(log.details || {})}`)
      .join('\n');
    
    const blob = new Blob([logText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `recovery-logs-${activeJob?.job_id || 'unknown'}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Initial fetch and polling
  useEffect(() => {
    fetchReplicationStatus();
    fetchRecoveryFlag();
    fetchActiveJob();
    
    const interval = setInterval(() => {
      fetchReplicationStatus();
      fetchRecoveryFlag();
    }, 5000);
    
    return () => clearInterval(interval);
  }, [fetchReplicationStatus, fetchRecoveryFlag, fetchActiveJob]);

  // Poll active job status and logs
  useEffect(() => {
    if (!pollingActive && !activeJob) return;
    
    const pollJob = async () => {
      const job = await fetchActiveJob();
      if (job?.job_id) {
        await fetchJobLogs(job.job_id);
        
        // Stop polling if job completed
        if (['ready', 'failed', 'aborted'].includes(job.state)) {
          setPollingActive(false);
        }
      } else {
        setPollingActive(false);
      }
    };
    
    const interval = setInterval(pollJob, 2000);
    pollJob(); // Initial fetch
    
    return () => clearInterval(interval);
  }, [pollingActive, fetchActiveJob, fetchJobLogs, activeJob?.job_id]);

  // Get status icon based on state
  const getStatusIcon = (status) => {
    switch (status?.toLowerCase()) {
      case 'online':
      case 'ready':
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'error':
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-500" />;
      case 'syncing':
      case 'applying':
      case 'checking':
        return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />;
      case 'degraded':
      case 'gating':
        return <AlertTriangle className="w-4 h-4 text-yellow-500" />;
      default:
        return <Database className="w-4 h-4 text-gray-400" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-cyan-700">Recovery Dashboard</h2>
        <button
          onClick={() => {
            fetchReplicationStatus();
            fetchRecoveryFlag();
            fetchActiveJob();
          }}
          className="flex items-center gap-2 px-3 py-1.5 text-sm bg-cyan-100 text-cyan-700 rounded hover:bg-cyan-200 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
          <XCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
          <p className="text-red-700">{error}</p>
          <button
            onClick={() => setError(null)}
            className="ml-auto text-red-500 hover:text-red-700"
          >
            ×
          </button>
        </div>
      )}

      {/* Write Gating Warning */}
      {recoveryFlag?.writes_gated && (
        <div className="bg-yellow-50 border-2 border-yellow-400 rounded-lg p-4 flex items-center gap-3">
          <AlertTriangle className="w-6 h-6 text-yellow-600 flex-shrink-0" />
          <div>
            <p className="font-semibold text-yellow-800">Writes Gated</p>
            <p className="text-sm text-yellow-700">
              Write operations are blocked during recovery finalization. Read operations are available.
            </p>
          </div>
        </div>
      )}

      {/* Node Health Grid */}
      <div className="bg-white rounded-lg border-2 border-cyan-200 p-4">
        <h3 className="font-semibold text-gray-700 mb-3">Node Health</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {replicationStatus?.nodes?.map((node) => (
            <div
              key={node.name}
              className={`p-4 rounded-lg border-2 ${
                node.status === 'online' 
                  ? 'border-green-200 bg-green-50' 
                  : node.status === 'error'
                  ? 'border-red-200 bg-red-50'
                  : 'border-yellow-200 bg-yellow-50'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium text-gray-800">{node.name}</span>
                {getStatusIcon(node.status)}
              </div>
              <div className="text-sm text-gray-600 space-y-1">
                <p>Role: <span className="font-medium">{node.role}</span></p>
                <p>Status: <span className="font-medium">{node.status}</span></p>
                {node.promoted && (
                  <p className="text-orange-600 font-medium">⚡ Promoted</p>
                )}
                {node.last_seen_lamport !== undefined && (
                  <p>Last Lamport: <span className="font-mono">{node.last_seen_lamport}</span></p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Replication Metrics */}
      {replicationStatus && (
        <div className="bg-white rounded-lg border-2 border-cyan-200 p-4">
          <h3 className="font-semibold text-gray-700 mb-3">Replication Metrics</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center p-3 bg-gray-50 rounded">
              <p className="text-2xl font-bold text-cyan-600">
                {replicationStatus.replicator?.total_inserted || 0}
              </p>
              <p className="text-sm text-gray-600">Ops Replicated</p>
            </div>
            <div className="text-center p-3 bg-gray-50 rounded">
              <p className="text-2xl font-bold text-green-600">
                {replicationStatus.applier?.applied_count || 0}
              </p>
              <p className="text-sm text-gray-600">Ops Applied</p>
            </div>
            <div className="text-center p-3 bg-gray-50 rounded">
              <p className="text-2xl font-bold text-yellow-600">
                {replicationStatus.applier?.skipped_count || 0}
              </p>
              <p className="text-sm text-gray-600">Ops Skipped</p>
            </div>
            <div className="text-center p-3 bg-gray-50 rounded">
              <p className="text-2xl font-bold text-red-600">
                {replicationStatus.applier?.failed_count || 0}
              </p>
              <p className="text-sm text-gray-600">Ops Failed</p>
            </div>
          </div>
        </div>
      )}

      {/* Recovery Actions */}
      <div className="bg-white rounded-lg border-2 border-cyan-200 p-4">
        <h3 className="font-semibold text-gray-700 mb-3">Recovery Actions</h3>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => startRecovery('leader')}
            disabled={isLoading || activeJob}
            className="flex items-center gap-2 px-4 py-2 bg-cyan-500 text-white rounded hover:bg-cyan-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Play className="w-4 h-4" />
            Start Leader Reconverge
          </button>
          
          <button
            onClick={() => startRecovery('node')}
            disabled={isLoading || activeJob}
            className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Play className="w-4 h-4" />
            Start Node Rejoin
          </button>
          
          <button
            onClick={() => {
              const since = prompt('Enter promotion start timestamp (ISO format, or leave empty):');
              startRecovery('promotion', { since_ts: since || undefined });
            }}
            disabled={isLoading || activeJob}
            className="flex items-center gap-2 px-4 py-2 bg-purple-500 text-white rounded hover:bg-purple-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Play className="w-4 h-4" />
            Start Promotion Resync
          </button>
          
          <div className="border-l border-gray-300 mx-2" />
          
          <button
            onClick={() => forceSnapshot('node1', 'low')}
            disabled={isLoading}
            className="flex items-center gap-2 px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Download className="w-4 h-4" />
            Snapshot Node1
          </button>
          
          <button
            onClick={() => forceSnapshot('node2', 'high')}
            disabled={isLoading}
            className="flex items-center gap-2 px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Download className="w-4 h-4" />
            Snapshot Node2
          </button>
        </div>
      </div>

      {/* Active Job Status */}
      {activeJob && (
        <div className="bg-white rounded-lg border-2 border-cyan-200 p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-gray-700">Active Recovery Job</h3>
            <div className="flex items-center gap-2">
              <span className={`px-2 py-1 rounded text-sm font-medium ${
                activeJob.state === 'ready' ? 'bg-green-100 text-green-700' :
                activeJob.state === 'failed' ? 'bg-red-100 text-red-700' :
                activeJob.state === 'aborted' ? 'bg-gray-100 text-gray-700' :
                'bg-blue-100 text-blue-700'
              }`}>
                {activeJob.state.toUpperCase()}
              </span>
              {!['ready', 'failed', 'aborted'].includes(activeJob.state) && (
                <button
                  onClick={abortRecovery}
                  disabled={isLoading}
                  className="flex items-center gap-1 px-3 py-1 bg-red-500 text-white rounded text-sm hover:bg-red-600 disabled:opacity-50"
                >
                  <Square className="w-3 h-3" />
                  Abort
                </button>
              )}
            </div>
          </div>
          
          {/* Job Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="text-center p-2 bg-gray-50 rounded">
              <p className="text-xl font-bold text-cyan-600">
                {activeJob.metrics?.ops_fetched || 0}
              </p>
              <p className="text-xs text-gray-600">Ops Fetched</p>
            </div>
            <div className="text-center p-2 bg-gray-50 rounded">
              <p className="text-xl font-bold text-green-600">
                {activeJob.metrics?.ops_applied || 0}
              </p>
              <p className="text-xs text-gray-600">Ops Applied</p>
            </div>
            <div className="text-center p-2 bg-gray-50 rounded">
              <p className="text-xl font-bold text-blue-600">
                {activeJob.metrics?.last_applied_lamport || 0}
              </p>
              <p className="text-xs text-gray-600">Last Lamport</p>
            </div>
            <div className="text-center p-2 bg-gray-50 rounded">
              <p className="text-xl font-bold text-purple-600">
                {activeJob.metrics?.ops_remaining || 0}
              </p>
              <p className="text-xs text-gray-600">Remaining</p>
            </div>
          </div>
          
          {/* Progress Bar */}
          {activeJob.metrics?.ops_fetched > 0 && (
            <div className="mb-4">
              <div className="flex justify-between text-sm text-gray-600 mb-1">
                <span>Progress</span>
                <span>
                  {Math.round((activeJob.metrics.ops_applied / activeJob.metrics.ops_fetched) * 100)}%
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-cyan-500 h-2 rounded-full transition-all duration-300"
                  style={{
                    width: `${Math.min(100, (activeJob.metrics.ops_applied / activeJob.metrics.ops_fetched) * 100)}%`
                  }}
                />
              </div>
            </div>
          )}
          
          {/* ETA */}
          {activeJob.metrics?.estimated_eta_seconds != null && activeJob.state === 'applying' && (
            <p className="text-sm text-gray-600">
              Estimated time remaining: {Math.round(activeJob.metrics.estimated_eta_seconds)}s
            </p>
          )}
        </div>
      )}

      {/* Live Logs */}
      {(activeJob || jobLogs.length > 0) && (
        <div className="bg-white rounded-lg border-2 border-cyan-200 p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-gray-700">Recovery Logs</h3>
            <button
              onClick={downloadLogs}
              disabled={!jobLogs.length}
              className="flex items-center gap-1 px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 disabled:opacity-50"
            >
              <Download className="w-4 h-4" />
              Download
            </button>
          </div>
          
          <div className="bg-gray-900 rounded-lg p-4 max-h-64 overflow-y-auto font-mono text-sm">
            {jobLogs.length === 0 ? (
              <p className="text-gray-500">No logs available</p>
            ) : (
              jobLogs.map((log, idx) => (
                <div key={idx} className={`mb-1 ${
                  log.level === 'error' ? 'text-red-400' :
                  log.level === 'warning' ? 'text-yellow-400' :
                  log.level === 'debug' ? 'text-gray-500' :
                  'text-green-400'
                }`}>
                  <span className="text-gray-500">
                    [{new Date(log.timestamp).toLocaleTimeString()}]
                  </span>
                  {' '}
                  <span className="font-semibold">{log.level.toUpperCase()}</span>
                  {': '}
                  {log.message}
                  {log.details && Object.keys(log.details).length > 0 && (
                    <span className="text-gray-400">
                      {' '}
                      {JSON.stringify(log.details)}
                    </span>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default RecoveryPanel;
