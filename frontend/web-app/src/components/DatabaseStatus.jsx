import { Activity, Database, CheckCircle, Clock } from 'lucide-react';

export function DatabaseStatus({ isRunning, activeScenario }) {
  const getScenarioName = () => {
    switch (activeScenario) {
      case 1: return 'Concurrent Reads';
      case 2: return 'Read-Write Conflict';
      case 3: return 'Concurrent Writes';
      default: return 'Idle';
    }
  };

  return (
    <div className="bg-white border-2 border-cyan-400 shadow-lg p-6">
      <div className="flex items-center justify-between">
        {/* Left Section */}
        <div className="flex items-center gap-4">
          <div className="p-3 bg-cyan-100 border-2 border-cyan-400 rounded-lg">
            <Database className="w-6 h-6 text-cyan-700" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-cyan-800">Database Status</h3>
            <p className="text-sm text-slate-600">Real-time monitoring</p>
          </div>
        </div>

        {/* Right Section - Status Indicators */}
        <div className="flex items-center gap-6">
          {/* Connection Status */}
          <div className="flex items-center gap-2">
            <CheckCircle className="w-5 h-5 text-green-600" />
            <div>
              <p className="text-xs text-slate-500 uppercase tracking-wide">Connection</p>
              <p className="text-sm font-semibold text-green-700">Active</p>
            </div>
          </div>

          {/* Activity Status */}
          <div className="flex items-center gap-2">
            <Activity className={`w-5 h-5 ${isRunning ? 'text-amber-600 animate-pulse' : 'text-slate-400'}`} />
            <div>
              <p className="text-xs text-slate-500 uppercase tracking-wide">Activity</p>
              <p className={`text-sm font-semibold ${isRunning ? 'text-amber-700' : 'text-slate-600'}`}>
                {isRunning ? 'Running' : 'Idle'}
              </p>
            </div>
          </div>

          {/* Current Scenario */}
          <div className="flex items-center gap-2">
            <Clock className="w-5 h-5 text-blue-600" />
            <div>
              <p className="text-xs text-slate-500 uppercase tracking-wide">Scenario</p>
              <p className="text-sm font-semibold text-blue-700">{getScenarioName()}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Progress Bar */}
      {isRunning && (
        <div className="mt-4 h-2 bg-slate-200 rounded-full overflow-hidden">
          <div className="h-full bg-gradient-to-r from-cyan-400 via-blue-500 to-cyan-400 animate-pulse"></div>
        </div>
      )}
    </div>
  );
}
