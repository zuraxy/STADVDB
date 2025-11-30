import { motion } from 'framer-motion';
import { Play, Pause, Eye, Edit, AlertTriangle } from 'lucide-react';

export function ConcurrencyScenarios({ 
  activeScenario, 
  setActiveScenario, 
  isRunning, 
  setIsRunning 
}) {
  
  const scenarios = [
    {
      id: 1,
      title: 'CASE #1: CONCURRENT READS',
      description: 'Multiple nodes reading the same data item simultaneously',
      icon: Eye,
      color: 'green',
      details: 'No conflicts - All transactions can proceed in parallel'
    },
    {
      id: 2,
      title: 'CASE #2: READ-WRITE CONFLICT',
      description: 'Mixed read and write operations on the same data item',
      icon: Edit,
      color: 'yellow',
      details: 'Requires locking - Reads must wait for writes to complete'
    },
    {
      id: 3,
      title: 'CASE #3: CONCURRENT WRITES',
      description: 'Multiple nodes writing/updating the same data item',
      icon: AlertTriangle,
      color: 'red',
      details: 'Critical section - Strict serialization required'
    }
  ];

  const handleScenarioClick = (scenarioId) => {
    if (activeScenario === scenarioId && isRunning) {
      setIsRunning(false);
    } else {
      setActiveScenario(scenarioId);
      setIsRunning(true);
    }
  };

  const getColorClasses = (color, isActive) => {
    const colors = {
      green: {
        border: isActive ? 'border-green-600' : 'border-green-400',
        bg: 'from-green-50 to-emerald-50',
        text: 'text-green-700',
        shadow: isActive ? 'shadow-green-300/40' : 'shadow-green-200/30'
      },
      yellow: {
        border: isActive ? 'border-yellow-600' : 'border-yellow-400',
        bg: 'from-yellow-50 to-amber-50',
        text: 'text-yellow-700',
        shadow: isActive ? 'shadow-yellow-300/40' : 'shadow-yellow-200/30'
      },
      red: {
        border: isActive ? 'border-red-600' : 'border-red-400',
        bg: 'from-red-50 to-rose-50',
        text: 'text-red-700',
        shadow: isActive ? 'shadow-red-300/40' : 'shadow-red-200/30'
      }
    };
    return colors[color];
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between border-t border-cyan-400/50 pt-6">
        <div className="flex items-center gap-3 text-cyan-700">
          <span className="text-sm tracking-widest">CONCURRENCY SCENARIOS</span>
        </div>
        {activeScenario !== null && (
          <button
            onClick={() => {
              setIsRunning(false);
              setActiveScenario(null);
            }}
            className="px-4 py-2 bg-red-50 border-2 border-red-400 hover:border-red-600 text-red-700 text-sm transition-all"
          >
            RESET
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {scenarios.map((scenario) => {
          const isActive = activeScenario === scenario.id;
          const colors = getColorClasses(scenario.color, isActive);
          const Icon = scenario.icon;

          return (
            <motion.div
              key={scenario.id}
              className={`relative cursor-pointer transition-all duration-300 ${
                isActive ? 'scale-105' : 'hover:scale-102'
              }`}
              onClick={() => handleScenarioClick(scenario.id)}
              whileHover={{ y: -4 }}
            >
              <div className={`bg-gradient-to-br ${colors.bg} border-2 ${colors.border} shadow-xl ${colors.shadow} p-6`}>
                {/* Header */}
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <Icon className={`w-6 h-6 ${colors.text}`} />
                    <div className={`text-xs ${colors.text} tracking-widest`}>
                      SCENARIO {scenario.id}
                    </div>
                  </div>
                  {isActive && isRunning && (
                    <motion.div
                      animate={{ scale: [1, 1.2, 1] }}
                      transition={{ duration: 1, repeat: Infinity }}
                    >
                      <div className={`w-3 h-3 rounded-full ${colors.text.replace('text-', 'bg-')}`} />
                    </motion.div>
                  )}
                </div>

                {/* Title */}
                <h3 className={`${colors.text} mb-2`}>{scenario.title}</h3>
                
                {/* Description */}
                <p className="text-sm text-slate-600 mb-4">{scenario.description}</p>

                {/* Details */}
                <div className={`text-xs ${colors.text} border-t-2 ${colors.border} pt-3`}>
                  {scenario.details}
                </div>

                {/* Action Button */}
                <div className="mt-4 flex items-center justify-center">
                  {isActive && isRunning ? (
                    <div className="flex items-center gap-2 text-sm">
                      <Pause className="w-4 h-4" />
                      <span className={colors.text}>RUNNING</span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-sm text-slate-500">
                      <Play className="w-4 h-4" />
                      <span>CLICK TO START</span>
                    </div>
                  )}
                </div>

                {/* Corner accents */}
                <div className={`absolute top-0 left-0 w-4 h-4 border-t-2 border-l-2 ${colors.border}`} />
                <div className={`absolute top-0 right-0 w-4 h-4 border-t-2 border-r-2 ${colors.border}`} />
                <div className={`absolute bottom-0 left-0 w-4 h-4 border-b-2 border-l-2 ${colors.border}`} />
                <div className={`absolute bottom-0 right-0 w-4 h-4 border-b-2 border-r-2 ${colors.border}`} />
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
