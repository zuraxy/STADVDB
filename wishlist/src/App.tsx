import { useState } from 'react';
import { DatabaseDashboard } from './components/DatabaseDashboard';
import { SimplifiedArchitecture } from './components/SimplifiedArchitecture';
import { ConcurrencyScenarios } from './components/ConcurrencyScenarios';
import { TransactionFlow } from './components/TransactionFlow';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';
import { Database, Activity, Network } from 'lucide-react';

export default function App() {
  const [activeScenario, setActiveScenario] = useState<number | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-cyan-50 to-slate-50">
      <div className="max-w-[1600px] mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="text-center space-y-3 pb-6 border-b-2 border-cyan-200">
          <div className="flex items-center justify-center gap-3">
            <Database className="w-8 h-8 text-cyan-600" />
            <h1 className="text-4xl font-bold text-cyan-700 tracking-tight">
              Distributed Database System
            </h1>
          </div>
          <p className="text-slate-600 text-lg">
            Three-Node Architecture with Horizontal Fragmentation & Concurrency Control
          </p>
        </div>

        {/* Main Tabbed Interface */}
        <Tabs defaultValue="dashboard" className="w-full">
          <TabsList className="grid w-full grid-cols-3 mb-6 bg-white border-2 border-cyan-200 p-1">
            <TabsTrigger 
              value="dashboard" 
              className="data-[state=active]:bg-cyan-500 data-[state=active]:text-white"
            >
              <Database className="w-4 h-4 mr-2" />
              Database Dashboard
            </TabsTrigger>
            <TabsTrigger 
              value="concurrency"
              className="data-[state=active]:bg-cyan-500 data-[state=active]:text-white"
            >
              <Activity className="w-4 h-4 mr-2" />
              Concurrency Testing
            </TabsTrigger>
            <TabsTrigger 
              value="architecture"
              className="data-[state=active]:bg-cyan-500 data-[state=active]:text-white"
            >
              <Network className="w-4 h-4 mr-2" />
              Architecture Overview
            </TabsTrigger>
          </TabsList>

          {/* Tab 1: Database Dashboard with Live Tables */}
          <TabsContent value="dashboard" className="space-y-6">
            <DatabaseDashboard />
          </TabsContent>

          {/* Tab 2: Concurrency Scenarios */}
          <TabsContent value="concurrency" className="space-y-6">
            <div className="bg-white rounded-lg border-2 border-cyan-200 p-6">
              <SimplifiedArchitecture 
                activeScenario={activeScenario}
                isRunning={isRunning}
              />
              
              {activeScenario !== null && isRunning && (
                <div className="mt-8">
                  <TransactionFlow scenario={activeScenario} />
                </div>
              )}
              
              <div className="mt-8">
                <ConcurrencyScenarios 
                  activeScenario={activeScenario}
                  setActiveScenario={setActiveScenario}
                  isRunning={isRunning}
                  setIsRunning={setIsRunning}
                />
              </div>
            </div>
          </TabsContent>

          {/* Tab 3: Architecture Overview */}
          <TabsContent value="architecture" className="space-y-6">
            <div className="bg-white rounded-lg border-2 border-cyan-200 p-8">
              <SimplifiedArchitecture 
                activeScenario={null}
                isRunning={false}
              />
              
              {/* Additional Architecture Info */}
              <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="p-6 bg-green-50 border-2 border-green-200 rounded-lg">
                  <h3 className="font-bold text-green-800 mb-3">Node 1: Central Node</h3>
                  <ul className="space-y-2 text-sm text-green-700">
                    <li>• Stores complete dataset</li>
                    <li>• Acts as master replica</li>
                    <li>• All departments included</li>
                    <li>• Primary transaction coordinator</li>
                  </ul>
                </div>
                <div className="p-6 bg-yellow-50 border-2 border-yellow-200 rounded-lg">
                  <h3 className="font-bold text-yellow-800 mb-3">Node 2: Sales Fragment</h3>
                  <ul className="space-y-2 text-sm text-yellow-700">
                    <li>• Horizontal fragmentation</li>
                    <li>• Department = 'Sales'</li>
                    <li>• Optimized for sales queries</li>
                    <li>• Regional distribution ready</li>
                  </ul>
                </div>
                <div className="p-6 bg-blue-50 border-2 border-blue-200 rounded-lg">
                  <h3 className="font-bold text-blue-800 mb-3">Node 3: Engineering/HR</h3>
                  <ul className="space-y-2 text-sm text-blue-700">
                    <li>• Complementary fragment</li>
                    <li>• Department ≠ 'Sales'</li>
                    <li>• No data overlap with Node 2</li>
                    <li>• Node 2 + Node 3 = Node 1</li>
                  </ul>
                </div>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}