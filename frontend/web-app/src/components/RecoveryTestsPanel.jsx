import { useState, useEffect, useCallback } from 'react';
import { 
  Play, 
  Square, 
  RefreshCw, 
  CheckCircle, 
  XCircle, 
  AlertTriangle, 
  Loader2,
  Database,
  ArrowRight,
  History,
  Trash2,
  ToggleLeft,
  ToggleRight,
  Server
} from 'lucide-react';
import {
  getRecoveryTestCases,
  runRecoveryTest,
  getCurrentRecoveryTest,
  getRecoveryTestHistory,
  clearRecoveryTestHistory,
  getNodeAvailability,
  setNodeAvailability,
} from '../services/api';

/**
 * Recovery Tests Panel - UI for running 4 recovery test scenarios
 */
export function RecoveryTestsPanel() {
  const [testCases, setTestCases] = useState([]);
  const [currentTest, setCurrentTest] = useState(null);
  const [testHistory, setTestHistory] = useState([]);
  const [nodeAvailability, setNodeAvailabilityState] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedResult, setSelectedResult] = useState(null);

  // Fetch test cases
  const fetchTestCases = useCallback(async () => {
    try {
      const data = await getRecoveryTestCases();
      setTestCases(data.cases || []);
    } catch (err) {
      console.error('Failed to fetch test cases:', err);
    }
  }, []);

  // Fetch current test
  const fetchCurrentTest = useCallback(async () => {
    try {
      const data = await getCurrentRecoveryTest();
      setCurrentTest(data.current_test);
    } catch (err) {
      console.error('Failed to fetch current test:', err);
    }
  }, []);

  // Fetch test history
  const fetchHistory = useCallback(async () => {
    try {
      const data = await getRecoveryTestHistory();
      setTestHistory(data.history || []);
    } catch (err) {
      console.error('Failed to fetch history:', err);
    }
  }, []);

  // Fetch node availability
  const fetchNodeAvailability = useCallback(async () => {
    try {
      const data = await getNodeAvailability();
      setNodeAvailabilityState(data.availability || {});
    } catch (err) {
      console.error('Failed to fetch node availability:', err);
    }
  }, []);

  // Run a test
  const handleRunTest = async (testCase) => {
    setIsLoading(true);
    setError(null);
    
    try {
      const result = await runRecoveryTest(testCase);
      setSelectedResult(result);
      await fetchHistory();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
      setCurrentTest(null);
    }
  };

  // Toggle node availability
  const handleToggleNode = async (node) => {
    const currentState = nodeAvailability[node] ?? true;
    try {
      await setNodeAvailability(node, !currentState);
      await fetchNodeAvailability();
    } catch (err) {
      setError(err.message);
    }
  };

  // Clear history
  const handleClearHistory = async () => {
    try {
      await clearRecoveryTestHistory();
      setTestHistory([]);
      setSelectedResult(null);
    } catch (err) {
      setError(err.message);
    }
  };

  // Initial fetch
  useEffect(() => {
    fetchTestCases();
    fetchCurrentTest();
    fetchHistory();
    fetchNodeAvailability();
  }, [fetchTestCases, fetchCurrentTest, fetchHistory, fetchNodeAvailability]);

  // Poll current test status
  useEffect(() => {
    if (!currentTest) return;
    
    const interval = setInterval(() => {
      fetchCurrentTest();
    }, 1000);
    
    return () => clearInterval(interval);
  }, [currentTest, fetchCurrentTest]);

  // Get status badge color
  const getStatusColor = (status) => {
    switch (status?.toLowerCase()) {
      case 'passed':
        return 'bg-green-100 text-green-700 border-green-300';
      case 'failed':
        return 'bg-red-100 text-red-700 border-red-300';
      case 'running':
        return 'bg-blue-100 text-blue-700 border-blue-300';
      case 'aborted':
        return 'bg-gray-100 text-gray-700 border-gray-300';
      default:
        return 'bg-yellow-100 text-yellow-700 border-yellow-300';
    }
  };

  // Get status icon
  const getStatusIcon = (status) => {
    switch (status?.toLowerCase()) {
      case 'passed':
        return <CheckCircle className="w-4 h-4 text-green-600" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-600" />;
      case 'running':
        return <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />;
      default:
        return <AlertTriangle className="w-4 h-4 text-yellow-600" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-cyan-700">Recovery Test Suite</h2>
          <p className="text-sm text-gray-600">Test node failure and recovery scenarios</p>
        </div>
        <button
          onClick={() => {
            fetchTestCases();
            fetchHistory();
            fetchNodeAvailability();
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
          <button onClick={() => setError(null)} className="ml-auto text-red-500 hover:text-red-700">×</button>
        </div>
      )}

      {/* Node Availability Controls */}
      <div className="bg-white rounded-lg border-2 border-cyan-200 p-4">
        <h3 className="font-semibold text-gray-700 mb-3 flex items-center gap-2">
          <Server className="w-4 h-4" />
          Node Availability Controls (Simulation)
        </h3>
        <p className="text-sm text-gray-600 mb-4">
          Toggle node availability to simulate outages during recovery tests.
        </p>
        <div className="grid grid-cols-3 gap-4">
          {['node0', 'node1', 'node2'].map((node) => {
            const isAvailable = nodeAvailability[node] ?? true;
            return (
              <button
                key={node}
                onClick={() => handleToggleNode(node)}
                className={`p-4 rounded-lg border-2 transition-all ${
                  isAvailable
                    ? 'border-green-300 bg-green-50 hover:bg-green-100'
                    : 'border-red-300 bg-red-50 hover:bg-red-100'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-gray-800 capitalize">{node}</span>
                  {isAvailable ? (
                    <ToggleRight className="w-6 h-6 text-green-600" />
                  ) : (
                    <ToggleLeft className="w-6 h-6 text-red-600" />
                  )}
                </div>
                <p className={`text-sm ${isAvailable ? 'text-green-700' : 'text-red-700'}`}>
                  {isAvailable ? 'Online' : 'Offline (Simulated)'}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Test Cases */}
      <div className="bg-white rounded-lg border-2 border-cyan-200 p-4">
        <h3 className="font-semibold text-gray-700 mb-3 flex items-center gap-2">
          <Play className="w-4 h-4" />
          Recovery Test Cases
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {testCases.map((testCase) => (
            <div
              key={testCase.id}
              className="p-4 rounded-lg border-2 border-gray-200 hover:border-cyan-300 transition-colors"
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <h4 className="font-medium text-gray-800">{testCase.name}</h4>
                  <span className="text-xs text-cyan-600 font-mono">{testCase.id.toUpperCase()}</span>
                </div>
                <button
                  onClick={() => handleRunTest(testCase.id)}
                  disabled={isLoading || currentTest}
                  className="flex items-center gap-1 px-3 py-1.5 bg-cyan-500 text-white rounded text-sm hover:bg-cyan-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Play className="w-4 h-4" />
                  )}
                  Run
                </button>
              </div>
              <p className="text-sm text-gray-600">{testCase.description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Current Test Status */}
      {currentTest && (
        <div className="bg-white rounded-lg border-2 border-blue-200 p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-gray-700 flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
              Running: {currentTest.test_name}
            </h3>
            <span className={`px-2 py-1 rounded text-sm font-medium border ${getStatusColor(currentTest.status)}`}>
              {currentTest.status.toUpperCase()}
            </span>
          </div>
          <div className="grid grid-cols-4 gap-4 text-center">
            <div className="p-2 bg-gray-50 rounded">
              <p className="text-xl font-bold text-cyan-600">{currentTest.ops_created || 0}</p>
              <p className="text-xs text-gray-600">Ops Created</p>
            </div>
            <div className="p-2 bg-gray-50 rounded">
              <p className="text-xl font-bold text-green-600">{currentTest.ops_replicated || 0}</p>
              <p className="text-xs text-gray-600">Ops Replicated</p>
            </div>
            <div className="p-2 bg-gray-50 rounded">
              <p className="text-xl font-bold text-red-600">{currentTest.ops_failed || 0}</p>
              <p className="text-xs text-gray-600">Ops Failed</p>
            </div>
            <div className="p-2 bg-gray-50 rounded">
              <p className="text-xl font-bold text-yellow-600">{currentTest.retry_attempts || 0}</p>
              <p className="text-xs text-gray-600">Retries</p>
            </div>
          </div>
        </div>
      )}

      {/* Test History */}
      <div className="bg-white rounded-lg border-2 border-cyan-200 p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-700 flex items-center gap-2">
            <History className="w-4 h-4" />
            Test History
          </h3>
          {testHistory.length > 0 && (
            <button
              onClick={handleClearHistory}
              className="flex items-center gap-1 px-2 py-1 text-sm text-red-600 hover:text-red-700 hover:bg-red-50 rounded transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              Clear
            </button>
          )}
        </div>
        
        {testHistory.length === 0 ? (
          <p className="text-gray-500 text-center py-4">No tests run yet</p>
        ) : (
          <div className="space-y-2">
            {testHistory.slice().reverse().map((test, idx) => (
              <button
                key={idx}
                onClick={() => setSelectedResult(test)}
                className={`w-full p-3 rounded-lg border-2 text-left transition-colors ${
                  selectedResult === test
                    ? 'border-cyan-400 bg-cyan-50'
                    : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {getStatusIcon(test.status)}
                    <span className="font-medium text-gray-800">{test.test_name}</span>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium border ${getStatusColor(test.status)}`}>
                    {test.status.toUpperCase()}
                  </span>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  {new Date(test.started_at).toLocaleString()}
                </p>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Selected Result Detail */}
      {selectedResult && (
        <div className="bg-white rounded-lg border-2 border-cyan-200 p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-gray-700">Test Result Details</h3>
            <button
              onClick={() => setSelectedResult(null)}
              className="text-gray-500 hover:text-gray-700"
            >
              ×
            </button>
          </div>

          {/* Summary */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
            <div className="text-center p-2 bg-gray-50 rounded">
              <p className="text-xl font-bold text-cyan-600">{selectedResult.ops_created}</p>
              <p className="text-xs text-gray-600">Created</p>
            </div>
            <div className="text-center p-2 bg-gray-50 rounded">
              <p className="text-xl font-bold text-green-600">{selectedResult.ops_replicated}</p>
              <p className="text-xs text-gray-600">Replicated</p>
            </div>
            <div className="text-center p-2 bg-gray-50 rounded">
              <p className="text-xl font-bold text-red-600">{selectedResult.ops_failed}</p>
              <p className="text-xs text-gray-600">Failed</p>
            </div>
            <div className="text-center p-2 bg-gray-50 rounded">
              <p className="text-xl font-bold text-yellow-600">{selectedResult.retry_attempts}</p>
              <p className="text-xs text-gray-600">Retries</p>
            </div>
            <div className="text-center p-2 bg-gray-50 rounded">
              <p className="text-sm font-bold text-purple-600">{selectedResult.reconciliation_status}</p>
              <p className="text-xs text-gray-600">Reconciliation</p>
            </div>
          </div>

          {/* Before/After States */}
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <h4 className="font-medium text-gray-700 mb-2">Before States</h4>
              <div className="space-y-2">
                {Object.entries(selectedResult.before_states || {}).map(([node, state]) => (
                  <div key={node} className="p-2 bg-gray-50 rounded text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{node}</span>
                      <span className={state.is_online ? 'text-green-600' : 'text-red-600'}>
                        {state.is_online ? 'Online' : 'Offline'}
                      </span>
                    </div>
                    <p className="text-gray-600">Orders: {state.order_count} | Lamport: {state.max_lamport}</p>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h4 className="font-medium text-gray-700 mb-2">After States</h4>
              <div className="space-y-2">
                {Object.entries(selectedResult.after_states || {}).map(([node, state]) => (
                  <div key={node} className="p-2 bg-gray-50 rounded text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{node}</span>
                      <span className={state.is_online ? 'text-green-600' : 'text-red-600'}>
                        {state.is_online ? 'Online' : 'Offline'}
                      </span>
                    </div>
                    <p className="text-gray-600">Orders: {state.order_count} | Lamport: {state.max_lamport}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Logs */}
          <div>
            <h4 className="font-medium text-gray-700 mb-2">Test Logs</h4>
            <div className="bg-gray-900 rounded-lg p-4 max-h-64 overflow-y-auto font-mono text-sm">
              {(selectedResult.logs || []).map((log, idx) => (
                <div
                  key={idx}
                  className={`mb-1 ${
                    log.level === 'error' ? 'text-red-400' :
                    log.level === 'warning' ? 'text-yellow-400' :
                    log.level === 'debug' ? 'text-gray-500' :
                    'text-green-400'
                  }`}
                >
                  <span className="text-gray-500">[{new Date(log.timestamp).toLocaleTimeString()}]</span>
                  {' '}
                  <span className="text-cyan-400">[{log.phase}]</span>
                  {log.node && <span className="text-purple-400"> @{log.node}</span>}
                  {': '}
                  {log.message}
                  {log.details && Object.keys(log.details).length > 0 && (
                    <span className="text-gray-400"> {JSON.stringify(log.details)}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default RecoveryTestsPanel;
