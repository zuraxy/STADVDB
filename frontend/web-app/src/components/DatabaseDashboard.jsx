import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Database, Server, Activity, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Badge } from './ui/badge';

export function DatabaseDashboard() {
  const [data, setData] = useState({
    node1: [],
    node2: [],
    node3: []
  });
  const [loading, setLoading] = useState(true);
  const [nodeStatus, setNodeStatus] = useState({
    node1: 'active',
    node2: 'active',
    node3: 'active'
  });

  // Mock data - replace with actual API calls
  useEffect(() => {
    // Simulate data fetch
    setTimeout(() => {
      setData({
        node1: [
          { id: 1, name: 'Alice', email: 'alice@example.com', department: 'Sales', salary: 50000 },
          { id: 2, name: 'Bob', email: 'bob@example.com', department: 'Engineering', salary: 75000 },
          { id: 3, name: 'Charlie', email: 'charlie@example.com', department: 'Sales', salary: 55000 },
        ],
        node2: [
          { id: 1, name: 'Alice', email: 'alice@example.com', department: 'Sales', salary: 50000 },
          { id: 3, name: 'Charlie', email: 'charlie@example.com', department: 'Sales', salary: 55000 },
        ],
        node3: [
          { id: 2, name: 'Bob', email: 'bob@example.com', department: 'Engineering', salary: 75000 },
        ]
      });
      setLoading(false);
    }, 1000);
  }, []);

  const getStatusColor = (status) => {
    switch (status) {
      case 'active':
        return 'bg-green-500';
      case 'warning':
        return 'bg-yellow-500';
      case 'error':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'active':
        return <CheckCircle2 className="w-4 h-4 text-green-600" />;
      case 'warning':
        return <AlertCircle className="w-4 h-4 text-yellow-600" />;
      case 'error':
        return <AlertCircle className="w-4 h-4 text-red-600" />;
      default:
        return <Loader2 className="w-4 h-4 animate-spin text-gray-600" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header with Node Status */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {['node1', 'node2', 'node3'].map((node, index) => (
          <motion.div
            key={node}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
          >
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Database className="w-5 h-5 text-cyan-600" />
                    <CardTitle className="text-sm font-medium">
                      {index === 0 ? 'Central Node' : `Fragment Node ${index}`}
                    </CardTitle>
                  </div>
                  {getStatusIcon(nodeStatus[node])}
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <p className="text-2xl font-bold text-cyan-700">
                      {data[node]?.length || 0}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {index === 0 ? 'All Records' : index === 1 ? 'Sales Dept' : 'Engineering/HR'}
                    </p>
                  </div>
                  <div className={`w-2 h-2 rounded-full ${getStatusColor(nodeStatus[node])} animate-pulse`} />
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Main Data Tables */}
      <div className="grid grid-cols-1 gap-6">
        {/* Node 1 - Central Node */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Node 1 - Central Database</CardTitle>
                <CardDescription>Complete dataset across all departments</CardDescription>
              </div>
              <Badge variant="outline" className="bg-green-50 text-green-700 border-green-300">
                <Activity className="w-3 h-3 mr-1" />
                Live
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-cyan-600" />
              </div>
            ) : (
              <div className="border rounded-lg overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-cyan-50">
                      <TableHead className="font-semibold">ID</TableHead>
                      <TableHead className="font-semibold">Name</TableHead>
                      <TableHead className="font-semibold">Email</TableHead>
                      <TableHead className="font-semibold">Department</TableHead>
                      <TableHead className="font-semibold">Salary</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.node1.map((row) => (
                      <TableRow key={row.id} className="hover:bg-cyan-50/50 transition-colors">
                        <TableCell className="font-medium">{row.id}</TableCell>
                        <TableCell>{row.name}</TableCell>
                        <TableCell>{row.email}</TableCell>
                        <TableCell>
                          <Badge variant="secondary">{row.department}</Badge>
                        </TableCell>
                        <TableCell>${row.salary.toLocaleString()}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Fragmented Nodes Side by Side */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Node 2 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Node 2 - Sales Fragment</CardTitle>
              <CardDescription>Department: Sales only</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="border rounded-lg overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-yellow-50">
                      <TableHead className="text-xs">ID</TableHead>
                      <TableHead className="text-xs">Name</TableHead>
                      <TableHead className="text-xs">Department</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.node2.map((row) => (
                      <TableRow key={row.id} className="hover:bg-yellow-50/50">
                        <TableCell className="text-sm">{row.id}</TableCell>
                        <TableCell className="text-sm">{row.name}</TableCell>
                        <TableCell className="text-sm">
                          <Badge variant="secondary" className="bg-yellow-100">
                            {row.department}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          {/* Node 3 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Node 3 - Engineering/HR Fragment</CardTitle>
              <CardDescription>Department: Non-Sales</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="border rounded-lg overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-blue-50">
                      <TableHead className="text-xs">ID</TableHead>
                      <TableHead className="text-xs">Name</TableHead>
                      <TableHead className="text-xs">Department</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.node3.map((row) => (
                      <TableRow key={row.id} className="hover:bg-blue-50/50">
                        <TableCell className="text-sm">{row.id}</TableCell>
                        <TableCell className="text-sm">{row.name}</TableCell>
                        <TableCell className="text-sm">
                          <Badge variant="secondary" className="bg-blue-100">
                            {row.department}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
