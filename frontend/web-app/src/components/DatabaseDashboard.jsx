import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Database, Server, Activity, AlertCircle, CheckCircle2, Loader2, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { fetchAllOrders } from '../services/api';

export function DatabaseDashboard() {
  const [data, setData] = useState({
    node1: [],
    node2: [],
    node3: []
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [nodeStatus, setNodeStatus] = useState({
    node1: 'checking',
    node2: 'checking',
    node3: 'checking'
  });

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const orders = await fetchAllOrders();
      
      setData(orders);
      setNodeStatus({
        node1: orders.node1.length >= 0 ? 'online' : 'error',
        node2: orders.node2.length >= 0 ? 'online' : 'error',
        node3: orders.node3.length >= 0 ? 'online' : 'error'
      });
    } catch (err) {
      console.error('Failed to fetch orders:', err);
      setError(err.message || 'Failed to connect to database nodes');
      setNodeStatus({
        node1: 'error',
        node2: 'error',
        node3: 'error'
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // Auto-refresh every 5 seconds
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
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
        return 'bg-gray-400';
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

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleString();
  };

  const formatUUID = (uuid) => {
    if (!uuid) return 'N/A';
    return `${uuid.substring(0, 8)}...${uuid.substring(uuid.length - 8)}`;
  };

  return (
    <div className="space-y-6">
      {/* Header with Refresh Button */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-800">Database Overview</h2>
        <Button
          onClick={fetchData}
          disabled={loading}
          variant="outline"
          className="flex items-center gap-2"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Error Display */}
      {error && (
        <div className="p-4 bg-red-50 border-2 border-red-200 rounded-lg text-red-700">
          <p className="font-semibold">Error loading data:</p>
          <p className="text-sm">{error}</p>
        </div>
      )}

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
                      {index === 0 ? 'All Orders' : index === 1 ? 'Fragment 1' : 'Fragment 2'}
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
                <CardDescription>Complete dataset with all orders</CardDescription>
              </div>
              <Badge variant="outline" className="bg-green-50 text-green-700 border-green-300">
                <Activity className="w-3 h-3 mr-1" />
                {nodeStatus.node1 === 'active' ? 'Live' : 'Offline'}
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
                      <TableHead className="font-semibold">Order ID</TableHead>
                      <TableHead className="font-semibold">Quantity</TableHead>
                      <TableHead className="font-semibold">Created At</TableHead>
                      <TableHead className="font-semibold">Updated At</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.node1.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={4} className="text-center text-gray-500 py-8">
                          No orders found
                        </TableCell>
                      </TableRow>
                    ) : (
                      data.node1.map((row) => (
                        <TableRow key={row.order_id} className="hover:bg-cyan-50/50 transition-colors">
                          <TableCell className="font-mono text-sm" title={row.order_id}>
                            {formatUUID(row.order_id)}
                          </TableCell>
                          <TableCell>
                            <Badge variant="secondary">{row.quantity}</Badge>
                          </TableCell>
                          <TableCell className="text-sm text-gray-600">
                            {formatDate(row.created_at)}
                          </TableCell>
                          <TableCell className="text-sm text-gray-600">
                            {formatDate(row.updated_at)}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
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
              <CardTitle className="text-base">Node 2 - Fragment 1</CardTitle>
              <CardDescription>Horizontal partition (even order_id)</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="border rounded-lg overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-yellow-50">
                      <TableHead className="text-xs">Order ID</TableHead>
                      <TableHead className="text-xs">Quantity</TableHead>
                      <TableHead className="text-xs">Created</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.node2.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="text-center text-gray-500 py-4 text-sm">
                          No orders
                        </TableCell>
                      </TableRow>
                    ) : (
                      data.node2.map((row) => (
                        <TableRow key={row.order_id} className="hover:bg-yellow-50/50">
                          <TableCell className="font-mono text-xs" title={row.order_id}>
                            {formatUUID(row.order_id)}
                          </TableCell>
                          <TableCell className="text-sm">
                            <Badge variant="secondary" className="bg-yellow-100">
                              {row.quantity}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs text-gray-600">
                            {formatDate(row.created_at)}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          {/* Node 3 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Node 3 - Fragment 2</CardTitle>
              <CardDescription>Horizontal partition (odd order_id)</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="border rounded-lg overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-blue-50">
                      <TableHead className="text-xs">Order ID</TableHead>
                      <TableHead className="text-xs">Quantity</TableHead>
                      <TableHead className="text-xs">Created</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.node3.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="text-center text-gray-500 py-4 text-sm">
                          No orders
                        </TableCell>
                      </TableRow>
                    ) : (
                      data.node3.map((row) => (
                        <TableRow key={row.order_id} className="hover:bg-blue-50/50">
                          <TableCell className="font-mono text-xs" title={row.order_id}>
                            {formatUUID(row.order_id)}
                          </TableCell>
                          <TableCell className="text-sm">
                            <Badge variant="secondary" className="bg-blue-100">
                              {row.quantity}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs text-gray-600">
                            {formatDate(row.created_at)}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
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
