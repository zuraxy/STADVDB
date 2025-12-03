import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, AlertTriangle, BookOpen, Check, Clock, Database, Edit3, FileText, Play, RefreshCw, Shield, StopCircle, User, Zap } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import {
  abortOrchestratorRun,
  getOrchestratorLogs,
  getOrchestratorStatus,
  runOrchestratorScenario,
  subscribeToOrchestratorStream,
} from '../services/api';

const scenarioOptions = [
  {
    id: 'READ_READ',
    label: 'Readers vs Readers',
    description: 'Two+ readers issue BEGIN/SELECT/pg_sleep/SELECT to visualize snapshot semantics.',
  },
  {
    id: 'READ_WRITE',
    label: 'Writer vs Readers',
    description: 'A writer updates Node X while readers on Node Y observe visibility differences.',
  },
  {
    id: 'WRITE_WRITE',
    label: 'Writer vs Writer',
    description: 'Two writers concurrently increment the same row. Each reads current value and adds 1. Tests for lost updates and serialization conflicts.',
  },
  {
    id: 'NON_REPEATABLE_READ',
    label: 'Non-Repeatable Read Test',
    description: 'Reader performs SELECT, sleeps, then SELECT again. Writer updates the row during sleep. Tests if isolation level prevents non-repeatable reads.',
  },
  {
    id: 'PHANTOM_READ',
    label: 'Phantom Read Test',
    description: 'Reader performs COUNT and range SELECT, sleeps, then repeats. Writer inserts a new row during sleep. Tests if isolation level prevents phantom reads.',
  },
];

const isolationLevels = [
  { id: 'READ_UNCOMMITTED', label: 'Read Uncommitted' },
  { id: 'READ_COMMITTED', label: 'Read Committed' },
  { id: 'REPEATABLE_READ', label: 'Repeatable Read' },
  { id: 'SERIALIZABLE', label: 'Serializable' },
];

const nodeOptions = ['node0', 'node1', 'node2'];

const statusTone = {
  running: 'bg-blue-100 text-blue-800 border-blue-200',
  completed: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  failed: 'bg-rose-100 text-rose-800 border-rose-200',
  aborted: 'bg-amber-100 text-amber-800 border-amber-200',
};

const clientTone = {
  committed: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  running: 'bg-blue-50 text-blue-700 border-blue-200',
  error: 'bg-rose-50 text-rose-700 border-rose-200',
  cancelled: 'bg-slate-50 text-slate-600 border-slate-200',
  serialization_aborted: 'bg-amber-50 text-amber-700 border-amber-200',
};

export function TransactionOrchestrator() {
  const [scenario, setScenario] = useState('READ_READ');
  const [isolation, setIsolation] = useState('READ_COMMITTED');
  const [parallelClients, setParallelClients] = useState(2);
  const [orderId, setOrderId] = useState('');
  const [nodeX, setNodeX] = useState('node0');
  const [nodeY, setNodeY] = useState('node1');
  const [newValue1, setNewValue1] = useState('');
  const [newValue2, setNewValue2] = useState('');
  const [runId, setRunId] = useState(null);
  const [statusSnapshot, setStatusSnapshot] = useState(null);
  const [logs, setLogs] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [streamError, setStreamError] = useState(null);
  const streamRef = useRef(null);

  const activeScenario = useMemo(() => scenarioOptions.find((opt) => opt.id === scenario), [scenario]);
  const requiresWriter = scenario !== 'READ_READ';
  const requiresSecondWriter = scenario === 'WRITE_WRITE';

  // Dynamic labels based on scenario
  const nodeXLabel = useMemo(() => {
    if (scenario === 'READ_READ') return 'Reader A Node';
    if (scenario === 'READ_WRITE') return 'Writer Node (Master)';
    return 'Writer A Node';
  }, [scenario]);

  const nodeYLabel = useMemo(() => {
    if (scenario === 'READ_READ') return 'Reader B Node';
    if (scenario === 'READ_WRITE') return 'Reader Node (Slave)';
    return 'Writer B Node';
  }, [scenario]);

  const fetchRunData = useCallback(
    async (targetRunId) => {
      const effectiveRunId = targetRunId || runId;
      if (!effectiveRunId) return;
      try {
        const hasLiveStream = Boolean(streamRef.current);
        const [statusPayload, logPayload] = await Promise.all([
          getOrchestratorStatus(effectiveRunId),
          hasLiveStream ? Promise.resolve({ logs: [] }) : getOrchestratorLogs(effectiveRunId),
        ]);
        setStatusSnapshot(statusPayload);
        if (!hasLiveStream) {
          setLogs(logPayload.logs || []);
        }
        if (statusPayload.status !== 'running') {
          setAutoRefresh(false);
        }
      } catch (err) {
        setError(err.message || 'Failed to fetch run status');
        setAutoRefresh(false);
      }
    },
    [runId],
  );

  const attachStream = useCallback(
    (targetRunId) => {
      if (streamRef.current) {
        streamRef.current.close();
        streamRef.current = null;
      }
      const source = subscribeToOrchestratorStream(targetRunId, {
        onMessage: (entry) => {
          setLogs((prev) => [...prev.slice(-199), entry]);
        },
        onError: () => {
          setStreamError('Live stream interrupted. Falling back to polling.');
          if (streamRef.current) {
            streamRef.current.close();
            streamRef.current = null;
          }
        },
      });
      if (source) {
        streamRef.current = source;
        setStreamError(null);
      } else {
        setStreamError('Live stream unavailable in this browser.');
      }
    },
    [],
  );

  useEffect(() => {
    if (!runId) return;
    fetchRunData(runId);
  }, [runId, fetchRunData]);

  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.close();
      }
    };
  }, []);

  useEffect(() => {
    if (!runId || !autoRefresh) {
      return undefined;
    }
    const interval = setInterval(() => fetchRunData(runId), 2500);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchRunData, runId]);

  useEffect(() => {
    if (statusSnapshot?.status && statusSnapshot.status !== 'running' && streamRef.current) {
      streamRef.current.close();
      streamRef.current = null;
    }
  }, [statusSnapshot]);

  const handleRun = async () => {
    setError(null);
    setIsSubmitting(true);
    try {
      const normalizedClients = Math.min(16, Math.max(2, Number(parallelClients) || 2));
      const payload = {
        scenario,
        isolation_level: isolation,
        parallel_clients: normalizedClients,
        order_id: orderId.trim() || undefined,
        node_x: nodeX,
        node_y: nodeY,
      };
      if (scenario !== 'READ_READ') {
        const parsedValue1 = newValue1 === '' ? undefined : Number(newValue1);
        if (Number.isNaN(parsedValue1)) {
          throw new Error('New Value 1 must be numeric when provided');
        }
        payload.new_value_1 = parsedValue1;
      }
      if (scenario === 'WRITE_WRITE') {
        const parsedValue2 = newValue2 === '' ? undefined : Number(newValue2);
        if (Number.isNaN(parsedValue2)) {
          throw new Error('New Value 2 must be numeric when provided');
        }
        payload.new_value_2 = parsedValue2;
      }
      const response = await runOrchestratorScenario(payload);
      setRunId(response.run_id);
      setStatusSnapshot(null);
      setLogs([]);
      setAutoRefresh(true);
      attachStream(response.run_id);
      await fetchRunData(response.run_id);
    } catch (err) {
      setError(err.message || 'Failed to start orchestrator run');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAbort = async () => {
    if (!runId) return;
    try {
      await abortOrchestratorRun(runId);
      if (streamRef.current) {
        streamRef.current.close();
        streamRef.current = null;
      }
      setAutoRefresh(true);
      await fetchRunData(runId);
    } catch (err) {
      setError(err.message || 'Unable to abort run');
    }
  };

  const latestLogs = useMemo(() => logs.slice(-10).reverse(), [logs]);
  const clientEntries = useMemo(() => {
    if (!statusSnapshot?.clients) return [];
    return Object.entries(statusSnapshot.clients).sort(([a], [b]) => a.localeCompare(b));
  }, [statusSnapshot]);
  const isolationDisplayLabel = useMemo(() => {
    if (statusSnapshot?.result_summary?.isolation_level) {
      return statusSnapshot.result_summary.isolation_level;
    }
    const selected = isolationLevels.find((lvl) => lvl.id === isolation);
    return selected ? selected.label : isolation;
  }, [isolation, statusSnapshot]);
  const finalStateEntries = useMemo(() => {
    const snapshots = statusSnapshot?.result_summary?.final_states;
    if (!snapshots) return [];
    return Object.entries(snapshots);
  }, [statusSnapshot]);
  const serializationConflicts = statusSnapshot?.result_summary?.serialization_conflicts || [];

  const isolationNote = useMemo(() => {
    if (isolation === 'READ_UNCOMMITTED') {
      return 'PostgreSQL promotes READ UNCOMMITTED to READ COMMITTED to stay standards compliant.';
    }
    if (scenario === 'WRITE_WRITE') {
      if (isolation === 'READ_COMMITTED') {
        return 'With FOR UPDATE locking, second writer waits for first. Both increments should succeed.';
      }
      if (isolation === 'REPEATABLE_READ' || isolation === 'SERIALIZABLE') {
        return 'Expect one writer to abort with a serialization conflict. Only one increment succeeds.';
      }
    }
    return null;
  }, [isolation, scenario]);

  const getLogIcon = (event) => {
    const iconMap = {
      'scenario_compiled': <Zap className="w-3.5 h-3.5 text-purple-500" />,
      'transaction_started': <Play className="w-3.5 h-3.5 text-blue-500" />,
      'read_snapshot': <BookOpen className="w-3.5 h-3.5 text-cyan-500" />,
      'read_complete': <Check className="w-3.5 h-3.5 text-emerald-500" />,
      'write_locked': <Database className="w-3.5 h-3.5 text-amber-500" />,
      'write_complete': <Edit3 className="w-3.5 h-3.5 text-emerald-500" />,
      'write_delay_before_commit': <Clock className="w-3.5 h-3.5 text-orange-500" />,
      'write_write_concurrent_start': <Zap className="w-3.5 h-3.5 text-purple-500" />,
      'pg_sleep': <Clock className="w-3.5 h-3.5 text-slate-400" />,
      'client_error': <AlertTriangle className="w-3.5 h-3.5 text-rose-500" />,
      'client_serialization_abort': <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />,
      'run_failed': <AlertTriangle className="w-3.5 h-3.5 text-rose-500" />,
      'run_aborted': <StopCircle className="w-3.5 h-3.5 text-amber-500" />,
    };
    return iconMap[event] || <Activity className="w-3.5 h-3.5 text-slate-400" />;
  };

  const formatLogEvent = (event) => {
    const eventLabels = {
      'scenario_compiled': 'Scenario Ready',
      'transaction_started': 'Transaction Started',
      'read_snapshot': 'Read Snapshot',
      'read_complete': 'Read Complete',
      'write_locked': 'Row Locked',
      'write_complete': 'Write Complete',
      'write_delay_before_commit': 'Holding Transaction',
      'write_write_concurrent_start': 'Concurrent Writers Starting',
      'pg_sleep': 'Waiting',
      'client_error': 'Error',
      'client_serialization_abort': 'Serialization Conflict',
      'run_failed': 'Run Failed',
      'run_aborted': 'Run Aborted',
    };
    return eventLabels[event] || event.replace(/_/g, ' ');
  };

  const formatLogDetails = (details, event) => {
    if (!details || Object.keys(details).length === 0) {
      return null;
    }

    // Format based on event type
    if (event === 'transaction_started') {
      const remote = details.remote ? ' (remote)' : '';
      return (
        <span className="flex items-center gap-1">
          <User className="w-3 h-3" />
          <span className="font-medium">{details.actor_id}</span>
          <span className="text-slate-400">on</span>
          <span className="font-medium">{details.node?.toUpperCase()}</span>
          <span className="text-slate-400">as</span>
          <span className={details.role === 'write' ? 'text-amber-600 font-medium' : 'text-cyan-600 font-medium'}>
            {details.role}
          </span>
          {remote && <span className="text-xs text-purple-500">{remote}</span>}
        </span>
      );
    }

    if (event === 'read_snapshot' || event === 'read_complete') {
      const qty = details.quantity ?? details.initial_quantity;
      const finalQty = details.final_quantity;
      return (
        <span className="flex items-center gap-1">
          <span className="font-medium">{details.actor_id}</span>
          <span className="text-slate-400">→</span>
          <span className="font-mono bg-slate-100 px-1.5 py-0.5 rounded text-sm">qty: {qty}</span>
          {finalQty !== undefined && finalQty !== qty && (
            <><span className="text-slate-400">→</span>
            <span className="font-mono bg-emerald-100 px-1.5 py-0.5 rounded text-sm">final: {finalQty}</span></>
          )}
        </span>
      );
    }

    if (event === 'write_locked') {
      return (
        <span className="flex items-center gap-1">
          <span className="font-medium">{details.actor_id}</span>
          <span className="text-slate-400">locked row with</span>
          <span className="font-mono bg-amber-100 px-1.5 py-0.5 rounded text-sm">qty: {details.quantity}</span>
        </span>
      );
    }

    if (event === 'write_complete') {
      return (
        <span className="flex items-center gap-1">
          <span className="font-medium">{details.actor_id}</span>
          <span className="text-slate-400">{details.previous_quantity ?? '?'} →</span>
          <span className="font-mono bg-emerald-100 px-1.5 py-0.5 rounded text-sm font-medium">{details.committed_quantity}</span>
        </span>
      );
    }

    if (event === 'pg_sleep') {
      return (
        <span className="flex items-center gap-1">
          <span className="font-medium">{details.actor_id}</span>
          <span className="text-slate-400">sleeping for</span>
          <span className="font-mono">{details.seconds}s</span>
        </span>
      );
    }

    if (event === 'scenario_compiled') {
      return (
        <span className="flex items-center gap-1">
          <span className="text-slate-400">Order:</span>
          <span className="font-mono text-xs">{details.order_id?.slice(0, 8)}...</span>
          <span className="text-slate-400">Actors:</span>
          <span className="font-medium">{details.actors?.join(', ')}</span>
        </span>
      );
    }

    if (details.error) {
      return <span className="text-rose-600">{details.error}</span>;
    }

    // Fallback to key-value display
    return (
      <span>
        {Object.entries(details).map(([key, value], idx) => (
          <span key={key}>
            {idx > 0 && <span className="text-slate-300 mx-1">·</span>}
            <span className="text-slate-500">{key}:</span> {typeof value === 'object' ? JSON.stringify(value) : String(value)}
          </span>
        ))}
      </span>
    );
  };

  const summarizeStep = (step) => {
    if (!step) return '';
    if (step.error) {
      return `${step.action}: ${step.error}`;
    }
    if (Array.isArray(step.result) && step.result.length > 0) {
      const first = step.result[0];
      if (first?.quantity !== undefined) {
        return `${step.action}: qty ${first.quantity}`;
      }
    }
    if (typeof step.result === 'string') {
      return `${step.action}: ${step.result}`;
    }
    return step.action;
  };

  return (
    <Card className="border-cyan-200 shadow-sm">
      <CardHeader>
        <div className="flex items-center gap-3 text-cyan-700">
          <Activity className="w-5 h-5" />
          <CardTitle>Transaction Orchestrator</CardTitle>
        </div>
        <CardDescription>
          Configure isolation level + scenario, launch concurrent transactions, and observe per-client outcomes in real time.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Partition Info Banner */}
        <div className="rounded-md border border-blue-200 bg-blue-50 px-4 py-3 text-sm">
          <p className="font-semibold text-blue-900 mb-2">Partition Configuration</p>
          <div className="grid grid-cols-2 gap-3 text-blue-800">
            <div className="flex items-center gap-2">
              <span className="font-medium">Node 1 (Fragment 1):</span>
              <span>Quantity 1-5</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-medium">Node 2 (Fragment 2):</span>
              <span>Quantity 6-10</span>
            </div>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="space-y-2">
            <Label htmlFor="scenario" className="text-slate-700 font-medium">Scenario</Label>
            <Select value={scenario} onValueChange={setScenario}>
              <SelectTrigger id="scenario" className="bg-white border-slate-300">
                <SelectValue placeholder="Pick a scenario" />
              </SelectTrigger>
              <SelectContent className="bg-white">
                {scenarioOptions.map((option) => (
                  <SelectItem key={option.id} value={option.id}>
                    <div className="flex flex-col text-left">
                      <span className="font-medium text-sm">{option.label}</span>
                      <span className="text-xs text-muted-foreground">{option.description}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="isolation" className="text-slate-700 font-medium">Isolation Level</Label>
            <Select value={isolation} onValueChange={setIsolation}>
              <SelectTrigger id="isolation" className="bg-white border-slate-300">
                <SelectValue placeholder="Pick isolation" />
              </SelectTrigger>
              <SelectContent className="bg-white">
                {isolationLevels.map((level) => (
                  <SelectItem key={level.id} value={level.id}>
                    {level.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {isolationNote && (
              <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-2 py-1 flex items-center gap-2">
                <Shield className="w-3 h-3" />
                {isolationNote}
              </p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="parallelClients" className="text-slate-700 font-medium">Parallel Clients</Label>
            <Input
              id="parallelClients"
              type="number"
              min={2}
              max={16}
              value={parallelClients}
              onChange={(e) => setParallelClients(Math.max(2, Math.min(16, Number(e.target.value) || 2)))}
              className="bg-white border-slate-300"
            />
            <p className="text-xs text-muted-foreground">2-16 concurrent scripts (writer included).</p>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="space-y-2">
            <Label htmlFor="orderId" className="text-slate-700 font-medium">Order ID (optional)</Label>
            <Input
              id="orderId"
              value={orderId}
              onChange={(e) => setOrderId(e.target.value)}
              placeholder="Leave blank to auto-provision"
              className="bg-white border-slate-300"
            />
            <p className="text-xs text-muted-foreground">Provide a UUID to target a specific order.</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="nodeX" className="text-slate-700 font-medium">{nodeXLabel}</Label>
            <Select value={nodeX} onValueChange={setNodeX}>
              <SelectTrigger id="nodeX" className="bg-white border-slate-300">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-white">
                {nodeOptions.map((node) => (
                  <SelectItem key={node} value={node}>
                    {node.toUpperCase()}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="nodeY" className="text-slate-700 font-medium">{nodeYLabel}</Label>
            <Select value={nodeY} onValueChange={setNodeY}>
              <SelectTrigger id="nodeY" className="bg-white border-slate-300">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-white">
                {nodeOptions.map((node) => (
                  <SelectItem key={node} value={node}>
                    {node.toUpperCase()}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {requiresWriter && scenario === 'READ_WRITE' && (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="newValue1" className="text-slate-700 font-medium">
                Writer target quantity
              </Label>
              <Input
                id="newValue1"
                type="number"
                value={newValue1}
                onChange={(e) => setNewValue1(e.target.value)}
                placeholder="e.g., 42"
                className="bg-white border-slate-300"
              />
              <p className="text-xs text-muted-foreground">
                The value the writer will set the quantity to.
              </p>
            </div>
          </div>
        )}

        {requiresSecondWriter && (
          <div className="rounded-md border border-purple-100 bg-purple-50 px-4 py-3 text-sm text-purple-800">
            <div className="flex items-start gap-3">
              <Zap className="w-4 h-4 mt-0.5" />
              <div className="space-y-2">
                <p className="font-medium">Auto-Increment Mode</p>
                <p>Both writers will read the current quantity and increment by 1. This tests for <strong>lost updates</strong>:</p>
                <ul className="list-disc list-inside space-y-1 text-xs">
                  <li><strong>READ COMMITTED:</strong> With FOR UPDATE lock, second writer waits. Both increments succeed (qty +2).</li>
                  <li><strong>REPEATABLE READ:</strong> Second writer gets serialization error. One increment succeeds (qty +1).</li>
                  <li><strong>SERIALIZABLE:</strong> Strictest isolation. One writer aborts with serialization conflict.</li>
                </ul>
              </div>
            </div>
          </div>
        )}

        {activeScenario?.description && (
          <div className="rounded-md border border-cyan-100 bg-cyan-50 px-4 py-3 text-sm text-cyan-800 flex items-start gap-3">
            <FileText className="w-4 h-4 mt-0.5" />
            <div>
              <p className="font-medium">What to expect</p>
              <p>{activeScenario.description}</p>
            </div>
          </div>
        )}

        {error && (
          <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {streamError && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800 flex items-start gap-2">
            <Shield className="w-4 h-4 mt-0.5" />
            <span>{streamError}</span>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={handleRun} disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Launching...
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                Run Scenario
              </>
            )}
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={!runId}
            onClick={() => fetchRunData(runId)}
          >
            <RefreshCw className="w-4 h-4" />
            Refresh Status
          </Button>
          {statusSnapshot?.status === 'running' && (
            <Button type="button" variant="destructive" onClick={handleAbort}>
              <StopCircle className="w-4 h-4" />
              Abort Run
            </Button>
          )}
          {statusSnapshot && (
            <Badge
              variant="outline"
              className={`${statusTone[statusSnapshot.status] || 'bg-slate-100 text-slate-700 border-slate-200'} border`}
            >
              {statusSnapshot.status?.toUpperCase() || 'UNKNOWN'}
            </Badge>
          )}
        </div>

        {statusSnapshot && (
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="space-y-4 border rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs uppercase text-slate-500">Run ID</p>
                  <p className="font-mono text-sm break-all">{statusSnapshot.run_id}</p>
                </div>
                <div className="text-right text-sm text-slate-500">
                  <p>Scenario: {statusSnapshot.scenario}</p>
                  <p>Started: {new Date(statusSnapshot.created_at).toLocaleTimeString()}</p>
                  {statusSnapshot.finished_at && (
                    <p>Finished: {new Date(statusSnapshot.finished_at).toLocaleTimeString()}</p>
                  )}
                </div>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                  <Shield className="w-4 h-4" /> Isolation: {isolationDisplayLabel}
                </p>
                {statusSnapshot.result_summary ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="p-3 border rounded-md bg-slate-50">
                      <p className="text-xs uppercase text-slate-500">Order</p>
                      <p className="font-mono text-sm break-all">{statusSnapshot.result_summary.order_id}</p>
                    </div>
                    <div className="p-3 border rounded-md bg-slate-50">
                      <p className="text-xs uppercase text-slate-500">Quantity Δ</p>
                      <p className="text-lg font-semibold">{statusSnapshot.result_summary.delta ?? '—'}</p>
                    </div>
                    <div className="p-3 border rounded-md bg-slate-50">
                      <p className="text-xs uppercase text-slate-500">Initial Qty</p>
                      <p className="text-sm font-semibold">{statusSnapshot.result_summary.initial_quantity ?? '—'}</p>
                    </div>
                    <div className="p-3 border rounded-md bg-slate-50">
                      <p className="text-xs uppercase text-slate-500">Final Qty</p>
                      <p className="text-sm font-semibold">{statusSnapshot.result_summary.final_quantity ?? '—'}</p>
                    </div>
                    {statusSnapshot.result_summary.verdict && (
                      <div className="md:col-span-2 p-3 border rounded-md bg-white">
                        <p className="text-xs uppercase text-slate-500">Verdict</p>
                        <p className="text-sm text-slate-700">{statusSnapshot.result_summary.verdict}</p>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-slate-500">Waiting for summary...</p>
                )}
                {statusSnapshot.result_summary?.read_uncommitted_note && (
                  <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
                    {statusSnapshot.result_summary.read_uncommitted_note}
                  </p>
                )}
                {serializationConflicts.length > 0 && (
                  <p className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-md px-3 py-2">
                    Serialization retries triggered for: {serializationConflicts.join(', ')}
                  </p>
                )}
                {finalStateEntries.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs uppercase text-slate-500">Node snapshots</p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {finalStateEntries.map(([node, snapshot]) => (
                        <div key={node} className="border rounded-md p-3 bg-white">
                          <p className="text-xs uppercase text-slate-500">{node.toUpperCase()}</p>
                          {snapshot?.available === false ? (
                            <p className="text-sm text-slate-500">DSN not configured</p>
                          ) : snapshot?.present === false ? (
                            <p className="text-sm text-slate-500">Order not present</p>
                          ) : (
                            <div>
                              <p className="text-2xl font-semibold">{snapshot?.quantity ?? '—'}</p>
                              <p className="text-xs text-slate-500">Updated {snapshot?.updated_at ? new Date(snapshot.updated_at).toLocaleTimeString() : 'n/a'}</p>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                    {statusSnapshot.result_summary?.replication_note && (
                      <p className="text-xs text-slate-500">{statusSnapshot.result_summary.replication_note}</p>
                    )}
                  </div>
                )}
              </div>

              {/* Timing Metrics Panel */}
              {statusSnapshot.result_summary?.timing_metrics && (
                <div className="space-y-2">
                  <p className="text-sm font-semibold text-slate-700">Performance Metrics</p>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div className="border rounded-md p-3 bg-gradient-to-br from-blue-50 to-white">
                      <p className="text-xs uppercase text-slate-500">Avg Total Duration</p>
                      <p className="text-2xl font-semibold text-blue-600">
                        {statusSnapshot.result_summary.timing_metrics.avg_total_duration_ms.toFixed(1)}
                        <span className="text-sm text-slate-500 ml-1">ms</span>
                      </p>
                    </div>
                    <div className="border rounded-md p-3 bg-gradient-to-br from-green-50 to-white">
                      <p className="text-xs uppercase text-slate-500">Avg Execution Time</p>
                      <p className="text-2xl font-semibold text-green-600">
                        {statusSnapshot.result_summary.timing_metrics.avg_execution_time_ms.toFixed(1)}
                        <span className="text-sm text-slate-500 ml-1">ms</span>
                      </p>
                    </div>
                    <div className="border rounded-md p-3 bg-gradient-to-br from-amber-50 to-white">
                      <p className="text-xs uppercase text-slate-500">Avg Sleep Time</p>
                      <p className="text-2xl font-semibold text-amber-600">
                        {statusSnapshot.result_summary.timing_metrics.avg_sleep_time_ms.toFixed(1)}
                        <span className="text-sm text-slate-500 ml-1">ms</span>
                      </p>
                    </div>
                  </div>
                  
                  {/* Per-Actor Breakdown */}
                  {statusSnapshot.result_summary.timing_metrics.per_actor && (
                    <div className="mt-3 space-y-2">
                      <p className="text-xs uppercase text-slate-500">Per-Actor Breakdown</p>
                      <div className="space-y-2">
                        {Object.entries(statusSnapshot.result_summary.timing_metrics.per_actor).map(([actorId, timing]) => (
                          <div key={actorId} className="border rounded-md p-3 bg-white">
                            <p className="text-sm font-semibold mb-2">{actorId}</p>
                            <div className="grid grid-cols-3 gap-3 text-xs">
                              <div>
                                <p className="text-slate-500">Total</p>
                                <p className="font-mono font-semibold">{timing.total_duration_ms}ms</p>
                              </div>
                              <div>
                                <p className="text-slate-500">Execution</p>
                                <p className="font-mono font-semibold text-green-600">{timing.execution_time_ms}ms</p>
                              </div>
                              <div>
                                <p className="text-slate-500">Sleep</p>
                                <p className="font-mono font-semibold text-amber-600">{timing.sleep_time_ms}ms</p>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div className="space-y-2">
                <p className="text-sm font-semibold text-slate-700">Client Status</p>
                {clientEntries.length === 0 && <p className="text-sm text-slate-500">Clients are spinning up...</p>}
                <div className="space-y-2">
                  {clientEntries.map(([clientId, info]) => (
                    <div
                      key={clientId}
                      className={`border rounded-md px-3 py-2 ${
                        clientTone[info.status] || 'bg-slate-50 text-slate-700 border-slate-200'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold">{clientId}</p>
                          <p className="text-xs capitalize">
                            {info.role} · {info.node}
                            {info.auto_increment && <span className="ml-1 text-purple-600">(+1 increment)</span>}
                            {info.new_quantity !== undefined && <span className="ml-1 text-blue-600">(set to {info.new_quantity})</span>}
                          </p>
                          {info.steps?.length > 0 && (
                            <div className="mt-2 space-y-1 text-xs text-slate-600 max-h-24 overflow-y-auto">
                              {info.steps.slice(-4).map((step, idx) => (
                                <p key={`${clientId}-step-${idx}`} className="font-mono">
                                  {summarizeStep(step)}
                                </p>
                              ))}
                            </div>
                          )}
                        </div>
                        <Badge variant="outline" className="bg-white/70 text-slate-700">
                          {info.status}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="space-y-3 border rounded-lg p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-slate-700 flex items-center gap-2">
                  <FileText className="w-4 h-4" /> Recent Logs
                </p>
                {statusSnapshot?.status === 'running' && (
                  <span className="text-xs text-blue-600">Auto-refreshing…</span>
                )}
              </div>
              <div className="max-h-80 overflow-y-auto space-y-2">
                {latestLogs.length === 0 && <p className="text-sm text-slate-500">No log entries yet.</p>}
                {latestLogs.map((entry, idx) => (
                  <div key={`${entry.timestamp}-${entry.event}-${idx}`} className="border rounded-md p-3 bg-white hover:bg-slate-50 transition-colors">
                    <div className="flex items-center gap-2 mb-1">
                      {getLogIcon(entry.event)}
                      <span className="text-xs font-medium text-slate-600">
                        {formatLogEvent(entry.event)}
                      </span>
                      <span className="text-xs text-slate-400 ml-auto">
                        {new Date(entry.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                    <div className="text-sm text-slate-700 pl-5">
                      {formatLogDetails(entry.details, entry.event)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
