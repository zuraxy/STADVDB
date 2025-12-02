import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, FileText, Play, RefreshCw, Shield, StopCircle } from 'lucide-react';
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
} from '../services/api';

const scenarioOptions = [
  {
    id: 'READ_READ',
    label: 'Scenario · Read vs Read',
    description: 'Two concurrent readers observe the same row and hold locks for optional delays.',
  },
  {
    id: 'READ_WRITE',
    label: 'Scenario · Read vs Write',
    description: 'A reader races a writer against the same order to highlight non-repeatable reads.',
  },
  {
    id: 'WRITE_WRITE',
    label: 'Scenario · Write vs Write',
    description: 'Two writers lock and update the same row to surface serialization behavior.',
  },
];

const scenarioRoles = {
  READ_READ: ['read', 'read'],
  READ_WRITE: ['read', 'write'],
  WRITE_WRITE: ['write', 'write'],
};

const isolationLevels = [
  { id: 'READ_UNCOMMITTED', label: 'Read Uncommitted' },
  { id: 'READ_COMMITTED', label: 'Read Committed' },
  { id: 'REPEATABLE_READ', label: 'Repeatable Read' },
  { id: 'SERIALIZABLE', label: 'Serializable' },
];

const nodeOptions = [
  { id: 'node0', label: 'Node 0 · Primary' },
  { id: 'node1', label: 'Node 1 · Fragment 1-5' },
  { id: 'node2', label: 'Node 2 · Fragment 6-10' },
];

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
  const [orderIdInput, setOrderIdInput] = useState('');
  const [actors, setActors] = useState([
    { name: 'tx_a', node: 'node0', isolationLevel: 'READ_COMMITTED', delaySeconds: 0.1, newQuantity: '' },
    { name: 'tx_b', node: 'node0', isolationLevel: 'READ_COMMITTED', delaySeconds: 0.1, newQuantity: '' },
  ]);
  const [runId, setRunId] = useState(null);
  const [statusSnapshot, setStatusSnapshot] = useState(null);
  const [logs, setLogs] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const activeScenario = useMemo(() => scenarioOptions.find((opt) => opt.id === scenario), [scenario]);
  const activeRoles = scenarioRoles[scenario] || scenarioRoles.READ_READ;

  const updateActor = (index, field, value) => {
    setActors((prev) => {
      const clone = [...prev];
      clone[index] = { ...clone[index], [field]: value };
      return clone;
    });
  };

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
      const actorPayload = activeRoles.map((role, idx) => {
        const actor = actors[idx] || {};
        const baseName = role === 'read' ? `reader_${idx + 1}` : `writer_${idx + 1}`;
        const name = (actor.name || baseName).trim() || baseName;
        const delaySeconds = Number(actor.delaySeconds) || 0;
        const payload = {
          name,
          node: actor.node || 'node0',
          isolation_level: actor.isolationLevel || 'READ_COMMITTED',
          delay_seconds: delaySeconds,
        };
        if (role === 'write') {
          if (actor.newQuantity === '' || actor.newQuantity === null || Number.isNaN(Number(actor.newQuantity))) {
            throw new Error(`${name} requires a new quantity value`);
          }
          payload.new_quantity = Number(actor.newQuantity);
        }
        return payload;
      });
      const payload = {
        scenario,
        order_id: orderIdInput ? orderIdInput.trim() : null,
        actors: actorPayload,
      };
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
  const isolationOverview = statusSnapshot?.result_summary?.isolation_overview || {};
  const readUncommittedSelected = actors.some((actor) => actor.isolationLevel === 'READ_UNCOMMITTED');
  const orchestrationNote = statusSnapshot?.result_summary?.read_uncommitted_note;
  const isolationNote = orchestrationNote || (readUncommittedSelected
    ? 'PostgreSQL promotes READ UNCOMMITTED to READ COMMITTED to stay standards compliant.'
    : null);
  const finalStateEntries = useMemo(() => {
    const snapshots = statusSnapshot?.result_summary?.final_states;
    if (!snapshots) return [];
    return Object.entries(snapshots);
  }, [statusSnapshot]);
  const serializationConflicts = statusSnapshot?.result_summary?.serialization_conflicts || [];

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
            <Label htmlFor="orderId" className="text-slate-700 font-medium">Order ID (optional)</Label>
            <Input
              id="orderId"
              value={orderIdInput}
              onChange={(e) => setOrderIdInput(e.target.value)}
              placeholder="Leave blank to auto-select latest"
              className="bg-white border-slate-300"
            />
            <p className="text-xs text-muted-foreground">Provide a UUID to target a specific order.</p>
          </div>
          <div className="space-y-2">
            <Label className="text-slate-700 font-medium">Read Uncommitted note</Label>
            {isolationNote ? (
              <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-2 py-1 flex items-center gap-2">
                <Shield className="w-3 h-3" />
                {isolationNote}
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">Shown when any actor requests READ UNCOMMITTED.</p>
            )}
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

        <div className="grid gap-4 md:grid-cols-2">
          {actors.map((actor, idx) => {
            const role = activeRoles[idx] ?? 'read';
            const writeMode = role === 'write';
            return (
              <div key={idx} className="border rounded-lg p-4 space-y-3 bg-white">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-slate-700">{`Transaction ${idx === 0 ? 'A' : 'B'}`} · {role.toUpperCase()}</p>
                  <Badge variant="outline" className="bg-cyan-50 text-cyan-700 border-cyan-200">{role}</Badge>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs uppercase text-slate-500">Label</Label>
                  <Input value={actor.name} onChange={(e) => updateActor(idx, 'name', e.target.value)} className="bg-white border-slate-300" />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs uppercase text-slate-500">Node</Label>
                  <Select value={actor.node} onValueChange={(value) => updateActor(idx, 'node', value)}>
                    <SelectTrigger className="bg-white border-slate-300">
                      <SelectValue placeholder="Choose node" />
                    </SelectTrigger>
                    <SelectContent className="bg-white">
                      {nodeOptions.map((node) => (
                        <SelectItem key={node.id} value={node.id}>{node.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs uppercase text-slate-500">Isolation Level</Label>
                  <Select value={actor.isolationLevel} onValueChange={(value) => updateActor(idx, 'isolationLevel', value)}>
                    <SelectTrigger className="bg-white border-slate-300">
                      <SelectValue placeholder="Pick isolation" />
                    </SelectTrigger>
                    <SelectContent className="bg-white">
                      {isolationLevels.map((level) => (
                        <SelectItem key={level.id} value={level.id}>{level.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs uppercase text-slate-500">pg_sleep delay (seconds)</Label>
                  <Input
                    type="number"
                    min={0}
                    step={0.1}
                    value={actor.delaySeconds}
                    onChange={(e) => updateActor(idx, 'delaySeconds', e.target.value)}
                    className="bg-white border-slate-300"
                  />
                </div>
                {writeMode && (
                  <div className="space-y-2">
                    <Label className="text-xs uppercase text-slate-500">Commit quantity</Label>
                    <Input
                      type="number"
                      value={actor.newQuantity}
                      onChange={(e) => updateActor(idx, 'newQuantity', e.target.value)}
                      placeholder="e.g., 5"
                      className="bg-white border-slate-300"
                    />
                    <p className="text-xs text-muted-foreground">Required for write transactions.</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>

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
                  <Shield className="w-4 h-4" /> Isolation Overview
                </p>
                <div className="grid gap-2 md:grid-cols-2">
                  {Object.entries(isolationOverview).map(([actorId, iso]) => (
                    <div key={actorId} className="p-3 border rounded-md bg-slate-50">
                      <p className="text-xs uppercase text-slate-500">{actorId}</p>
                      <p className="text-sm font-semibold">{iso}</p>
                    </div>
                  ))}
                  {Object.keys(isolationOverview).length === 0 && (
                    <p className="text-xs text-slate-500">Pending actor metadata...</p>
                  )}
                </div>
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
                {statusSnapshot.result_summary?.actor_results && (
                  <div className="space-y-2">
                    <p className="text-xs uppercase text-slate-500">Actor observations</p>
                    {Object.entries(statusSnapshot.result_summary.actor_results).map(([actorId, result]) => (
                      <div key={actorId} className="border rounded-md p-3 bg-white">
                        <p className="text-sm font-semibold">{actorId} · {result.role}</p>
                        <p className="text-xs text-slate-500">Node: {result.node} · Delay: {result.delay_seconds}s</p>
                        <pre className="text-xs text-slate-700 bg-slate-50 rounded-md p-2 mt-2 overflow-x-auto">
                          {JSON.stringify(result.details, null, 2)}
                        </pre>
                      </div>
                    ))}
                  </div>
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
