import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, FileText, Play, RefreshCw, Shield, StopCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import {
  abortOrchestratorRun,
  getOrchestratorLogs,
  getOrchestratorStatus,
  runOrchestratorScenario,
} from '../services/api';

const scenarioOptions = [
  {
    id: 'Case1_readers_only',
    label: 'Case 1 · Readers Only',
    description: 'Baseline scenario showing snapshot consistency with concurrent readers.',
  },
  {
    id: 'Case2_writer_readers',
    label: 'Case 2 · Writer vs Readers',
    description: 'One writer competes with readers to highlight non-repeatable reads.',
  },
  {
    id: 'Case3_concurrent_writers',
    label: 'Case 3 · Concurrent Writers',
    description: 'Multiple writers contend for the same row to surface serialization anomalies.',
  },
  {
    id: 'custom',
    label: 'Custom JSON Script',
    description: 'Bring your own transactions and nodes (advanced).',
  },
];

const isolationLevels = [
  { id: 'READ_UNCOMMITTED', label: 'Read Uncommitted' },
  { id: 'READ_COMMITTED', label: 'Read Committed' },
  { id: 'REPEATABLE_READ', label: 'Repeatable Read' },
  { id: 'SERIALIZABLE', label: 'Serializable' },
];

const defaultCustomScript = `[
  {
    "node": "node0",
    "statements": [
      { "sql": "SELECT pg_sleep(0.5)", "description": "custom delay" }
    ]
  }
]`;

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
  const [scenario, setScenario] = useState('Case1_readers_only');
  const [isolation, setIsolation] = useState('READ_COMMITTED');
  const [parallelClients, setParallelClients] = useState(2);
  const [customJson, setCustomJson] = useState(defaultCustomScript);
  const [runId, setRunId] = useState(null);
  const [statusSnapshot, setStatusSnapshot] = useState(null);
  const [logs, setLogs] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const activeScenario = useMemo(() => scenarioOptions.find((opt) => opt.id === scenario), [scenario]);

  const fetchRunData = useCallback(
    async (targetRunId) => {
      const effectiveRunId = targetRunId || runId;
      if (!effectiveRunId) return;
      try {
        const [statusPayload, logPayload] = await Promise.all([
          getOrchestratorStatus(effectiveRunId),
          getOrchestratorLogs(effectiveRunId),
        ]);
        setStatusSnapshot(statusPayload);
        setLogs(logPayload.logs || []);
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

  useEffect(() => {
    if (!runId) return;
    fetchRunData(runId);
  }, [runId, fetchRunData]);

  useEffect(() => {
    if (!runId || !autoRefresh) {
      return undefined;
    }
    const interval = setInterval(() => fetchRunData(runId), 2500);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchRunData, runId]);

  const handleRun = async () => {
    setError(null);
    setIsSubmitting(true);
    try {
      const payload = {
        scenario,
        isolation_level: isolation,
        parallel_clients: Math.min(16, Math.max(1, Number(parallelClients) || 1)),
      };
      if (scenario === 'custom') {
        const parsed = JSON.parse(customJson);
        if (!Array.isArray(parsed) || parsed.length === 0) {
          throw new Error('Custom transactions must be a non-empty array');
        }
        payload.custom_transactions = parsed;
      }
      const response = await runOrchestratorScenario(payload);
      setRunId(response.run_id);
      setStatusSnapshot(null);
      setLogs([]);
      setAutoRefresh(true);
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

  const isolationNote =
    isolation === 'READ_UNCOMMITTED'
      ? 'PostgreSQL promotes READ UNCOMMITTED to READ COMMITTED to stay standards compliant.'
      : null;

  const formatLogDetails = (details) => {
    if (!details || Object.keys(details).length === 0) {
      return '—';
    }
    if (details.description) {
      return details.description;
    }
    return Object.entries(details)
      .map(([key, value]) => {
        const text = typeof value === 'object' ? JSON.stringify(value) : value;
        return `${key}: ${text}`;
      })
      .join(' · ');
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
        <div className="grid gap-4 md:grid-cols-3">
          <div className="space-y-2">
            <Label htmlFor="scenario">Scenario</Label>
            <Select value={scenario} onValueChange={setScenario}>
              <SelectTrigger id="scenario">
                <SelectValue placeholder="Pick a scenario" />
              </SelectTrigger>
              <SelectContent>
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
            <Label htmlFor="isolation">Isolation Level</Label>
            <Select value={isolation} onValueChange={setIsolation}>
              <SelectTrigger id="isolation">
                <SelectValue placeholder="Pick isolation" />
              </SelectTrigger>
              <SelectContent>
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
            <Label htmlFor="parallelClients">Parallel Clients</Label>
            <Input
              id="parallelClients"
              type="number"
              min={1}
              max={16}
              value={parallelClients}
              onChange={(e) => setParallelClients(Math.max(1, Math.min(16, Number(e.target.value) || 1)))}
            />
            <p className="text-xs text-muted-foreground">1-16 parallel client scripts per scenario.</p>
          </div>
        </div>

        {activeScenario?.description && (
          <div className="rounded-md border border-cyan-100 bg-cyan-50 px-4 py-3 text-sm text-cyan-800 flex items-start gap-3">
            <FileText className="w-4 h-4 mt-0.5" />
            <div>
              <p className="font-medium">What to expect</p>
              <p>{activeScenario.description}</p>
            </div>
          </div>
        )}

        {scenario === 'custom' && (
          <div className="space-y-2">
            <Label htmlFor="customJson">Custom Transactions (JSON array)</Label>
            <Textarea
              id="customJson"
              rows={8}
              value={customJson}
              onChange={(e) => setCustomJson(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Provide a list of clients: each entry needs a <code>node</code> and <code>statements</code> with SQL, params, optional delays.
            </p>
          </div>
        )}

        {error && (
          <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-0.5" />
            <span>{error}</span>
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

              <div className="space-y-2">
                <p className="text-sm font-semibold text-slate-700">Client Status</p>
                {clientEntries.length === 0 && <p className="text-sm text-slate-500">Clients are spinning up...</p>}
                <div className="space-y-2">
                  {clientEntries.map(([clientId, info]) => (
                    <div
                      key={clientId}
                      className={`flex items-center justify-between border rounded-md px-3 py-2 ${
                        clientTone[info.status] || 'bg-slate-50 text-slate-700 border-slate-200'
                      }`}
                    >
                      <div>
                        <p className="text-sm font-semibold">{clientId}</p>
                        <p className="text-xs capitalize">{info.role} · {info.node}</p>
                      </div>
                      <Badge variant="outline" className="bg-white/70 text-slate-700">
                        {info.status}
                      </Badge>
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
              <div className="max-h-64 overflow-y-auto space-y-2">
                {latestLogs.length === 0 && <p className="text-sm text-slate-500">No log entries yet.</p>}
                {latestLogs.map((entry, idx) => (
                  <div key={`${entry.timestamp}-${entry.event}-${idx}`} className="border rounded-md p-3 bg-white">
                    <p className="text-xs text-slate-500">
                      {new Date(entry.timestamp).toLocaleTimeString()} · {entry.event}
                    </p>
                    <p className="text-sm text-slate-700">
                      {formatLogDetails(entry.details)}
                    </p>
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
