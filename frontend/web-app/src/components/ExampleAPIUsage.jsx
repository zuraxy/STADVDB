/**
 * Example usage of the centralized API service
 * 
 * This file demonstrates how to use the API functions
 * in your components. Copy these patterns to your own components.
 */

import { useState, useEffect } from 'react';
import { 
  fetchAllOrders, 
  createOrder, 
  updateOrder, 
  deleteOrder,
  getAllNodeStatus 
} from '../services/api';

export function ExampleComponent() {
  const [orders, setOrders] = useState({ node0: [], node1: [], node2: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Example 1: Fetch all orders on component mount
  useEffect(() => {
    loadOrders();
  }, []);

  const loadOrders = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const data = await fetchAllOrders();
      setOrders(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Example 2: Create a new order
  const handleCreateOrder = async (quantity, payload) => {
    try {
      const result = await createOrder({ quantity, payload });
      console.log('Order created:', result);
      
      // Refresh the list after creating
      await loadOrders();
    } catch (err) {
      console.error('Failed to create order:', err);
    }
  };

  // Example 3: Update an existing order
  const handleUpdateOrder = async (orderId, newQuantity) => {
    try {
      const result = await updateOrder(orderId, { quantity: newQuantity });
      console.log('Order updated:', result);
      
      // Refresh the list after updating
      await loadOrders();
    } catch (err) {
      console.error('Failed to update order:', err);
    }
  };

  // Example 4: Delete an order
  const handleDeleteOrder = async (orderId) => {
    try {
      await deleteOrder(orderId);
      console.log('Order deleted');
      
      // Refresh the list after deleting
      await loadOrders();
    } catch (err) {
      console.error('Failed to delete order:', err);
    }
  };

  // Example 5: Check node status
  const checkNodeStatus = async () => {
    try {
      const status = await getAllNodeStatus();
      console.log('Node status:', status);
    } catch (err) {
      console.error('Failed to check status:', err);
    }
  };

  return (
    <div>
      <h2>Example Component</h2>
      
      {loading && <p>Loading...</p>}
      {error && <p>Error: {error}</p>}
      
      <div>
        <h3>Node 0: {orders.node0.length} orders</h3>
        <h3>Node 1: {orders.node1.length} orders</h3>
        <h3>Node 2: {orders.node2.length} orders</h3>
      </div>

      <button onClick={() => handleCreateOrder(10, { item: 'test' })}>
        Create Order
      </button>
      <button onClick={checkNodeStatus}>
        Check Status
      </button>
    </div>
  );
}
