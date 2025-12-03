import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Play,
  Square,
  RefreshCw,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
  Database,
  Server,
  Power,
  PowerOff,
  Activity,
  Clock,
  Zap,
  Shield,
  Users,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Download,
  RotateCcw,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

// Event type colors and icons
const eventStyles = {
  heartbeat_sent: { color: 'text-slate-400', bg: 'bg-slate-100' },
  heartbeat_received: { color: 'text-slate-400', bg: 'bg-slate-100' },
  heartbeat_timeout: { color: 'text-amber-600', bg: 'bg-amber-100' },
  node_up: { color: 'text-emerald-600', bg: 'bg-emerald-100' },
  node_down: { color: 'text-red-600', bg: 'bg-red-100' },
  node_recovering: { color: 'text-blue-600', bg: 'bg-blue-100' },
  node_synced: { color: 'text-emerald-600', bg: 'bg-emerald-100' },
  election_started: { color: 'text-purple-600', bg: 'bg-purple-100' },
  election_vote: { color: 'text-purple-500', bg: 'bg-purple-50' },
  election_won: { color: 'text-purple-700', bg: 'bg-purple-200' },
  election_lost: { color: 'text-slate-600', bg: 'bg-slate-100' },
  leader_elected: { color: 'text-purple-600', bg: 'bg-purple-100' },
  recovery_started: { color: 'text-blue-600', bg: 'bg-blue-100' },
  recovery_fetching: { color: 'text-blue-500', bg: 'bg-blue-50' },
  recovery_applying: { color: 'text-blue-500', bg: 'bg-blue-50' },
  recovery_completed: { color: 'text-emerald-600', bg: 'bg-emerald-100' },
  recovery_failed: { color: 'text-red-600', bg: 'bg-red-100' },
  replication_queued: { color: 'text-cyan-600', bg: 'bg-cyan-100' },
  replication_retry: { color: 'text-amber-600', bg: 'bg-amber-100' },
  replication_failed: { color: 'text-red-600', bg: 'bg-red-100' },
  replication_success: { color: 'text-emerald-600', bg: 'bg-emerald-100' },
  writes_gated: { color: 'text-amber-600', bg: 'bg-amber-100' },
  writes_enabled: { color: 'text-emerald-600', bg: 'bg-emerald-100' },
  write_rejected: { color: 'text-red-600', bg: 'bg-red-100' },
};

const getEventIcon = (eventType) => {
  const iconMap = {
    heartbeat_sent: <Activity className="w-3.5 h-3.5" />,
    heartbeat_received: <Activity className="w-3.5 h-3.5" />,
    heartbeat_timeout: <Clock className="w-3.5 h-3.5" />,
    node_up: <Power className="w-3.5 h-3.5" />,
    node_down: <PowerOff className="w-3.5 h-3.5" />,
    node_recovering: <RotateCcw className="w-3.5 h-3.5" />,
    node_synced: <CheckCircle className="w-3.5 h-3.5" />,
    election_started: <Users className="w-3.5 h-3.5" />,
    election_vote: <Users className="w-3.5 h-3.5" />,
    election_won: <Shield className="w-3.5 h-3.5" />,
    election_lost: <XCircle className="w-3.5 h-3.5" />,
    leader_elected: <Shield className="w-3.5 h-3.5" />,
    recovery_started: <RefreshCw className="w-3.5 h-3.5" />,
    recovery_fetching: <Download className="w-3.5 h-3.5" />,
    recovery_applying: <Zap className="w-3.5 h-3.5" />,
    recovery_completed: <CheckCircle className="w-3.5 h-3.5" />,
    recovery_failed: <XCircle className="w-3.5 h-3.5" />,
    writes_gated: <AlertTriangle className="w-3.5 h-3.5" />,
    writes_enabled: <CheckCircle className="w-3.5 h-3.5" />,
    write_rejected: <XCircle className="w-3.5 h-3.5" />,
  };
  return iconMap[eventType] || <Activity className="w-3.5 h-3.5" />;
};

// Test scenarios for automated recovery tests
const testScenarios = [
  {
    id: 'leader_failure',
    name: 'Leader Failure & Election',
    description: 'Simulate leader node going down, triggering automatic election and failover.',
    expectedEvents: ['node_down', 'election_started', 'leader_elected', 'node_up', 'recovery_started'],
  },
  {
    id: 'follower_failure',
    name: 'Follower Failure & Rejoin',
    description: 'Simulate a follower node failing and rejoining with automatic catch-up.',
    expectedEvents: ['node_down', 'node_up', 'recovery_started', 'recovery_completed'],
  },
  {
    id: 'network_partition',
    name: 'Network Partition',
    description: 'Simulate both partition nodes (node1 & node2) failing and recovering.',
    expectedEvents: ['node_down', 'node_down', 'node_up', 'node_up', 'recovery_completed'],
  },
  {
    id: 'cascading_failure',
    name: 'Cascading Failure',
    description: 'Test cascading failure where nodes fail one by one and then recover.',
    expectedEvents: ['node_down', 'election_started', 'recovery_started', 'recovery_completed'],
  },
];

/**
 * Unified Recovery Panel Component
 * 
 * Features:
 * - Node status display with ON/OFF controls
 * - Automated recovery test scenarios
 * - Real-time event log (like concurrency orchestrator)
 * - Timeline visualization
 * - All recovery actions are AUTOMATIC
 */
export function UnifiedRecoveryPanel() {
  // Cluster state
  const [clusterStatus, setClusterStatus] = useState(null);
  const [events, setEvents] = useState([]);
  const [latestLamport, setLatestLamport] = useState(0);
  
  // UI state
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedScenario, setSelectedScenario] = useState(null);
  const [runningScenario, setRunningScenario] = useState(null);
  const [scenarioResult, setScenarioResult] = useState(null);
  const [showTimeline, setShowTimeline] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  
  // Refs
  const eventStreamRef = useRef(null);
  const logsEndRef = useRef(null);

  // Fetch cluster status
  const fetchClusterStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/cluster/status`);
      if (response.ok) {
        const data = await response.json();
        setClusterStatus(data);
      }
    } catch (err) {
      console.error('Failed to fetch cluster status:', err);
    }
  }, []);

  // Fetch events
  const fetchEvents = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/cluster/events?limit=100&since_lamport=${latestLamport}`);
      if (response.ok) {
        const data = await response.json();
        if (data.events && data.events.length > 0) {
          setEvents(prev => {
            const newEvents = data.events.filter(
              e => !prev.some(p => p.event_id === e.event_id)
            );
            return [...prev, ...newEvents].slice(-200); // Keep last 200
          });
          setLatestLamport(data.latest_lamport);
        }
      }
    } catch (err) {
      console.error('Failed to fetch events:', err);
    }
  }, [latestLamport]);

  // Toggle node state
  const toggleNode = async (nodeName, currentlyUp) => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`${API_BASE_URL}/cluster/node/${nodeName}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ simulate_down: currentlyUp }),
      });
      
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Failed to toggle node');
      }
      
      await fetchClusterStatus();
      await fetchEvents();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // Run test scenario
  const runScenario = async (scenarioId) => {
    setRunningScenario(scenarioId);
    setScenarioResult(null);
    setError(null);
    
    try {
      const response = await fetch(`${API_BASE_URL}/cluster/test/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ test_id: scenarioId }),
      });
      
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Failed to run scenario');
      }
      
      const result = await response.json();
      setScenarioResult(result);
      await fetchClusterStatus();
      await fetchEvents();
    } catch (err) {
      setError(err.message);
    } finally {
      setRunningScenario(null);
    }
  };

  // Setup SSE stream for real-time events
  const setupEventStream = useCallback(() => {
    if (eventStreamRef.current) {
      eventStreamRef.current.close();
    }
    
    try {
      const eventSource = new EventSource(`${API_BASE_URL}/cluster/events/stream`);
      
      eventSource.onmessage = (e) => {
        try {
          const event = JSON.parse(e.data);
          if (event.event_id) {
            setEvents(prev => {
              if (prev.some(p => p.event_id === event.event_id)) return prev;
              return [...prev, event].slice(-200);
            });
            setLatestLamport(event.lamport_time);
          }
        } catch (err) {
          console.error('Failed to parse event:', err);
        }
      };
      
      eventSource.onerror = () => {
        eventSource.close();
        eventStreamRef.current = null;
      };
      
      eventStreamRef.current = eventSource;
    } catch (err) {
      console.error('Failed to setup event stream:', err);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchClusterStatus();
    fetchEvents();
    setupEventStream();
    
    return () => {
      if (eventStreamRef.current) {
        eventStreamRef.current.close();
      }
    };
  }, [fetchClusterStatus, fetchEvents, setupEventStream]);

  // Auto-refresh
  useEffect(() => {
    if (!autoRefresh) return;
    
    const interval = setInterval(() => {
      fetchClusterStatus();
      if (!eventStreamRef.current) {
        fetchEvents();
      }
    }, 3000);
    
    return () => clearInterval(interval);
  }, [autoRefresh, fetchClusterStatus, fetchEvents]);

  // Auto-scroll logs
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [events]);

  // Format timestamp for display
  const formatTime = (timestamp) => {
    try {
      return new Date(timestamp).toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        fractionalSecondDigits: 3,
      });
    } catch {
      return timestamp;
    }
  };

  // Get node status badge color
  const getNodeBadgeClass = (node) => {
    if (!node) return 'bg-slate-100 text-slate-700 border-slate-200';
    if (!node.effective_alive) return 'bg-red-100 text-red-700 border-red-200';
    if (node.is_simulated_down) return 'bg-amber-100 text-amber-700 border-amber-200';
    if (node.recovery_in_progress) return 'bg-blue-100 text-blue-700 border-blue-200';
    return 'bg-emerald-100 text-emerald-700 border-emerald-200';
  };

  // Memoized sorted events for timeline
  const sortedEvents = useMemo(() => {
    return [...events].sort((a, b) => a.lamport_time - b.lamport_time);
  }, [events]);

  // Filter significant events for timeline
  const timelineEvents = useMemo(() => {
    const significant = [
      'node_up', 'node_down', 'election_started', 'election_won', 'leader_elected',
      'recovery_started', 'recovery_completed', 'recovery_failed', 'writes_gated', 'writes_enabled'
    ];
    return sortedEvents.filter(e => significant.includes(e.event_type));
  }, [sortedEvents]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-cyan-700 flex items-center gap-2">
            <Server className="w-6 h-6" />
            Recovery Dashboard
          </h2>
          <p className="text-sm text-slate-600 mt-1">
            Automatic failover, leader election, and replica recovery
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-slate-300"
            />
            Auto-refresh
          </label>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              fetchClusterStatus();
              fetchEvents();
            }}
            disabled={isLoading}
          >
            <RefreshCw className={`w-4 h-4 mr-1 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
          <XCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
          <p className="text-red-700">{error}</p>
          <button onClick={() => setError(null)} className="ml-auto text-red-500 hover:text-red-700">×</button>
        </div>
      )}

      {/* Cluster Status Banner */}
      {clusterStatus && (
        <div className={`rounded-lg border-2 p-4 ${
          clusterStatus.writes_allowed
            ? 'border-emerald-200 bg-emerald-50'
            : 'border-amber-200 bg-amber-50'
        }`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div>
                <p className="text-sm font-medium text-slate-700">Current Leader</p>
                <p className="text-lg font-bold text-slate-900">
                  {clusterStatus.current_leader || 'None (Electing...)'}
                </p>
              </div>
              <div className="h-8 border-l border-slate-300" />
              <div>
                <p className="text-sm font-medium text-slate-700">This Node</p>
                <p className="text-lg font-bold text-slate-900 flex items-center gap-2">
                  {clusterStatus.my_node}
                  <Badge variant="outline" className={`text-xs ${
                    clusterStatus.my_role === 'leader' ? 'bg-purple-100 text-purple-700' : ''
                  }`}>
                    {clusterStatus.my_role}
                  </Badge>
                </p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              {clusterStatus.election_in_progress && (
                <Badge variant="outline" className="bg-purple-100 text-purple-700 border-purple-200">
                  <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                  Election in Progress
                </Badge>
              )}
              {clusterStatus.recovery_in_progress && (
                <Badge variant="outline" className="bg-blue-100 text-blue-700 border-blue-200">
                  <RotateCcw className="w-3 h-3 mr-1 animate-spin" />
                  Recovery in Progress
                </Badge>
              )}
              <Badge variant="outline" className={
                clusterStatus.writes_allowed
                  ? 'bg-emerald-100 text-emerald-700 border-emerald-200'
                  : 'bg-amber-100 text-amber-700 border-amber-200'
              }>
                {clusterStatus.writes_allowed ? (
                  <><CheckCircle className="w-3 h-3 mr-1" /> Writes Enabled</>
                ) : (
                  <><AlertTriangle className="w-3 h-3 mr-1" /> Writes Gated</>
                )}
              </Badge>
            </div>
          </div>
        </div>
      )}

      {/* Node Control Panel */}
      <Card className="border-cyan-200">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Database className="w-5 h-5 text-cyan-600" />
            Node Control
          </CardTitle>
          <CardDescription>
            Toggle node availability to simulate failures. Recovery happens automatically.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-4">
            {clusterStatus?.nodes && Object.entries(clusterStatus.nodes).map(([name, node]) => (
              <div
                key={name}
                className={`p-4 rounded-lg border-2 transition-all ${
                  node.effective_alive
                    ? 'border-emerald-200 bg-emerald-50'
                    : 'border-red-200 bg-red-50'
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h4 className="font-semibold text-slate-800">{name.toUpperCase()}</h4>
                    <div className="flex items-center gap-2 mt-1">
                      <Badge
                        variant="outline"
                        className={`text-xs ${getNodeBadgeClass(node)}`}
                      >
                        {node.effective_alive ? 'Online' : 'Offline'}
                      </Badge>
                      {node.role === 'leader' && (
                        <Badge variant="outline" className="text-xs bg-purple-100 text-purple-700">
                          Leader
                        </Badge>
                      )}
                      {node.recovery_in_progress && (
                        <Badge variant="outline" className="text-xs bg-blue-100 text-blue-700">
                          <Loader2 className="w-2 h-2 mr-1 animate-spin" />
                          Recovering
                        </Badge>
                      )}
                    </div>
                  </div>
                  {node.effective_alive ? (
                    <CheckCircle className="w-6 h-6 text-emerald-500" />
                  ) : (
                    <XCircle className="w-6 h-6 text-red-500" />
                  )}
                </div>
                
                <div className="text-xs text-slate-600 space-y-1 mb-3">
                  <p>Role: <span className="font-medium">{node.role}</span></p>
                  {node.last_heartbeat && (
                    <p>Last HB: <span className="font-mono">{formatTime(node.last_heartbeat)}</span></p>
                  )}
                  <p>Lamport: <span className="font-mono">{node.last_seen_lamport}</span></p>
                </div>
                
                <Button
                  variant={node.effective_alive ? "destructive" : "default"}
                  size="sm"
                  className="w-full"
                  onClick={() => toggleNode(name, node.effective_alive)}
                  disabled={isLoading || runningScenario}
                >
                  {node.effective_alive ? (
                    <><PowerOff className="w-4 h-4 mr-1" /> Turn Off</>
                  ) : (
                    <><Power className="w-4 h-4 mr-1" /> Turn On</>
                  )}
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Recovery Test Scenarios */}
      <Card className="border-cyan-200">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Play className="w-5 h-5 text-cyan-600" />
            Automated Recovery Tests
          </CardTitle>
          <CardDescription>
            Run pre-defined scenarios to test automatic failover, election, and recovery.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            {testScenarios.map((scenario) => (
              <div
                key={scenario.id}
                className={`p-4 rounded-lg border-2 transition-all ${
                  selectedScenario === scenario.id
                    ? 'border-cyan-400 bg-cyan-50'
                    : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <h4 className="font-semibold text-slate-800">{scenario.name}</h4>
                    <p className="text-sm text-slate-600 mt-1">{scenario.description}</p>
                  </div>
                </div>
                
                <div className="flex flex-wrap gap-1 mt-2 mb-3">
                  {scenario.expectedEvents.slice(0, 4).map((evt, idx) => (
                    <span
                      key={idx}
                      className={`text-xs px-1.5 py-0.5 rounded ${eventStyles[evt]?.bg || 'bg-slate-100'} ${eventStyles[evt]?.color || 'text-slate-600'}`}
                    >
                      {evt.replace(/_/g, ' ')}
                    </span>
                  ))}
                </div>
                
                <Button
                  size="sm"
                  className="w-full"
                  onClick={() => runScenario(scenario.id)}
                  disabled={isLoading || runningScenario}
                >
                  {runningScenario === scenario.id ? (
                    <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Running...</>
                  ) : (
                    <><Play className="w-4 h-4 mr-1" /> Run Test</>
                  )}
                </Button>
              </div>
            ))}
          </div>
          
          {/* Scenario Result */}
          {scenarioResult && (
            <div className="mt-4 p-4 bg-slate-50 rounded-lg border border-slate-200">
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-semibold text-slate-800">Test Result</h4>
                <Badge variant="outline" className={
                  scenarioResult.status === 'completed'
                    ? 'bg-emerald-100 text-emerald-700'
                    : 'bg-red-100 text-red-700'
                }>
                  {scenarioResult.status}
                </Badge>
              </div>
              <p className="text-sm text-slate-600">
                Scenario: {scenarioResult.scenario} | Events generated: {scenarioResult.events?.length || 0}
              </p>
              {scenarioResult.error && (
                <p className="text-sm text-red-600 mt-1">Error: {scenarioResult.error}</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Timeline Visualization */}
      <Card className="border-cyan-200">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <Activity className="w-5 h-5 text-cyan-600" />
              Event Timeline
            </CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowTimeline(!showTimeline)}
            >
              {showTimeline ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </Button>
          </div>
        </CardHeader>
        {showTimeline && (
          <CardContent>
            {timelineEvents.length === 0 ? (
              <p className="text-center text-slate-500 py-4">No events yet. Run a test scenario or toggle a node.</p>
            ) : (
              <div className="relative">
                {/* Timeline line */}
                <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-slate-200" />
                
                {/* Timeline events */}
                <div className="space-y-2 pl-10">
                  {timelineEvents.map((event, idx) => {
                    const style = eventStyles[event.event_type] || { color: 'text-slate-600', bg: 'bg-slate-100' };
                    return (
                      <div
                        key={event.event_id || idx}
                        className="relative flex items-center gap-3"
                      >
                        {/* Timeline dot */}
                        <div className={`absolute -left-6 w-4 h-4 rounded-full ${style.bg} flex items-center justify-center border-2 border-white shadow-sm`}>
                          <div className={`w-2 h-2 rounded-full ${style.color.replace('text-', 'bg-')}`} />
                        </div>
                        
                        {/* Event content */}
                        <div className={`flex-1 p-2 rounded-lg ${style.bg} border border-opacity-50`}>
                          <div className="flex items-center gap-2">
                            <span className={style.color}>{getEventIcon(event.event_type)}</span>
                            <span className="font-medium text-sm text-slate-800">
                              {event.event_type.replace(/_/g, ' ')}
                            </span>
                            <span className="text-xs text-slate-500 ml-auto">
                              T={event.lamport_time}
                            </span>
                          </div>
                          <p className="text-sm text-slate-600 mt-0.5">{event.message}</p>
                          {event.node && (
                            <Badge variant="outline" className="text-xs mt-1">
                              @{event.node}
                            </Badge>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </CardContent>
        )}
      </Card>

      {/* Live Event Logs */}
      <Card className="border-cyan-200">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <Zap className="w-5 h-5 text-cyan-600" />
              Live Event Log
              <Badge variant="outline" className="text-xs ml-2">
                {events.length} events
              </Badge>
            </CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setEvents([])}
            >
              Clear
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="bg-slate-900 rounded-lg p-4 max-h-80 overflow-y-auto font-mono text-sm">
            {events.length === 0 ? (
              <p className="text-slate-500 text-center">Waiting for events...</p>
            ) : (
              sortedEvents.map((event, idx) => {
                const style = eventStyles[event.event_type] || { color: 'text-slate-400' };
                return (
                  <div key={event.event_id || idx} className="mb-1 flex items-start gap-2">
                    <span className="text-slate-500 flex-shrink-0">
                      [{formatTime(event.timestamp)}]
                    </span>
                    <span className="text-cyan-400 flex-shrink-0">
                      [T={String(event.lamport_time).padStart(5, '0')}]
                    </span>
                    <span className={`flex-shrink-0 ${style.color}`}>
                      {event.event_type}
                    </span>
                    <span className="text-slate-300">
                      {event.node && <span className="text-purple-400">@{event.node} </span>}
                      {event.message}
                    </span>
                    {event.details && Object.keys(event.details).length > 0 && (
                      <span className="text-slate-500">
                        {JSON.stringify(event.details)}
                      </span>
                    )}
                  </div>
                );
              })
            )}
            <div ref={logsEndRef} />
          </div>
        </CardContent>
      </Card>

      {/* Info Panel */}
      <Card className="border-slate-200 bg-slate-50">
        <CardContent className="p-4">
          <h4 className="font-semibold text-slate-800 mb-2 flex items-center gap-2">
            <Shield className="w-4 h-4 text-slate-600" />
            Automatic Recovery Features
          </h4>
          <div className="grid grid-cols-2 gap-4 text-sm text-slate-600">
            <div>
              <p className="font-medium text-slate-700">Leader Election</p>
              <p>When the leader goes down, remaining nodes automatically elect a new leader.</p>
            </div>
            <div>
              <p className="font-medium text-slate-700">Replica Catch-up</p>
              <p>When a failed node returns, it automatically pulls missed operations and resyncs.</p>
            </div>
            <div>
              <p className="font-medium text-slate-700">Write Gating</p>
              <p>Writes are automatically blocked during elections and recovery to ensure consistency.</p>
            </div>
            <div>
              <p className="font-medium text-slate-700">Heartbeat Monitoring</p>
              <p>Nodes exchange heartbeats every 2s. After 6s timeout, a node is marked as DOWN.</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default UnifiedRecoveryPanel;
