import { motion } from 'framer-motion';
import { Database, ArrowDown } from 'lucide-react';

export function SimplifiedArchitecture({ activeScenario, isRunning }) {
  return (
    <div className="relative py-8">
      {/* Grid Background */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(6,182,212,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(6,182,212,0.05)_1px,transparent_1px)] bg-[size:40px_40px] pointer-events-none" />
      
      <div className="relative max-w-4xl mx-auto">
        {/* User Layer */}
        <motion.div 
          className="text-center mb-8"
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="inline-flex items-center gap-3 px-6 py-4 bg-gradient-to-r from-cyan-500 to-blue-500 text-white rounded-lg shadow-lg">
            <Database className="w-6 h-6" />
            <span className="font-semibold tracking-wide">USER APPLICATION</span>
          </div>
          
          {/* Connection Arrow */}
          <motion.div 
            className="flex justify-center my-6"
            animate={isRunning ? { opacity: [0.3, 1, 0.3] } : {}}
            transition={{ duration: 2, repeat: Infinity }}
          >
            <ArrowDown className="w-6 h-6 text-cyan-600" />
          </motion.div>
        </motion.div>

        {/* Three Database Nodes */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[
            { 
              id: 0, 
              title: 'Central Node',
              subtitle: 'All Orders',
              color: 'from-green-400 to-emerald-500',
              data: 'Complete Dataset'
            },
            { 
              id: 1, 
              title: 'Fragment Node',
              subtitle: 'Qty<=5',
              color: 'from-yellow-400 to-orange-500',
              data: 'Fragment 1'
            },
            { 
              id: 2, 
              title: 'Fragment Node',
              subtitle: 'Qty>5',
              color: 'from-blue-400 to-indigo-500',
              data: 'Fragment 2'
            }
          ].map((node, index) => (
            <motion.div
              key={node.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.2 }}
              className="relative"
            >
              <div className={`relative bg-gradient-to-br ${node.color} p-[2px] rounded-xl shadow-xl`}>
                <div className="bg-white rounded-xl p-6">
                  <div className="text-center space-y-4">
                    {/* Animated Database Icon */}
                    <motion.div
                      animate={isRunning && activeScenario !== null ? {
                        scale: [1, 1.2, 1],
                        rotate: [0, 5, -5, 0]
                      } : {}}
                      transition={{ duration: 2, repeat: Infinity }}
                    >
                      <Database className={`w-16 h-16 mx-auto ${
                        node.id === 1 ? 'text-green-600' : 
                        node.id === 2 ? 'text-yellow-600' : 
                        'text-blue-600'
                      }`} />
                    </motion.div>
                    
                    <div>
                      <h3 className="font-bold text-lg text-gray-800">{node.title}</h3>
                      <p className="text-sm text-gray-600">{node.subtitle}</p>
                    </div>

                    {/* Data Indicator */}
                    <div className={`inline-block px-4 py-2 rounded-full text-xs font-medium ${
                      node.id === 1 ? 'bg-green-100 text-green-700' : 
                      node.id === 2 ? 'bg-yellow-100 text-yellow-700' : 
                      'bg-blue-100 text-blue-700'
                    }`}>
                      {node.data}
                    </div>

                    {/* Activity Indicator */}
                    {isRunning && activeScenario !== null && (
                      <motion.div
                        className={`w-full h-2 rounded-full overflow-hidden ${
                          node.id === 1 ? 'bg-green-100' : 
                          node.id === 2 ? 'bg-yellow-100' : 
                          'bg-blue-100'
                        }`}
                      >
                        <motion.div
                          className={`h-full ${
                            node.id === 1 ? 'bg-green-500' : 
                            node.id === 2 ? 'bg-yellow-500' : 
                            'bg-blue-500'
                          }`}
                          animate={{ width: ['0%', '100%', '0%'] }}
                          transition={{ 
                            duration: 2, 
                            repeat: Infinity, 
                            ease: 'easeInOut',
                            delay: index * 0.3
                          }}
                        />
                      </motion.div>
                    )}
                  </div>
                </div>
              </div>
              
              {/* Node Label */}
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-gray-800 text-white text-xs font-bold rounded-full">
                NODE {node.id}
              </div>
            </motion.div>
          ))}
        </div>

        {/* Fragmentation Info */}
        <motion.div 
          className="mt-12 text-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8 }}
        >
          <div className="inline-flex items-center gap-2 px-6 py-3 bg-cyan-50 border-2 border-cyan-200 rounded-lg">
            <div className="flex items-center gap-4 text-sm">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-yellow-500" />
                <span className="text-gray-700">Node 1: Qty greater less than or equal to 5 </span>
              </div>
              <div className="w-px h-4 bg-gray-300" />
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-blue-500" />
                <span className="text-gray-700">Node 3: Odd Order IDs</span>
              </div>
              <div className="w-px h-4 bg-gray-300" />
              <span className="text-cyan-700 font-semibold">= Node 2 greater than 5</span>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
