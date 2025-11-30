import { DatabaseArchitecture } from './DatabaseArchitecture';
import { ConcurrencyScenarios } from './ConcurrencyScenarios';
import { TransactionFlow } from './TransactionFlow';

export function DatabasePage({ activeScenario, setActiveScenario, isRunning, setIsRunning }) {
  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="bg-white border-2 border-cyan-400 shadow-lg p-6">
        <h2 className="text-2xl font-bold text-cyan-800">Database Architecture</h2>
        <p className="text-sm text-slate-600 mt-1">Visualize distributed database nodes and concurrency scenarios</p>
      </div>

      {/* Database Architecture Visualization */}
      <DatabaseArchitecture 
        activeScenario={activeScenario}
        isRunning={isRunning}
      />

      {/* Transaction Flow Visualization */}
      {activeScenario !== null && isRunning && (
        <TransactionFlow scenario={activeScenario} />
      )}

      {/* Concurrency Scenarios Control Panel */}
      <ConcurrencyScenarios 
        activeScenario={activeScenario}
        setActiveScenario={setActiveScenario}
        isRunning={isRunning}
        setIsRunning={setIsRunning}
      />
    </div>
  );
}
