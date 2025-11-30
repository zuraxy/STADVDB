import { motion } from 'framer-motion';
import { Database, Server, Monitor, Settings, Clock } from 'lucide-react';
import { DatabaseNode } from './DatabaseNode';

export function DatabaseArchitecture({ activeScenario, isRunning }) {
  return (
    <div className="relative">
      {/* Grid Background Effect */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(6,182,212,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(6,182,212,0.08)_1px,transparent_1px)] bg-[size:50px_50px] pointer-events-none" />
      
      <div className="relative space-y-12">
        {/* Tier 1: User Interface */}
        <motion.div 
          className="flex flex-col items-center space-y-4"
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <div className="flex items-center gap-3 text-cyan-700 mb-2">
            <Monitor className="w-5 h-5" />
            <span className="text-sm tracking-widest">TIER 1: USER INTERFACE</span>
          </div>
          
          <div className="flex gap-4">
            <button className="px-6 py-3 bg-white border-2 border-cyan-400 hover:border-cyan-600 hover:bg-cyan-50 transition-all shadow-lg shadow-cyan-200/50">
              <span className="text-cyan-700">CREATE USER</span>
            </button>
            <button className="px-6 py-3 bg-white border-2 border-cyan-400 hover:border-cyan-600 hover:bg-cyan-50 transition-all shadow-lg shadow-cyan-200/50">
              <span className="text-cyan-700">READ DATA</span>
            </button>
            <button className="px-6 py-3 bg-white border-2 border-cyan-400 hover:border-cyan-600 hover:bg-cyan-50 transition-all shadow-lg shadow-cyan-200/50">
              <span className="text-cyan-700">UPDATE RECORD</span>
            </button>
          </div>

          {/* Connection Line */}
          <div className="w-0.5 h-16 bg-gradient-to-b from-cyan-500 to-transparent relative">
            {isRunning && (
              <motion.div
                className="absolute w-2 h-2 bg-cyan-600 rounded-full -left-[3px]"
                animate={{ top: ['0%', '100%'] }}
                transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}
              />
            )}
          </div>
        </motion.div>

        {/* Tier 2: Application Server */}
        <motion.div 
          className="flex flex-col items-center space-y-4"
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <div className="flex items-center gap-3 text-cyan-700 mb-2">
            <Server className="w-5 h-5" />
            <span className="text-sm tracking-widest">TIER 2: APPLICATION SERVER</span>
          </div>
          
          <div className="relative w-80 h-32 bg-gradient-to-br from-white to-cyan-50 border-2 border-cyan-400 shadow-xl shadow-cyan-200/40">
            <div className="absolute inset-0 border border-cyan-300/30 m-3" />
            <div className="flex items-center justify-center h-full">
              <div className="text-center space-y-2">
                <Server className="w-8 h-8 text-cyan-600 mx-auto" />
                <div className="text-sm text-cyan-700">TRANSACTION PROCESSOR</div>
              </div>
            </div>
            
            {/* Corner accents */}
            <div className="absolute top-0 left-0 w-4 h-4 border-t-2 border-l-2 border-cyan-600" />
            <div className="absolute top-0 right-0 w-4 h-4 border-t-2 border-r-2 border-cyan-600" />
            <div className="absolute bottom-0 left-0 w-4 h-4 border-b-2 border-l-2 border-cyan-600" />
            <div className="absolute bottom-0 right-0 w-4 h-4 border-b-2 border-r-2 border-cyan-600" />
          </div>

          {/* Connection Lines to Database Nodes */}
          <div className="relative w-full h-24">
            {/* Central line down */}
            <div className="absolute left-1/2 top-0 w-0.5 h-12 bg-cyan-400 -translate-x-1/2" />
            
            {/* Split into three */}
            <div className="absolute left-1/2 top-12 w-0.5 h-4 bg-cyan-400 -translate-x-1/2" />
            
            {/* Three branches */}
            <div className="absolute top-16 left-0 right-0 flex justify-between px-32">
              <div className="w-0.5 h-8 bg-cyan-400 relative">
                {isRunning && (
                  <motion.div
                    className="absolute w-2 h-2 bg-cyan-600 rounded-full -left-[3px]"
                    animate={{ top: ['0%', '100%'] }}
                    transition={{ duration: 1, repeat: Infinity, ease: 'linear', delay: 0.3 }}
                  />
                )}
              </div>
              <div className="w-0.5 h-8 bg-cyan-400 relative">
                {isRunning && (
                  <motion.div
                    className="absolute w-2 h-2 bg-cyan-600 rounded-full -left-[3px]"
                    animate={{ top: ['0%', '100%'] }}
                    transition={{ duration: 1, repeat: Infinity, ease: 'linear', delay: 0.5 }}
                  />
                )}
              </div>
              <div className="w-0.5 h-8 bg-cyan-400 relative">
                {isRunning && (
                  <motion.div
                    className="absolute w-2 h-2 bg-cyan-600 rounded-full -left-[3px]"
                    animate={{ top: ['0%', '100%'] }}
                    transition={{ duration: 1, repeat: Infinity, ease: 'linear', delay: 0.7 }}
                  />
                )}
              </div>
            </div>
            
            {/* Horizontal connector */}
            <div className="absolute top-16 left-32 right-32 h-0.5 bg-cyan-400" />
          </div>
        </motion.div>

        {/* Tier 3: Database Servers with Scheduler */}
        <motion.div 
          className="flex flex-col items-center space-y-6"
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
        >
          <div className="flex items-center gap-3 text-cyan-700 mb-2">
            <Database className="w-5 h-5" />
            <span className="text-sm tracking-widest">TIER 3: DATABASE SERVERS</span>
          </div>

          {/* Scheduler/Concurrency Manager */}
          <motion.div 
            className="relative w-full max-w-2xl mx-auto mb-4"
            animate={isRunning ? { 
              boxShadow: [
                '0 0 20px rgba(251, 146, 60, 0.3)',
                '0 0 40px rgba(251, 146, 60, 0.5)',
                '0 0 20px rgba(251, 146, 60, 0.3)'
              ]
            } : {}}
            transition={{ duration: 2, repeat: Infinity }}
          >
            <div className="bg-gradient-to-r from-amber-50 via-orange-50 to-amber-50 border-2 border-amber-400 shadow-xl p-4">
              <div className="flex items-center justify-center gap-4">
                <motion.div
                  animate={isRunning ? { rotate: 360 } : {}}
                  transition={{ duration: 3, repeat: Infinity, ease: 'linear' }}
                >
                  <Settings className="w-8 h-8 text-amber-600" />
                </motion.div>
                <div className="space-y-1">
                  <div className="text-amber-700 tracking-wider">SCHEDULER / CONCURRENCY MANAGER</div>
                  <div className="text-xs text-amber-600">Transaction Ordering & Conflict Resolution</div>
                </div>
                <Clock className="w-6 h-6 text-amber-600" />
              </div>
            </div>
            
            {/* Corner accents */}
            <div className="absolute top-0 left-0 w-6 h-6 border-t-2 border-l-2 border-amber-600" />
            <div className="absolute top-0 right-0 w-6 h-6 border-t-2 border-r-2 border-amber-600" />
            <div className="absolute bottom-0 left-0 w-6 h-6 border-b-2 border-l-2 border-amber-600" />
            <div className="absolute bottom-0 right-0 w-6 h-6 border-b-2 border-r-2 border-amber-600" />
          </motion.div>

          {/* Database Nodes */}
          <div className="grid grid-cols-3 gap-8 w-full max-w-4xl">
            <DatabaseNode 
              nodeNumber={1}
              title="CENTRAL NODE"
              description="All rows in main database"
              activeScenario={activeScenario}
              isRunning={isRunning}
            />
            <DatabaseNode 
              nodeNumber={2}
              title="PARTITION NODE 2"
              description="Fragmented rows (Criterion A)"
              activeScenario={activeScenario}
              isRunning={isRunning}
            />
            <DatabaseNode 
              nodeNumber={3}
              title="PARTITION NODE 3"
              description="Fragmented rows (Criterion B)"
              activeScenario={activeScenario}
              isRunning={isRunning}
            />
          </div>
        </motion.div>
      </div>
    </div>
  );
}
