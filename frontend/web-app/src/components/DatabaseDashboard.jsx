import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Database, Activity, AlertCircle, CheckCircle2, Loader2, RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { fetchAllOrders, fetchReplicationStatus, fetchAllNodeMetrics, fetchNodeOrders } from '../services/api';

const DEFAULT_NODE_CARDS = [
  { id: 'node0', title: 'Central Node', description: 'Complete dataset with all orders', isPrimary: true },
  { id: 'node1', title: 'Fragment Node 1', description: 'Horizontal partition segment 1' },
  { id: 'node2', title: 'Fragment Node 2', description: 'Horizontal partition segment 2' },
];

const buildNodeState = (statusResponse) => {
  const map = new Map(
    DEFAULT_NODE_CARDS.map((card) => [card.id, { ...card, status: 'checking', error: null }]),
  );
  const normalizeKey = (name) => (name || '').toLowerCase();

  if (statusResponse?.nodes?.length) {
    statusResponse.nodes.forEach((node) => {
      const key = normalizeKey(node.name);
      if (!key) {
        return;
      }
      const base = map.get(key) || {
        id: key,
        title: node.name || key,
        description: node.role === 'peer' ? 'Replica node' : 'Cluster node',
      };
      map.set(key, {
        ...base,
        status: node.status || (node.error ? 'error' : 'online'),
        error: node.error || null,
        promoted: Boolean(node.promoted),
        role: node.role || base.role,
      });
    });
  } else if (statusResponse?.node) {
    const key = normalizeKey(statusResponse.node);
    const base = map.get(key) || {
      id: key,
      title: statusResponse.node,
      description: 'Cluster node',
    };
    map.set(key, { ...base, status: 'online', promoted: Boolean(statusResponse.promoted) });
  }

  const ordered = DEFAULT_NODE_CARDS.map((card) => map.get(card.id)).filter(Boolean);
  const extras = Array.from(map.entries())
    .filter(([key]) => !DEFAULT_NODE_CARDS.some((card) => card.id === key))
    .map(([, value]) => value);
  return [...ordered, ...extras];
};

export function DatabaseDashboard() {
  const [allData, setAllData] = useState([]);
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalRecords, setTotalRecords] = useState(0);
  const [partitionRule, setPartitionRule] = useState(null);
  const [nodeCards, setNodeCards] = useState(() => buildNodeState());
  const [nodeMetrics, setNodeMetrics] = useState({}); // Store metrics per node
  const [node1Data, setNode1Data] = useState([]); // NEW: Store actual Node1 data
  const [node2Data, setNode2Data] = useState([]); // NEW: Store actual Node2 data
  
  const itemsPerPage = 10;

  const applyReplicationStatus = useCallback((statusResponse, fallbackStatus = 'checking') => {
    if (statusResponse) {
      setNodeCards(buildNodeState(statusResponse));
      setPartitionRule(statusResponse.partition_rule ?? null);
    } else {
      setNodeCards(DEFAULT_NODE_CARDS.map((card) => ({ ...card, status: fallbackStatus })));
    }
  }, [setNodeCards, setPartitionRule]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);

    try {
      console.log('🔄 Fetching data from all nodes...');
      const [statusResponse, ordersResponse, metricsResponse, node1Orders, node2Orders] = await Promise.all([
        fetchReplicationStatus(),
        fetchAllOrders(),
        fetchAllNodeMetrics(),
        fetchNodeOrders('node1').catch(err => { 
          console.error('❌ Node1 fetch failed:', err); 
          return []; 
        }),
        fetchNodeOrders('node2').catch(err => { 
          console.error('❌ Node2 fetch failed:', err); 
          return []; 
        }),
      ]);

      console.log('✅ Data fetched:', {
        node0Orders: ordersResponse?.length || 0,
        node1Orders: node1Orders?.length || 0,
        node2Orders: node2Orders?.length || 0,
      });

      applyReplicationStatus(statusResponse);
      setNodeMetrics(metricsResponse);
      
      // Store node-specific data
      setNode1Data(Array.isArray(node1Orders) ? node1Orders : []);
      setNode2Data(Array.isArray(node2Orders) ? node2Orders : []);

      const rows = Array.isArray(ordersResponse) ? ordersResponse : [];
      setAllData(rows);
      setTotalRecords(rows.length);
      setTotalPages(Math.ceil(rows.length / itemsPerPage));
      
      // Set initial page data
      const startIndex = (currentPage - 1) * itemsPerPage;
      const endIndex = startIndex + itemsPerPage;
      setData(rows.slice(startIndex, endIndex));
    } catch (err) {
      console.error('❌ Failed to fetch data:', err);
      setError(err.message || 'Failed to connect to database nodes');
      applyReplicationStatus(null, 'error');
    } finally {
      setLoading(false);
    }
  };

  // Update displayed data when page changes
  useEffect(() => {
    if (allData.length > 0) {
      const startIndex = (currentPage - 1) * itemsPerPage;
      const endIndex = startIndex + itemsPerPage;
      setData(allData.slice(startIndex, endIndex));
    }
  }, [currentPage, allData]);

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    // Check node status every 5 seconds
    const statusInterval = setInterval(() => {
      fetchReplicationStatus()
        .then((statusResponse) => applyReplicationStatus(statusResponse))
        .catch((err) => console.error('Failed to check node status:', err));
    }, 5000);
    return () => clearInterval(statusInterval);
  }, [applyReplicationStatus]);

  useEffect(() => {
    // Refresh all data (including node-specific data) every 10 seconds
    const dataInterval = setInterval(() => {
      fetchData();
    }, 10000);
    return () => clearInterval(dataInterval);
  }, []);

  // Helper function to get actual node data
  const getNodeData = (nodeId) => {
    if (nodeId === 'node1') return node1Data;
    if (nodeId === 'node2') return node2Data;
    return [];
  };

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

  const getNodeStatusById = (id) => {
    return nodeCards.find((card) => card.id === id)?.status || 'checking';
  };

  const getBadgeClasses = (status) => {
    if (status === 'online') {
      return 'bg-green-50 text-green-700 border-green-300';
    }
    if (status === 'error') {
      return 'bg-red-50 text-red-700 border-red-300';
    }
    return 'bg-yellow-50 text-yellow-700 border-yellow-300';
  };

  const getBadgeLabel = (status) => {
    if (status === 'online') {
      return 'Live';
    }
    if (status === 'error') {
      return 'Offline';
    }
    return 'Checking';
  };

  const describeNode = (card) => {
    if (card.id === 'node0') {
      return 'All Orders';
    }
    if (card.id === 'node1') {
      return partitionRule ? `Quantity ≤ ${partitionRule}` : 'Fragment 1-5';
    }
    if (card.id === 'node2') {
      return partitionRule ? `Quantity > ${partitionRule}` : 'Fragment 6-10';
    }
    return card.description;
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
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">Auto-refresh: 10s</span>
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
        {nodeCards.map((card, index) => (
          <motion.div
            key={card.id}
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
                      {card.title}
                    </CardTitle>
                  </div>
                  {getStatusIcon(card.status)}
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <p className="text-2xl font-bold text-cyan-700">
                      {card.id === 'node1' ? node1Data.length : 
                       card.id === 'node2' ? node2Data.length :
                       card.isPrimary ? totalRecords : 0}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {describeNode(card)}
                    </p>
                    {/* NEW: Display applier and replicator metrics */}
                    {nodeMetrics[card.id] && !nodeMetrics[card.id].error && (
                      <div className="text-xs text-gray-500 mt-2 space-y-0.5">
                        {nodeMetrics[card.id].applier && (
                          <>
                            <div>Applied: {nodeMetrics[card.id].applier.applied_count || 0}</div>
                            <div>Skipped: {nodeMetrics[card.id].applier.skipped_count || 0}</div>
                          </>
                        )}
                        {nodeMetrics[card.id].replicator && (
                          <div>Replicated: {nodeMetrics[card.id].replicator.total_replicated || 0}</div>
                        )}
                      </div>
                    )}
                    {nodeMetrics[card.id]?.error && (
                      <div className="text-xs text-red-500 mt-1">
                        Error: {nodeMetrics[card.id].error}
                      </div>
                    )}
                  </div>
                  <div className={`w-2 h-2 rounded-full ${getStatusColor(card.status)} animate-pulse`} />
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
              <Badge variant="outline" className={getBadgeClasses(getNodeStatusById('node0'))}>
                <Activity className="w-3 h-3 mr-1" />
                {getBadgeLabel(getNodeStatusById('node0'))}
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
                <Badge variant="outline" className={getBadgeClasses(getNodeStatusById('node1'))}>
                  <Activity className="w-3 h-3 mr-1" />
                  {getBadgeLabel(getNodeStatusById('node1'))}
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
                    {loading ? (
                      <TableRow>
                        <TableCell colSpan={2} className="text-center py-4">
                          <Loader2 className="w-4 h-4 animate-spin inline" />
                        </TableCell>
                      </TableRow>
                    ) : node1Data.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={2} className="text-center text-gray-500 py-4 text-sm">
                          No orders in this node
                        </TableCell>
                      </TableRow>
                    ) : (
                      node1Data.slice(0, 5).map((order) => (
                        <TableRow key={order.order_id}>
                          <TableCell className="text-xs font-mono">{formatUUID(order.order_id)}</TableCell>
                          <TableCell className="text-xs">{order.quantity}</TableCell>
                        </TableRow>
                      ))
                    )}
                    {node1Data.length > 5 && (
                      <TableRow>
                        <TableCell colSpan={2} className="text-center text-gray-500 py-2 text-xs">
                          ... and {node1Data.length - 5} more
                        </TableCell>
                      </TableRow>
                    )}
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
                <Badge variant="outline" className={getBadgeClasses(getNodeStatusById('node2'))}>
                  <Activity className="w-3 h-3 mr-1" />
                  {getBadgeLabel(getNodeStatusById('node2'))}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="border rounded-lg overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-purple-50">
                      <TableHead className="text-xs">Order ID</TableHead>
                      <TableHead className="text-xs">Quantity</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loading ? (
                      <TableRow>
                        <TableCell colSpan={2} className="text-center py-4">
                          <Loader2 className="w-4 h-4 animate-spin inline" />
                        </TableCell>
                      </TableRow>
                    ) : node2Data.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={2} className="text-center text-gray-500 py-4 text-sm">
                          No orders in this node
                        </TableCell>
                      </TableRow>
                    ) : (
                      node2Data.slice(0, 5).map((order) => (
                        <TableRow key={order.order_id}>
                          <TableCell className="text-xs font-mono">{formatUUID(order.order_id)}</TableCell>
                          <TableCell className="text-xs">{order.quantity}</TableCell>
                        </TableRow>
                      ))
                    )}
                    {node2Data.length > 5 && (
                      <TableRow>
                        <TableCell colSpan={2} className="text-center text-gray-500 py-2 text-xs">
                          ... and {node2Data.length - 5} more
                        </TableCell>
                      </TableRow>
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
