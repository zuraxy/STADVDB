import { motion } from 'framer-motion';
import { ArrowRight, Lock, Unlock, CheckCircle, Clock } from 'lucide-react';

export function TransactionFlow({ scenario }) {
  const getScenarioInfo = () => {
    switch (scenario) {
      case 1:
        return {
          title: 'Concurrent Read Operations',
          transactions: [
            { node: 1, type: 'READ', color: 'green', delay: 0 },
            { node: 2, type: 'READ', color: 'green', delay: 0.2 },
            { node: 3, type: 'READ', color: 'green', delay: 0.4 }
          ],
          status: 'All transactions execute in parallel - No conflicts',
          lockStatus: 'No locks required',
          icon: Unlock
        };
      case 2:
        return {
          title: 'Read-Write Conflict Resolution',
          transactions: [
            { node: 1, type: 'WRITE', color: 'yellow', delay: 0 },
            { node: 2, type: 'READ', color: 'yellow', delay: 0.5 },
            { node: 3, type: 'READ', color: 'yellow', delay: 1.0 }
          ],
          status: 'Sequential execution - Reads wait for write completion',
          lockStatus: 'Shared locks after exclusive lock release',
          icon: Clock
        };
      case 3:
        return {
          title: 'Write-Write Conflict Resolution',
          transactions: [
            { node: 1, type: 'WRITE', color: 'red', delay: 0 },
            { node: 2, type: 'WRITE', color: 'red', delay: 1.0 },
            { node: 3, type: 'WRITE', color: 'red', delay: 2.0 }
          ],
          status: 'Strict serialization - One write at a time',
          lockStatus: 'Exclusive locks enforced sequentially',
          icon: Lock
        };
      default:
        return null;
    }
  };

  const scenarioInfo = getScenarioInfo();
  if (!scenarioInfo) return null;

  const Icon = scenarioInfo.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-gradient-to-br from-white to-blue-50 border-2 border-cyan-400 shadow-xl p-8"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-8 pb-4 border-b border-cyan-400/50">
        <div className="flex items-center gap-3">
          <Icon className="w-6 h-6 text-cyan-600" />
          <div>
            <h3 className="text-cyan-700 tracking-wider">{scenarioInfo.title}</h3>
            <p className="text-sm text-slate-600 mt-1">{scenarioInfo.status}</p>
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-cyan-700 tracking-widest">LOCK STATUS</div>
          <div className="text-sm text-slate-700">{scenarioInfo.lockStatus}</div>
        </div>
      </div>

      {/* Transaction Timeline */}
      <div className="space-y-6">
        {scenarioInfo.transactions.map((transaction, index) => (
          <motion.div
            key={index}
            initial={{ opacity: 0, x: -50 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: transaction.delay, duration: 0.5 }}
            className="relative"
          >
            <div className="flex items-center gap-4">
              {/* Node Label */}
              <div className="w-32 text-right">
                <span className="text-sm text-cyan-700">Node {transaction.node}</span>
              </div>

              {/* Arrow */}
              <ArrowRight className={`w-5 h-5 text-${transaction.color}-600`} />

              {/* Transaction Type */}
              <motion.div
                className={`px-6 py-3 bg-${transaction.color}-50 border-2 border-${transaction.color}-400 min-w-32 text-center`}
                animate={{
                  boxShadow: [
                    `0 0 10px rgba(${transaction.color === 'green' ? '34, 197, 94' : transaction.color === 'yellow' ? '234, 179, 8' : '239, 68, 68'}, 0.3)`,
                    `0 0 20px rgba(${transaction.color === 'green' ? '34, 197, 94' : transaction.color === 'yellow' ? '234, 179, 8' : '239, 68, 68'}, 0.6)`,
                    `0 0 10px rgba(${transaction.color === 'green' ? '34, 197, 94' : transaction.color === 'yellow' ? '234, 179, 8' : '239, 68, 68'}, 0.3)`
                  ]
                }}
                transition={{ duration: 2, repeat: Infinity, delay: transaction.delay }}
              >
                <span className={`text-${transaction.color}-700 tracking-wider`}>
                  {transaction.type}
                </span>
              </motion.div>

              {/* Progress Indicator */}
              <div className="flex-1 h-2 bg-slate-200 rounded-full overflow-hidden">
                <motion.div
                  className={`h-full bg-${transaction.color}-500`}
                  initial={{ width: '0%' }}
                  animate={{ width: '100%' }}
                  transition={{
                    delay: transaction.delay,
                    duration: 2,
                    repeat: Infinity,
                    repeatDelay: 1
                  }}
                />
              </div>

              {/* Status Icon */}
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{
                  delay: transaction.delay + 2,
                  duration: 0.3,
                  repeat: Infinity,
                  repeatDelay: 3
                }}
              >
                <CheckCircle className={`w-5 h-5 text-${transaction.color}-600`} />
              </motion.div>
            </div>

            {/* Timeline connector */}
            {index < scenarioInfo.transactions.length - 1 && (
              <div className="ml-32 mt-2 mb-2 flex items-center gap-2">
                <div className="w-5 h-8 border-l border-b border-cyan-400/50 rounded-bl" />
                <span className="text-xs text-slate-500">
                  {scenario === 1 ? 'Parallel' : 'Sequential'}
                </span>
              </div>
            )}
          </motion.div>
        ))}
      </div>

      {/* Legend */}
      <div className="mt-8 pt-6 border-t border-cyan-400/50 flex items-center justify-center gap-8 text-xs">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 bg-green-500 rounded" />
          <span className="text-slate-600">Safe (No Conflict)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 bg-yellow-500 rounded" />
          <span className="text-slate-600">Moderate (Locking Required)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 bg-red-500 rounded" />
          <span className="text-slate-600">Critical (Serialization)</span>
        </div>
      </div>
    </motion.div>
  );
}
