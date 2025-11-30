import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Database, Server, Activity, AlertCircle, CheckCircle2, Loader2, RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { fetchAllOrders, testAllConnections } from '../services/api';

export function DatabaseDashboard() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalRecords, setTotalRecords] = useState(0);
  const [nodeStatus, setNodeStatus] = useState({
    Node1: 'checking',
    Node2: 'checking',
    Node3: 'checking'
  });

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    
    try {
      // First, check which nodes are online
      const connectionStatus = await testAllConnections();
      
      // Update node status based on connection test
      const newStatus = {};
      if (connectionStatus.success && connectionStatus.connections) {
        Object.keys(connectionStatus.connections).forEach(nodeName => {
          const nodeInfo = connectionStatus.connections[nodeName];
          newStatus[nodeName] = nodeInfo.status === 'connected' ? 'online' : 'error';
        });
        setNodeStatus(newStatus);
      }
      
      // Fetch all orders from Node1 (central node)
      const ordersResponse = await fetchAllOrders(currentPage, 10);
      
      if (ordersResponse.success) {
        setData(ordersResponse.data || []);
        if (ordersResponse.pagination) {
          setTotalPages(ordersResponse.pagination.totalPages);
          setTotalRecords(ordersResponse.pagination.total);
        }
      } else {
        throw new Error('Failed to fetch orders');
      }
    } catch (err) {
      console.error('Failed to fetch data:', err);
      setError(err.message || 'Failed to connect to database nodes');
      setNodeStatus({
        Node1: 'error',
        Node2: 'error',
        Node3: 'error'
      });
    } finally {
      setLoading(false);
    }
  };

  const checkNodeStatus = async () => {
    try {
      const connectionStatus = await testAllConnections();
      
      if (connectionStatus.success && connectionStatus.connections) {
        const newStatus = {};
        Object.keys(connectionStatus.connections).forEach(nodeName => {
          const nodeInfo = connectionStatus.connections[nodeName];
          newStatus[nodeName] = nodeInfo.status === 'connected' ? 'online' : 'error';
        });
        setNodeStatus(newStatus);
      }
    } catch (err) {
      console.error('Failed to check node status:', err);
    }
  };

  useEffect(() => {
    fetchData();
  }, [currentPage]);

  useEffect(() => {
    // Check node status every 5 seconds
    const statusInterval = setInterval(checkNodeStatus, 5000);
    return () => clearInterval(statusInterval);
  }, []);

  const getStatusColor = (status) => {
    switch (status) {
      case 'online':
        return 'bg-green-500';
      case 'checking':
        return 'bg-yellow-500';
      case 'error':
        return 'bg-red-500';
      default:
        return 'bg-gray-400';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'online':
        return <CheckCircle2 className="w-4 h-4 text-green-600" />;
      case 'checking':
        return <Loader2 className="w-4 h-4 animate-spin text-gray-600" />;
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
        {['Node1', 'Node2', 'Node3'].map((node, index) => (
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
                      {index === 0 ? totalRecords : 0}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {index === 0 ? 'All Orders' : index === 1 ? 'Fragment 1-5' : 'Fragment 6-10'}
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
              <Badge variant="outline" className={nodeStatus.Node1 === 'online' ? 'bg-green-50 text-green-700 border-green-300' : 'bg-red-50 text-red-700 border-red-300'}>
                <Activity className="w-3 h-3 mr-1" />
                {nodeStatus.Node1 === 'online' ? 'Live' : 'Offline'}
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
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={2} className="text-center text-gray-500 py-8">
                          No orders found
                        </TableCell>
                      </TableRow>
                    ) : (
                      data.map((row) => (
                        <TableRow key={row.order_id} className="hover:bg-cyan-50/50 transition-colors">
                          <TableCell className="font-mono text-sm">
                            {row.order_id}
                          </TableCell>
                          <TableCell>
                            <Badge variant="secondary">{row.quantity}</Badge>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
            
            {/* Pagination Controls */}
            {!loading && totalPages > 1 && (
              <div className="flex items-center justify-between pt-4 border-t">
                <div className="text-sm text-gray-600">
                  Showing page {currentPage} of {totalPages} ({totalRecords.toLocaleString()} total records)
                </div>
                <div className="flex gap-2">
                  <Button
                    onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                    disabled={currentPage === 1}
                    variant="outline"
                    size="sm"
                  >
                    <ChevronLeft className="w-4 h-4 mr-1" />
                    Previous
                  </Button>
                  <Button
                    onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                    disabled={currentPage === totalPages}
                    variant="outline"
                    size="sm"
                  >
                    Next
                    <ChevronRight className="w-4 h-4 ml-1" />
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Fragmented Nodes Side by Side */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Node 2 */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base">Node 2 - Fragment 1</CardTitle>
                  <CardDescription>Orders 1-5 (Horizontal partition)</CardDescription>
                </div>
                <Badge variant="outline" className={nodeStatus.Node2 === 'online' ? 'bg-green-50 text-green-700 border-green-300' : 'bg-red-50 text-red-700 border-red-300'}>
                  <Activity className="w-3 h-3 mr-1" />
                  {nodeStatus.Node2 === 'online' ? 'Live' : 'Offline'}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="border rounded-lg overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-yellow-50">
                      <TableHead className="text-xs">Order ID</TableHead>
                      <TableHead className="text-xs">Quantity</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow>
                      <TableCell colSpan={2} className="text-center text-gray-500 py-4 text-sm">
                        Fragment-specific data not loaded
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          {/* Node 3 */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base">Node 3 - Fragment 2</CardTitle>
                  <CardDescription>Orders 6-10 (Horizontal partition)</CardDescription>
                </div>
                <Badge variant="outline" className={nodeStatus.Node3 === 'online' ? 'bg-green-50 text-green-700 border-green-300' : 'bg-red-50 text-red-700 border-red-300'}>
                  <Activity className="w-3 h-3 mr-1" />
                  {nodeStatus.Node3 === 'online' ? 'Live' : 'Offline'}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="border rounded-lg overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-blue-50">
                      <TableHead className="text-xs">Order ID</TableHead>
                      <TableHead className="text-xs">Quantity</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow>
                      <TableCell colSpan={2} className="text-center text-gray-500 py-4 text-sm">
                        Fragment-specific data not loaded
                      </TableCell>
                    </TableRow>
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
