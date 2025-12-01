import { useState, useEffect } from 'react';
import { Plus, Search, Edit, Trash2, Save, X, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import { Alert, AlertDescription } from './ui/alert';

export function CrudPage() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [isAdding, setIsAdding] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [formData, setFormData] = useState({ order_id: '', quantity: '' });

  // Placeholder for future API integration
  const loadOrders = async () => {
    setLoading(true);
    setError(null);
    try {
      // TODO: Replace with actual API call
      // const response = await fetchAllOrders(1, 100);
      // setOrders(response.data);
      
      // Mock data for now
      setOrders([
        { order_id: '1', quantity: 10 },
        { order_id: '2', quantity: 25 },
        { order_id: '3', quantity: 15 },
        { order_id: '4', quantity: 30 },
        { order_id: '5', quantity: 5 },
      ]);
    } catch (err) {
      setError(err.message || 'Failed to load orders');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOrders();
  }, []);

  const handleCreate = async () => {
    if (!formData.order_id || !formData.quantity) {
      setError('Please fill in all fields');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      // TODO: Replace with actual API call
      // await createOrder(formData);
      
      // Mock implementation
      setOrders([...orders, { ...formData, quantity: parseInt(formData.quantity) }]);
      setFormData({ order_id: '', quantity: '' });
      setIsAdding(false);
      setSuccess('Order created successfully!');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err.message || 'Failed to create order');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdate = async (orderId) => {
    if (!formData.quantity) {
      setError('Please enter a quantity');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      // TODO: Replace with actual API call
      // await updateOrder(orderId, { quantity: parseInt(formData.quantity) });
      
      // Mock implementation
      setOrders(orders.map(order => 
        order.order_id === orderId 
          ? { ...order, quantity: parseInt(formData.quantity) }
          : order
      ));
      setEditingId(null);
      setFormData({ order_id: '', quantity: '' });
      setSuccess('Order updated successfully!');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err.message || 'Failed to update order');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (orderId) => {
    if (!confirm(`Are you sure you want to delete order ${orderId}?`)) {
      return;
    }

    setLoading(true);
    setError(null);
    try {
      // TODO: Replace with actual API call
      // await deleteOrder(orderId);
      
      // Mock implementation
      setOrders(orders.filter(order => order.order_id !== orderId));
      setSuccess('Order deleted successfully!');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err.message || 'Failed to delete order');
    } finally {
      setLoading(false);
    }
  };

  const startEdit = (order) => {
    setEditingId(order.order_id);
    setFormData({ order_id: order.order_id, quantity: order.quantity.toString() });
    setIsAdding(false);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setFormData({ order_id: '', quantity: '' });
  };

  const filteredOrders = orders.filter(order => 
    order.order_id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-2xl">Order Management</CardTitle>
              <CardDescription>Create, update, and delete orders in the database</CardDescription>
            </div>
            <Button
              onClick={() => {
                setIsAdding(!isAdding);
                setEditingId(null);
                setFormData({ order_id: '', quantity: '' });
              }}
              className="bg-cyan-600 hover:bg-cyan-700"
            >
              <Plus className="w-4 h-4 mr-2" />
              New Order
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {/* Search Bar */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              type="text"
              placeholder="Search by Order ID..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
        </CardContent>
      </Card>

      {/* Success/Error Messages */}
      {success && (
        <Alert className="bg-green-50 border-green-200">
          <CheckCircle2 className="w-4 h-4 text-green-600" />
          <AlertDescription className="text-green-800">{success}</AlertDescription>
        </Alert>
      )}

      {error && (
        <Alert className="bg-red-50 border-red-200">
          <AlertCircle className="w-4 h-4 text-red-600" />
          <AlertDescription className="text-red-800">{error}</AlertDescription>
        </Alert>
      )}

      {/* Create Form */}
      {isAdding && (
        <Card className="border-cyan-200">
          <CardHeader>
            <CardTitle className="text-lg text-cyan-800">Create New Order</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium mb-2 block">Order ID</label>
                <Input
                  type="text"
                  placeholder="Enter order ID"
                  value={formData.order_id}
                  onChange={(e) => setFormData({ ...formData, order_id: e.target.value })}
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-2 block">Quantity</label>
                <Input
                  type="number"
                  placeholder="Enter quantity"
                  value={formData.quantity}
                  onChange={(e) => setFormData({ ...formData, quantity: e.target.value })}
                />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <Button
                onClick={handleCreate}
                disabled={loading}
                className="bg-green-600 hover:bg-green-700"
              >
                {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
                Create Order
              </Button>
              <Button
                onClick={() => {
                  setIsAdding(false);
                  setFormData({ order_id: '', quantity: '' });
                }}
                variant="outline"
              >
                <X className="w-4 h-4 mr-2" />
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Orders Table */}
      <Card>
        <CardHeader>
          <CardTitle>Orders ({filteredOrders.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {loading && !orders.length ? (
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
                    <TableHead className="font-semibold text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredOrders.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3} className="text-center text-gray-500 py-8">
                        No orders found
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredOrders.map((order) => (
                      <TableRow key={order.order_id} className="hover:bg-cyan-50/50">
                        <TableCell className="font-mono">
                          {order.order_id}
                        </TableCell>
                        <TableCell>
                          {editingId === order.order_id ? (
                            <Input
                              type="number"
                              value={formData.quantity}
                              onChange={(e) => setFormData({ ...formData, quantity: e.target.value })}
                              className="w-32"
                            />
                          ) : (
                            <Badge variant="secondary">{order.quantity}</Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          {editingId === order.order_id ? (
                            <div className="flex gap-2 justify-end">
                              <Button
                                onClick={() => handleUpdate(order.order_id)}
                                disabled={loading}
                                size="sm"
                                className="bg-green-600 hover:bg-green-700"
                              >
                                {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                              </Button>
                              <Button
                                onClick={cancelEdit}
                                size="sm"
                                variant="outline"
                              >
                                <X className="w-3 h-3" />
                              </Button>
                            </div>
                          ) : (
                            <div className="flex gap-2 justify-end">
                              <Button
                                onClick={() => startEdit(order)}
                                size="sm"
                                variant="outline"
                                className="text-blue-600 hover:text-blue-700 hover:bg-blue-50"
                              >
                                <Edit className="w-3 h-3" />
                              </Button>
                              <Button
                                onClick={() => handleDelete(order.order_id)}
                                disabled={loading}
                                size="sm"
                                variant="outline"
                                className="text-red-600 hover:text-red-700 hover:bg-red-50"
                              >
                                {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                              </Button>
                            </div>
                          )}
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
    </div>
  );
}
