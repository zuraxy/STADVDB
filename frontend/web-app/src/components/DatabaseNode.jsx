import { motion } from 'framer-motion';
import { Database, HardDrive } from 'lucide-react';

export function DatabaseNode({ nodeNumber, title, description, activeScenario, isRunning }) {
  // Determine if this node is active based on scenario
  const isActive = activeScenario !== null && isRunning;
  
  return (
    <motion.div 
      className="relative"
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5, delay: nodeNumber * 0.1 }}
    >
      <div className={`relative bg-gradient-to-br from-white to-blue-50 border-2 ${
        isActive ? 'border-cyan-600' : 'border-cyan-400'
      } shadow-lg p-6 transition-all duration-300`}>
        {/* Node Header */}
        <div className="text-center space-y-3 mb-4">
          <div className="flex items-center justify-center gap-2">
            <Database className="w-5 h-5 text-cyan-600" />
            <span className="text-xs text-cyan-700 tracking-widest">NODE {nodeNumber}</span>
          </div>
          
          {/* Animated Database Icon */}
          <motion.div
            animate={isActive ? {
              scale: [1, 1.1, 1],
              opacity: [0.7, 1, 0.7]
            } : {}}
            transition={{ duration: 2, repeat: Infinity }}
          >
            <HardDrive className="w-12 h-12 text-cyan-600 mx-auto" />
          </motion.div>
          
          <div className="space-y-1">
            <div className="text-sm text-cyan-700">{title}</div>
            <div className="text-xs text-cyan-600/70">{description}</div>
          </div>
        </div>

        {/* Data Representation */}
        <div className="space-y-2 mt-4">
          <div className="h-1 bg-cyan-200 relative overflow-hidden">
            {isActive && (
              <motion.div
                className="absolute inset-y-0 left-0 bg-cyan-500"
                animate={{ width: ['0%', '100%', '0%'] }}
                transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
              />
            )}
          </div>
          <div className="h-1 bg-cyan-200 relative overflow-hidden">
            {isActive && (
              <motion.div
                className="absolute inset-y-0 left-0 bg-cyan-500"
                animate={{ width: ['0%', '100%', '0%'] }}
                transition={{ duration: 2, repeat: Infinity, ease: 'linear', delay: 0.3 }}
              />
            )}
          </div>
          <div className="h-1 bg-cyan-200 relative overflow-hidden">
            {isActive && (
              <motion.div
                className="absolute inset-y-0 left-0 bg-cyan-500"
                animate={{ width: ['0%', '100%', '0%'] }}
                transition={{ duration: 2, repeat: Infinity, ease: 'linear', delay: 0.6 }}
              />
            )}
          </div>
        </div>

        {/* Status Indicator */}
        <div className="mt-4 flex items-center justify-center gap-2">
          <div className={`w-2 h-2 rounded-full ${
            isActive ? 'bg-green-500 animate-pulse' : 'bg-slate-300'
          }`} />
          <span className="text-xs text-slate-600">
            {isActive ? 'ACTIVE' : 'STANDBY'}
          </span>
        </div>

        {/* Corner accents */}
        <div className="absolute top-0 left-0 w-3 h-3 border-t border-l border-cyan-600" />
        <div className="absolute top-0 right-0 w-3 h-3 border-t border-r border-cyan-600" />
        <div className="absolute bottom-0 left-0 w-3 h-3 border-b border-l border-cyan-600" />
        <div className="absolute bottom-0 right-0 w-3 h-3 border-b border-r border-cyan-600" />
      </div>
    </motion.div>
  );
}
