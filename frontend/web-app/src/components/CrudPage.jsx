import { useState, useEffect } from 'react';
import { Plus, Search, Edit, Trash2, Save, X, Loader2, AlertCircle, CheckCircle2, ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import { Alert, AlertDescription } from './ui/alert';
import { fetchAllOrders, createOrder, updateOrder, deleteOrder } from '../services/api';

export function CrudPage() {
  const [allOrders, setAllOrders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [isAdding, setIsAdding] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [formData, setFormData] = useState({ quantity: '', payload: '' });
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  const loadOrders = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchAllOrders();
      setAllOrders(response);
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
    if (!formData.quantity) {
      setError('Please enter a quantity');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const orderData = {
        quantity: parseInt(formData.quantity),
        payload: formData.payload ? JSON.parse(formData.payload) : null,
      };
      
      await createOrder(orderData);
      await loadOrders(); // Reload to get fresh data
      setFormData({ quantity: '', payload: '' });
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
      const orderData = {
        quantity: parseInt(formData.quantity),
        payload: formData.payload ? JSON.parse(formData.payload) : null,
      };
      
      await updateOrder(orderId, orderData);
      await loadOrders(); // Reload to get fresh data
      setEditingId(null);
      setFormData({ quantity: '', payload: '' });
      setSuccess('Order updated successfully!');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err.message || 'Failed to update order');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (orderId) => {
    if (!confirm(`Are you sure you want to delete this order?`)) {
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await deleteOrder(orderId);
      await loadOrders(); // Reload to get fresh data
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
    setFormData({ 
      quantity: order.quantity.toString(),
      payload: order.payload ? JSON.stringify(order.payload) : '',
    });
    setIsAdding(false);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setFormData({ quantity: '', payload: '' });
  };

  const filteredOrders = allOrders.filter(order => 
    order.order_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
    order.quantity.toString().includes(searchTerm)
  );

  // Pagination calculations
  const totalPages = Math.ceil(filteredOrders.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const paginatedOrders = filteredOrders.slice(startIndex, endIndex);

  // Reset to page 1 when search term changes
  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm]);

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
                <label className="text-sm font-medium mb-2 block">Quantity</label>
                <Input
                  type="number"
                  placeholder="Enter quantity"
                  value={formData.quantity}
                  onChange={(e) => setFormData({ ...formData, quantity: e.target.value })}
                  min="1"
                  data-testid="create-quantity-input"
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-2 block">Payload (Optional JSON)</label>
                <Input
                  type="text"
                  placeholder='{"key": "value"}'
                  value={formData.payload}
                  onChange={(e) => setFormData({ ...formData, payload: e.target.value })}
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
                  setFormData({ quantity: '', payload: '' });
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
          <div className="flex items-center justify-between">
            <CardTitle>Orders ({filteredOrders.length} total)</CardTitle>
            <div className="text-sm text-gray-500">
              Page {currentPage} of {totalPages || 1}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading && !allOrders.length ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-cyan-600" />
            </div>
          ) : (
            <>
              <div className="border rounded-lg overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-cyan-50">
                      <TableHead className="font-semibold">Order ID</TableHead>
                      <TableHead className="font-semibold">Quantity</TableHead>
                      <TableHead className="font-semibold">Payload</TableHead>
                      <TableHead className="font-semibold">Created At</TableHead>
                      <TableHead className="font-semibold text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedOrders.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} className="text-center text-gray-500 py-8">
                          No orders found
                        </TableCell>
                      </TableRow>
                    ) : (
                      paginatedOrders.map((order) => (
                        <TableRow key={order.order_id} className="hover:bg-cyan-50/50">
                          <TableCell className="font-mono text-xs">
                          {order.order_id.substring(0, 8)}...
                        </TableCell>
                        <TableCell>
                          {editingId === order.order_id ? (
                            <Input
                              type="number"
                              value={formData.quantity}
                              onChange={(e) => setFormData({ ...formData, quantity: e.target.value })}
                              className="w-32"
                              min="1"
                              data-testid="edit-quantity-input"
                            />
                          ) : (
                            <Badge variant="secondary">{order.quantity}</Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-xs">
                          {editingId === order.order_id ? (
                            <Input
                              type="text"
                              value={formData.payload}
                              onChange={(e) => setFormData({ ...formData, payload: e.target.value })}
                              className="w-48"
                              placeholder='{"key": "value"}'
                            />
                          ) : (
                            <code className="text-gray-600">
                              {order.payload ? JSON.stringify(order.payload) : 'null'}
                            </code>
                          )}
                        </TableCell>
                        <TableCell className="text-xs text-gray-600">
                          {new Date(order.created_at).toLocaleString()}
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

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 pt-4 border-t">
                <div className="text-sm text-gray-600">
                  Showing {startIndex + 1} to {Math.min(endIndex, filteredOrders.length)} of {filteredOrders.length} orders
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    onClick={() => setCurrentPage(1)}
                    disabled={currentPage === 1}
                    size="sm"
                    variant="outline"
                  >
                    First
                  </Button>
                  <Button
                    onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                    disabled={currentPage === 1}
                    size="sm"
                    variant="outline"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                  
                  <div className="flex items-center gap-1">
                    {/* Smart pagination: show current page ± 2 pages */}
                    {currentPage > 3 && (
                      <>
                        <Button
                          onClick={() => setCurrentPage(1)}
                          size="sm"
                          variant="outline"
                        >
                          1
                        </Button>
                        {currentPage > 4 && <span className="px-2 text-gray-400">...</span>}
                      </>
                    )}
                    
                    {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                      let page;
                      if (totalPages <= 5) {
                        page = i + 1;
                      } else if (currentPage <= 3) {
                        page = i + 1;
                      } else if (currentPage >= totalPages - 2) {
                        page = totalPages - 4 + i;
                      } else {
                        page = currentPage - 2 + i;
                      }
                      
                      if (page < 1 || page > totalPages) return null;
                      
                      return (
                        <Button
                          key={page}
                          onClick={() => setCurrentPage(page)}
                          size="sm"
                          variant={currentPage === page ? "default" : "outline"}
                          className={currentPage === page ? "bg-cyan-600 hover:bg-cyan-700" : ""}
                        >
                          {page}
                        </Button>
                      );
                    })}
                    
                    {currentPage < totalPages - 2 && (
                      <>
                        {currentPage < totalPages - 3 && <span className="px-2 text-gray-400">...</span>}
                        <Button
                          onClick={() => setCurrentPage(totalPages)}
                          size="sm"
                          variant="outline"
                        >
                          {totalPages}
                        </Button>
                      </>
                    )}
                  </div>
                  
                  <Button
                    onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                    disabled={currentPage === totalPages}
                    size="sm"
                    variant="outline"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                  <Button
                    onClick={() => setCurrentPage(totalPages)}
                    disabled={currentPage === totalPages}
                    size="sm"
                    variant="outline"
                  >
                    Last
                  </Button>
                  
                  {/* Page jump input */}
                  <div className="flex items-center gap-2 ml-2 pl-2 border-l">
                    <span className="text-sm text-gray-600">Go to:</span>
                    <Input
                      type="number"
                      min={1}
                      max={totalPages}
                      value={currentPage}
                      onChange={(e) => {
                        const page = parseInt(e.target.value);
                        if (page >= 1 && page <= totalPages) {
                          setCurrentPage(page);
                        }
                      }}
                      className="w-20 text-center"
                    />
                  </div>
                </div>
              </div>
            )}
          </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
